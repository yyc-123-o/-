from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillforge_kb.agents.planning_agent_models import (
    CoursePlanningAgentResult,
    PlanningAgentStatus,
    PlanningNextAction,
)
from skillforge_kb.agents.retrieval_agent_models import (
    DomainRetrievalRequest,
    DomainRetrievalResult,
    EvidenceGap,
    EvidenceSummary,
    RetrievalMethod,
    RetrievedEvidence,
)
from skillforge_kb.domain.enums import LicenseStatus
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.evidence.models import EvidenceReviewStatus
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.ontology.resource_blueprints import load_resource_blueprints
from skillforge_kb.planning.adaptation import NodeWeightEngine
from skillforge_kb.planning.models import PathStatus
from skillforge_kb.planning.planner import CoursePlanner
from skillforge_kb.resources.briefs import ResourceBriefBuilder


@pytest.fixture
def profile() -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="PROFILE-2026-0001-DEMO",
        learner_ref="0" * 64,
        graph_version="ai-course-v1",
        generated_at=datetime(2026, 8, 16, tzinfo=UTC),
    )


@pytest.fixture
def platform_case(profile: LearnerProfileSnapshot) -> dict[str, object]:
    root = Path(__file__).parents[3]
    ontology_root = root / "resources" / "ontology"
    catalog = OntologyCatalog.load(
        ontology_root / "ai_course_v1.yaml",
        ontology_root / "ai_relations_v1.yaml",
    )
    attributes = load_concept_attributes(
        catalog,
        ontology_root / "concept_attributes_v1.yaml",
    )
    blueprints = load_resource_blueprints(
        catalog,
        ontology_root / "resource_blueprints_v1.yaml",
    )
    decision = CoursePlanner(catalog).plan(profile)
    engine = NodeWeightEngine(catalog, attributes)
    unfinished = tuple(
        node
        for node in decision.nodes
        if node.status not in {PathStatus.COMPLETED, PathStatus.SKIPPED}
    )
    adaptations = tuple(engine.evaluate(profile, node) for node in unfinished)
    current = next(node for node in decision.nodes if node.status is PathStatus.AVAILABLE)
    current_adaptation = next(
        item for item in adaptations if item.concept_id == current.concept_id
    )
    evidence_index = EvidenceIndex(
        version="evidence-manifest-v1",
        graph_version=catalog.course_document.version,
    )
    handoff = ResourceBriefBuilder(
        catalog=catalog,
        blueprints=blueprints,
        adaptations=adaptations,
        evidence_index=evidence_index,
    ).build_handoff(decision, profile, current.concept_id)
    planning = CoursePlanningAgentResult(
        thread_id="fixture-thread",
        status=PlanningAgentStatus.READY,
        next_action=PlanningNextAction.START_CURRENT_NODE,
        path=decision,
        current_node=current,
        current_adaptation=current_adaptation,
        adaptations=adaptations,
    )
    request = DomainRetrievalRequest(
        original_query=current.concept_id,
        rewritten_queries=(current.concept_id,),
        profile_id=profile.profile_id,
        concept_id=current.concept_id,
        depth=current.delivery_depth,
        top_k=5,
    )
    candidates = tuple(
        RetrievedEvidence(
            evidence_key=f"candidate-{kind.value}",
            chunk_id=f"chunk-{kind.value}",
            source_id="source-platform",
            source_title="Platform candidate fixture",
            heading_path=(kind.value,),
            excerpt=f"Evidence text for {kind.value} and {current.concept_id}.",
            locator=f"section:{kind.value}",
            score=1.0,
            retrieval_method=RetrievalMethod.BM25,
            concept_id=current.concept_id,
            depth=current.delivery_depth,
            content_kind=kind,
            review_status=EvidenceReviewStatus.CANDIDATE,
            license_status=LicenseStatus.PENDING,
            evidence_status="candidate",
        )
        for kind in handoff.evidence_filters.content_kinds
    )
    missing = handoff.evidence_filters.content_kinds
    retrieval = DomainRetrievalResult(
        request=request,
        candidate_evidence=candidates,
        concept_evidence={current.concept_id: tuple(item.evidence_key for item in candidates)},
        evidence_summary=EvidenceSummary(
            candidate_count=len(candidates),
            available_content_kinds=missing,
            missing_content_kinds=missing,
        ),
        evidence_gap=EvidenceGap(
            missing_content_kinds=missing,
            message="published evidence is missing",
        ),
    )
    return {
        "catalog": catalog,
        "blueprints": blueprints,
        "evidence_index": evidence_index,
        "planning": planning,
        "handoff": handoff,
        "retrieval": retrieval,
    }
