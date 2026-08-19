from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from skillforge_kb.agents.planning_agent import CoursePlanningAgent
from skillforge_kb.agents.planning_agent_models import CoursePlanningAgentResult
from skillforge_kb.agents.resource_agent import ResourceGenerationAgent
from skillforge_kb.agents.retrieval_agent import DomainRetrievalAgent
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
from skillforge_kb.resources.handoff import ResourceHandoffContract
from skillforge_kb.retrieval.bm25 import Bm25KnowledgeRetriever
from skillforge_kb.retrieval.corpus import KnowledgeCorpus
from skillforge_kb.retrieval.tool import KnowledgeRetrievalTool

from .graph import PlatformGraphDependencies, PlatformService
from .repository import InMemoryPlatformRunRepository


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
    corpus = KnowledgeCorpus.load(paths.knowledge_file)
    planning_agent = CoursePlanningAgent.create(catalog, attributes)
    retrieval_agent = DomainRetrievalAgent(
        corpus,
        KnowledgeRetrievalTool(Bm25KnowledgeRetriever(corpus)),
        evidence_index,
    )
    dependencies = PlatformGraphDependencies(
        planning_agent=planning_agent,
        retrieval_agent=retrieval_agent,
        resource_agent=ResourceGenerationAgent(),
        handoff_factory=ResourceHandoffFactory(catalog, blueprints, evidence_index),
        evidence_index=evidence_index,
        clock=SystemClock(),
    )
    return PlatformService(dependencies, InMemoryPlatformRunRepository())


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
