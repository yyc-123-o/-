from datetime import UTC, datetime
from pathlib import Path

import pytest

from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.evidence.models import (
    EvidenceRecord,
    EvidenceReviewStatus,
    build_evidence_id,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import (
    AbilityScore,
    AssessmentStatus,
    KnowledgeMastery,
    LearnerProfileSnapshot,
)
from skillforge_kb.ontology.resource_blueprints import load_resource_blueprints
from skillforge_kb.planning.adaptation import NodeWeightEngine
from skillforge_kb.planning.models import PathStatus
from skillforge_kb.planning.planner import CoursePlanner
from skillforge_kb.resources.briefs import ResourceBriefBuilder
from skillforge_kb.resources.evidence_bundle import build_evidence_bundle


@pytest.fixture(scope="session")
def catalog() -> OntologyCatalog:
    root = Path(__file__).parents[3] / "resources" / "ontology"
    return OntologyCatalog.load(root / "ai_course_v1.yaml", root / "ai_relations_v1.yaml")


@pytest.fixture
def resource_case(catalog):
    profile = LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="profile-agent-test",
        learner_ref="0" * 64,
        graph_version=catalog.course_document.version,
        generated_at=datetime(2026, 7, 29, tzinfo=UTC),
        abilities={
            dimension: AbilityScore(
                score=0.80,
                confidence=0.90,
                assessment_run_id="assessment-1",
            )
            for dimension in (
                "theoretical_understanding",
                "coding_ability",
                "mathematical_foundation",
                "problem_solving",
            )
        },
        knowledge_mastery=[
            KnowledgeMastery(
                concept_id="math.linear-algebra.scalar",
                mastery_score=0.60,
                assessment_status=AssessmentStatus.ASSESSED,
                confidence=0.90,
                observed_at=datetime(2026, 7, 29, tzinfo=UTC),
                evidence_refs=["assessment-1"],
            )
        ],
    )
    root = Path(__file__).parents[3] / "resources" / "ontology"
    attributes = load_concept_attributes(catalog, root / "concept_attributes_v1.yaml")
    blueprints = load_resource_blueprints(catalog, root / "resource_blueprints_v1.yaml")
    decision = CoursePlanner(catalog).plan(profile)
    node = next(item for item in decision.nodes if item.status is PathStatus.AVAILABLE)
    adaptation = NodeWeightEngine(catalog, attributes).evaluate(profile, node)
    records = tuple(
        EvidenceRecord(
            evidence_id=build_evidence_id(
                graph_version=catalog.course_document.version,
                source_id=f"source-{index}",
                chunk_id=f"chunk-{index}",
                concept_id=node.concept_id,
                depth=node.delivery_depth,
                locator=f"section {index}",
                normalized_hash=f"{index + 10:064x}",
                language=Language.EN,
                content_kind=kind,
            ),
            graph_version=catalog.course_document.version,
            source_id=f"source-{index}",
            chunk_id=f"chunk-{index}",
            concept_id=node.concept_id,
            depth=node.delivery_depth,
            source_url=f"https://example.edu/source-{index}",
            locator=f"section {index}",
            normalized_hash=f"{index + 10:064x}",
            language=Language.EN,
            content_kind=kind,
            difficulty=1,
            license_status=LicenseStatus.ALLOWED,
            review_status=EvidenceReviewStatus.PUBLISHED,
            reviewed_by="reviewer-1",
            reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
        )
        for index, kind in enumerate(
            (ContentKind.DEFINITION, ContentKind.CODE, ContentKind.EXERCISE),
            start=1,
        )
    )
    evidence_index = EvidenceIndex(
        version="evidence-manifest-v1",
        graph_version=catalog.course_document.version,
        records=records,
    )
    builder = ResourceBriefBuilder(
        catalog=catalog,
        blueprints=blueprints,
        adaptations={node.concept_id: adaptation},
        evidence_index=evidence_index,
    )
    brief = builder.build(decision, profile, node.concept_id)
    return brief, build_evidence_bundle(brief, evidence_index)
