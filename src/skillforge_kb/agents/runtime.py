import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import ValidationError

from skillforge_kb.agents.planning_agent import CoursePlanningAgent
from skillforge_kb.agents.planning_agent_models import (
    CoursePlanningAgentResult,
    PlanningAgentEvent,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.validation import validate_catalog
from skillforge_kb.retrieval.bm25 import Bm25KnowledgeRetriever
from skillforge_kb.retrieval.corpus import KnowledgeCorpus
from skillforge_kb.retrieval.tool import KnowledgeRetrievalTool


@dataclass(frozen=True)
class StandaloneAgentPaths:
    course_file: Path
    relations_file: Path
    attributes_file: Path
    knowledge_file: Path

    @classmethod
    def from_project_root(cls, root: Path) -> "StandaloneAgentPaths":
        return cls(
            course_file=root / "resources" / "ontology" / "ai_course_v1.yaml",
            relations_file=root / "resources" / "ontology" / "ai_relations_v1.yaml",
            attributes_file=root / "resources" / "ontology" / "concept_attributes_v1.yaml",
            knowledge_file=root / "data" / "index_chunks.jsonl",
        )


def load_planning_event(path: Path) -> PlanningAgentEvent:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PlanningAgentEvent.model_validate(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise ValueError(f"invalid planning event at {path}: {exc}") from exc


def build_standalone_course_planning_agent(
    paths: StandaloneAgentPaths,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CoursePlanningAgent:
    catalog = OntologyCatalog.load(paths.course_file, paths.relations_file)
    validate_catalog(catalog)
    attributes = load_concept_attributes(catalog, paths.attributes_file)
    corpus = KnowledgeCorpus.load(paths.knowledge_file)
    retriever = Bm25KnowledgeRetriever(corpus)
    return CoursePlanningAgent.create(
        catalog,
        attributes,
        knowledge_tool=KnowledgeRetrievalTool(retriever),
        checkpointer=checkpointer,
    )


def validate_standalone_agent_paths(paths: StandaloneAgentPaths) -> None:
    catalog = OntologyCatalog.load(paths.course_file, paths.relations_file)
    validate_catalog(catalog)
    load_concept_attributes(catalog, paths.attributes_file)
    KnowledgeCorpus.load(paths.knowledge_file)


def run_standalone_event(
    paths: StandaloneAgentPaths,
    event: PlanningAgentEvent,
    thread_id: str,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CoursePlanningAgentResult:
    agent = build_standalone_course_planning_agent(paths, checkpointer=checkpointer)
    return agent.invoke(event, thread_id=thread_id)
