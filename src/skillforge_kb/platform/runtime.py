import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import SecretStr

from skillforge_kb.agents.planning_agent import CoursePlanningAgent
from skillforge_kb.agents.planning_agent_models import CoursePlanningAgentResult
from skillforge_kb.agents.resource_agent import ResourceGenerationAgent
from skillforge_kb.agents.retrieval_agent import DomainRetrievalAgent
from skillforge_kb.config import Settings
from skillforge_kb.evidence.manifest import EvidenceIndex, load_evidence_index
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.ontology.profile_agent_adapter import LearnerProfileAgentAdapter
from skillforge_kb.ontology.resource_blueprints import (
    ResourceBlueprintCatalog,
    load_resource_blueprints,
)
from skillforge_kb.ontology.validation import validate_catalog
from skillforge_kb.resources.briefs import ResourceBriefBuilder
from skillforge_kb.resources.controlled_generation import OpenAICompatibleLLMAdapter
from skillforge_kb.resources.handoff import ResourceHandoffContract
from skillforge_kb.retrieval.bm25 import Bm25KnowledgeRetriever
from skillforge_kb.retrieval.corpus import KnowledgeCorpus
from skillforge_kb.retrieval.tool import KnowledgeRetrievalTool

from .graph import PlatformGraphDependencies, PlatformService
from .repository import SqlitePlatformRunRepository


@dataclass(frozen=True)
class DefaultPlatformPaths:
    course_file: Path
    relations_file: Path
    attributes_file: Path
    blueprints_file: Path
    evidence_file: Path
    profile_agent_map_file: Path
    knowledge_file: Path

    @classmethod
    def from_project_root(cls, root: Path) -> "DefaultPlatformPaths":
        ontology = root / "resources" / "ontology"
        return cls(
            course_file=ontology / "ai_course_v1.yaml",
            relations_file=ontology / "ai_relations_v1.yaml",
            attributes_file=ontology / "concept_attributes_v1.yaml",
            blueprints_file=ontology / "resource_blueprints_v1.yaml",
            evidence_file=(
                root / "resources" / "evidence" / "evidence_manifest_v1.yaml"
            ),
            profile_agent_map_file=(
                root / "resources" / "ontology" / "profile_agent_kp_map_v1.yaml"
            ),
            knowledge_file=root / "data" / "index_chunks.jsonl",
        )


@dataclass(frozen=True)
class ResourceHandoffFactory:
    catalog: OntologyCatalog
    blueprints: ResourceBlueprintCatalog
    evidence_index: EvidenceIndex

    def build(
        self,
        planning: CoursePlanningAgentResult,
        profile: LearnerProfileSnapshot,
    ) -> ResourceHandoffContract:
        if planning.path is None or planning.current_node is None:
            raise ValueError("planning result does not contain a current path node")
        return ResourceBriefBuilder(
            catalog=self.catalog,
            blueprints=self.blueprints,
            adaptations=planning.adaptations,
            evidence_index=self.evidence_index,
        ).build_handoff(
            planning.path,
            profile,
            planning.current_node.concept_id,
        )


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def validate_default_platform_paths(paths: DefaultPlatformPaths) -> None:
    for path in (
        paths.course_file,
        paths.relations_file,
        paths.attributes_file,
        paths.blueprints_file,
        paths.evidence_file,
        paths.profile_agent_map_file,
        paths.knowledge_file,
    ):
        if not path.is_file():
            raise ValueError(f"required platform file is missing: {path}")


def build_default_platform_service(project_root: Path) -> PlatformService:
    root = project_root.expanduser().resolve()
    paths = DefaultPlatformPaths.from_project_root(root)
    validate_default_platform_paths(paths)
    catalog = OntologyCatalog.load(paths.course_file, paths.relations_file)
    validate_catalog(catalog)
    attributes = load_concept_attributes(catalog, paths.attributes_file)
    blueprints = load_resource_blueprints(catalog, paths.blueprints_file)
    evidence_index = load_evidence_index(catalog, paths.evidence_file)
    corpus = KnowledgeCorpus.load_many((paths.knowledge_file,))
    retrieval_agent = DomainRetrievalAgent(
        corpus,
        KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus)),
        evidence_index,
        catalog=catalog,
    )
    settings = Settings()
    # Keep interactive path planning bounded. Resource previews already have a
    # deterministic, evidence-bounded fallback, so a slow external model must
    # not leave the whole learning-path request waiting indefinitely. The
    # preview makes four model calls (three in parallel, then the teacher guide),
    # so a 6-second per-call cap keeps the page responsive while still allowing
    # a healthy local/network model to personalize the draft.
    llm_timeout_seconds = min(settings.llm_timeout_seconds, 6.0)
    llm_adapter = (
        OpenAICompatibleLLMAdapter(
            base_url=cast(str, settings.llm_base_url),
            api_key=cast(SecretStr, settings.llm_api_key),
            model_name=cast(str, settings.llm_model),
            timeout_seconds=llm_timeout_seconds,
        )
        if settings.llm_configured
        else None
    )
    state_db = Path(settings.platform_state_db).expanduser()
    if not state_db.is_absolute():
        state_db = root / state_db
    state_db.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_connection = sqlite3.connect(state_db, check_same_thread=False)
    try:
        planning_agent = CoursePlanningAgent.create(
            catalog,
            attributes,
            checkpointer=SqliteSaver(checkpoint_connection),
        )
        dependencies = PlatformGraphDependencies(
            planning_agent=planning_agent,
            retrieval_agent=retrieval_agent,
            resource_agent=ResourceGenerationAgent(llm_adapter=llm_adapter),
            handoff_factory=ResourceHandoffFactory(catalog, blueprints, evidence_index),
            evidence_index=evidence_index,
            clock=SystemClock(),
            catalog=catalog,
            practice_llm=llm_adapter,
        )
        return PlatformService(
            dependencies,
            SqlitePlatformRunRepository(state_db),
            close_callbacks=(checkpoint_connection.close,),
        )
    except BaseException:
        checkpoint_connection.close()
        raise


def build_default_profile_agent_adapter(
    project_root: Path,
) -> LearnerProfileAgentAdapter:
    root = project_root.expanduser().resolve()
    paths = DefaultPlatformPaths.from_project_root(root)
    validate_default_platform_paths(paths)
    catalog = OntologyCatalog.load(paths.course_file, paths.relations_file)
    validate_catalog(catalog)
    return LearnerProfileAgentAdapter.load_mappings(
        catalog,
        paths.profile_agent_map_file,
    )
