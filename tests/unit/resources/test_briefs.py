from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillforge_kb.domain.enums import ContentKind, Language, LicenseStatus
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.evidence.models import (
    EvidenceRecord,
    EvidenceReviewStatus,
    build_evidence_id,
)
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import (
    AbilityScore,
    AssessmentStatus,
    DepthLevel,
    KnowledgeMastery,
    LearnerProfileSnapshot,
)
from skillforge_kb.ontology.resource_blueprints import (
    load_resource_blueprints,
    resource_blueprint,
)
from skillforge_kb.planning.adaptation import NodeWeightEngine
from skillforge_kb.planning.models import PathStatus
from skillforge_kb.planning.planner import CoursePlanner
from skillforge_kb.resources.allocation import build_resource_allocation_digest
from skillforge_kb.resources.briefs import ResourceBriefBuilder
from skillforge_kb.resources.models import ResourceBrief, build_brief_id

ABILITY_IDS = (
    "theoretical_understanding",
    "coding_ability",
    "mathematical_foundation",
    "problem_solving",
)


def _profile(
    catalog,
    *,
    profile_id: str = "profile-resource-test",
    concept_id: str = "math.linear-algebra.scalar",
    mastery: float | None = None,
    ability: float = 0.50,
) -> LearnerProfileSnapshot:
    mastery_records = []
    if mastery is not None:
        mastery_records.append(
            KnowledgeMastery(
                concept_id=concept_id,
                mastery_score=mastery,
                assessment_status=AssessmentStatus.ASSESSED,
                confidence=0.90,
                observed_at=datetime(2026, 7, 29, tzinfo=UTC),
                evidence_refs=["assessment-1"],
            )
        )
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id=profile_id,
        learner_ref="0" * 64,
        graph_version=catalog.course_document.version,
        generated_at=datetime(2026, 7, 29, tzinfo=UTC),
        abilities={
            dimension: AbilityScore(
                score=ability,
                confidence=0.90,
                assessment_run_id="assessment-1",
            )
            for dimension in ABILITY_IDS
        },
        knowledge_mastery=mastery_records,
    )


def _evidence_index(catalog, concept_id: str, depth) -> EvidenceIndex:
    records = []
    for index, kind in enumerate(
        (ContentKind.DEFINITION, ContentKind.CODE, ContentKind.EXERCISE),
        start=1,
    ):
        source_id = f"source-{index}"
        chunk_id = f"chunk-{index}"
        locator = f"section {index}"
        normalized_hash = f"{index + 10:064x}"
        records.append(
            EvidenceRecord(
                evidence_id=build_evidence_id(
                    graph_version=catalog.course_document.version,
                    source_id=source_id,
                    chunk_id=chunk_id,
                    concept_id=concept_id,
                    depth=depth,
                    locator=locator,
                    normalized_hash=normalized_hash,
                    language=Language.EN,
                    content_kind=kind,
                ),
                graph_version=catalog.course_document.version,
                source_id=source_id,
                chunk_id=chunk_id,
                concept_id=concept_id,
                depth=depth,
                source_url=f"https://example.edu/source-{index}",
                locator=locator,
                normalized_hash=normalized_hash,
                language=Language.EN,
                content_kind=kind,
                difficulty=1,
                license_status=LicenseStatus.ALLOWED,
                review_status=EvidenceReviewStatus.PUBLISHED,
                reviewed_by="reviewer-1",
                reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
            )
        )
    return EvidenceIndex(
        version="evidence-manifest-v1",
        graph_version=catalog.course_document.version,
        records=tuple(records),
    )


def _builder(catalog, profile, concept_id: str | None = None):
    root = Path(__file__).parents[3] / "resources" / "ontology"
    attributes = load_concept_attributes(catalog, root / "concept_attributes_v1.yaml")
    blueprints = load_resource_blueprints(catalog, root / "resource_blueprints_v1.yaml")
    decision = CoursePlanner(catalog).plan(profile)
    node = next(
        item
        for item in decision.nodes
        if item.concept_id == concept_id
        or (concept_id is None and item.status is PathStatus.AVAILABLE)
    )
    adaptation = NodeWeightEngine(catalog, attributes).evaluate(profile, node)
    evidence = _evidence_index(catalog, node.concept_id, node.delivery_depth)
    return (
        ResourceBriefBuilder(
            catalog=catalog,
            blueprints=blueprints,
            adaptations={node.concept_id: adaptation},
            evidence_index=evidence,
        ),
        decision,
        node,
    )


def test_build_is_deterministic_and_preserves_path_facts(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)

    first = builder.build(decision, profile, node.concept_id)
    second = builder.build(decision, profile, node.concept_id)

    assert first == second
    assert first.brief_id == second.brief_id
    assert first.path_id == decision.path_id
    assert first.sequence == node.sequence
    assert first.delivery_depth is node.delivery_depth
    assert first.concept_id == node.concept_id
    assert first.chapter_id == node.chapter_id
    assert first.section_id == node.section_id
    assert first.citation_requirements.min_evidence_records >= 1
    assert first.node_adaptation.resource_mode is first.node_adaptation.support_intensity
    assert first.request_version == "resource-brief.v2"
    allocation = first.resource_allocation
    blueprint = resource_blueprint(
        builder.blueprints,
        node.concept_id,
        node.delivery_depth,
    )
    assert allocation.concept_id == first.concept_id
    assert allocation.delivery_depth is first.delivery_depth
    assert allocation.support_intensity is first.node_adaptation.support_intensity
    assert allocation.resource_types == first.required_resource_types
    assert allocation.blueprint_estimated_minutes == blueprint.estimated_minutes
    assert allocation.effort_multiplier == first.node_adaptation.effort_multiplier
    assert allocation.estimated_minutes >= blueprint.estimated_minutes


def test_brief_is_frozen_and_rejects_path_field_override(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)
    brief = builder.build(decision, profile, node.concept_id)

    with pytest.raises(ValidationError):
        brief.path_id = "path_" + "0" * 64


def test_brief_rejects_internally_inconsistent_filters(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)
    brief = builder.build(decision, profile, node.concept_id)
    payload = brief.model_dump(mode="json")
    payload["evidence_filters"]["concept_id"] = "math.linear-algebra.vector"
    payload["brief_id"] = build_brief_id(
        {key: value for key, value in payload.items() if key != "brief_id"}
    )

    with pytest.raises(ValidationError, match="evidence filters"):
        ResourceBrief.model_validate(payload)


def test_brief_rejects_allocation_from_another_concept(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)
    brief = builder.build(decision, profile, node.concept_id)
    payload = brief.model_dump(mode="json")
    allocation = payload["resource_allocation"]
    allocation["concept_id"] = "math.linear-algebra.vector"
    allocation["allocation_digest"] = build_resource_allocation_digest(
        {
            key: value
            for key, value in allocation.items()
            if key != "allocation_digest"
        }
    )
    payload["brief_id"] = build_brief_id(
        {key: value for key, value in payload.items() if key != "brief_id"}
    )

    with pytest.raises(ValidationError, match="allocation concept"):
        ResourceBrief.model_validate(payload)


def test_nonblocked_brief_rejects_blocking_prerequisites(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)
    brief = builder.build(decision, profile, node.concept_id)
    payload = brief.model_dump(mode="json")
    payload["blocking_prerequisite_ids"] = ("math.linear-algebra.vector",)
    payload["hard_prerequisite_ids"] = ("math.linear-algebra.vector",)
    payload["brief_id"] = build_brief_id(
        {key: value for key, value in payload.items() if key != "brief_id"}
    )

    with pytest.raises(ValidationError, match="non-blocked"):
        ResourceBrief.model_validate(payload)


def test_skipped_and_completed_nodes_cannot_generate_briefs(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)

    skipped = decision.nodes[0].model_copy(
        update={"status": PathStatus.SKIPPED, "delivery_depth": None}
    )
    skipped_decision = decision.model_copy(update={"nodes": (skipped, *decision.nodes[1:])})
    with pytest.raises(ValueError, match="skipped"):
        builder.build(skipped_decision, profile, node.concept_id)

    completed = node.model_copy(update={"status": PathStatus.COMPLETED})
    completed_decision = decision.model_copy(
        update={"nodes": (completed, *decision.nodes[1:])}
    )
    with pytest.raises(ValueError, match="completed"):
        builder.build(completed_decision, profile, node.concept_id)


def test_missing_published_evidence_is_structured_failure(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)
    builder = builder.model_copy(update={"evidence_index": EvidenceIndex(
        version="evidence-manifest-v1",
        graph_version=catalog.course_document.version,
        records=(),
    )})

    with pytest.raises(ValueError, match="published evidence"):
        builder.build(decision, profile, node.concept_id)


def test_mismatched_profile_or_adaptation_is_rejected(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)
    other_profile = _profile(catalog, profile_id="profile-other")

    with pytest.raises(ValueError, match="profile"):
        builder.build(decision, other_profile, node.concept_id)

    changed_profile = _profile(catalog, ability=0.90)
    with pytest.raises(ValueError, match="adaptation profile"):
        builder.build(decision, changed_profile, node.concept_id)

    invalid_index = builder.evidence_index.model_copy(
        update={"graph_version": "ai-course-v2"}
    )
    invalid_builder = builder.model_copy(update={"evidence_index": invalid_index})
    with pytest.raises(ValueError, match="evidence graph version"):
        invalid_builder.build(decision, profile, node.concept_id)


def test_path_node_structure_must_match_catalog(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)

    wrong_position = node.model_copy(update={"chapter_id": "chapter.99.invalid"})
    wrong_position_decision = decision.model_copy(
        update={
            "nodes": tuple(
                wrong_position if item.concept_id == node.concept_id else item
                for item in decision.nodes
            )
        }
    )
    with pytest.raises(ValueError, match="catalog position"):
        builder.build(wrong_position_decision, profile, node.concept_id)

    wrong_prerequisites = node.model_copy(
        update={"hard_prerequisite_ids": ("math.linear-algebra.vector",)}
    )
    wrong_prerequisites_decision = decision.model_copy(
        update={
            "nodes": tuple(
                wrong_prerequisites if item.concept_id == node.concept_id else item
                for item in decision.nodes
            )
        }
    )
    with pytest.raises(ValueError, match="hard prerequisites"):
        builder.build(wrong_prerequisites_decision, profile, node.concept_id)


def test_path_id_must_match_structural_path_content(catalog) -> None:
    profile = _profile(catalog)
    builder, decision, node = _builder(catalog, profile)
    invalid = decision.model_copy(update={"path_id": "path_" + "0" * 64})

    with pytest.raises(ValueError, match="path ID"):
        builder.build(invalid, profile, node.concept_id)


@pytest.mark.parametrize(
    ("mastery", "ability", "expected_depth"),
    [
        (None, 0.50, DepthLevel.INTRO),
        (0.60, 0.80, DepthLevel.INTERMEDIATE),
        (0.84, 0.90, DepthLevel.ADVANCED),
    ],
)
def test_brief_uses_the_path_depth_blueprint(
    catalog,
    mastery: float | None,
    ability: float,
    expected_depth: DepthLevel,
) -> None:
    profile = _profile(catalog, mastery=mastery, ability=ability)
    builder, decision, node = _builder(catalog, profile)

    brief = builder.build(decision, profile, node.concept_id)

    assert brief.delivery_depth is expected_depth
    assert brief.evidence_filters.depth is expected_depth
    expected_level = next(
        level
        for level in catalog.get_concept(node.concept_id).levels
        if level.level is expected_depth
    )
    assert brief.learning_outcomes == tuple(expected_level.learning_outcomes)


def test_blocked_brief_preserves_intro_remediation_and_blockers(catalog) -> None:
    concept_id = "math.linear-algebra.vector"
    profile = _profile(
        catalog,
        concept_id=concept_id,
        mastery=0.84,
        ability=0.90,
    )
    builder, decision, node = _builder(catalog, profile, concept_id)

    brief = builder.build(decision, profile, concept_id)

    assert brief.status is PathStatus.BLOCKED
    assert brief.delivery_depth is DepthLevel.INTRO
    assert brief.node_adaptation.resource_mode.value == "remediation"
    assert brief.blocking_prerequisite_ids == ("math.linear-algebra.scalar",)


def test_project_blueprint_requires_code_and_exercise_evidence(catalog) -> None:
    profile = _profile(catalog, mastery=0.60, ability=0.80)
    builder, decision, node = _builder(catalog, profile)
    incomplete_index = builder.evidence_index.model_copy(
        update={
            "records": tuple(
                record
                for record in builder.evidence_index.records
                if record.content_kind is not ContentKind.EXERCISE
            )
        }
    )
    builder = builder.model_copy(update={"evidence_index": incomplete_index})

    with pytest.raises(ValueError, match="published evidence.*exercise"):
        builder.build(decision, profile, node.concept_id)
