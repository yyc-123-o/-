from datetime import UTC, datetime

import pytest

from skillforge_kb.ontology.models import (
    AbilityScore,
    AssessmentStatus,
    DepthLevel,
    KnowledgeMastery,
    LearnerProfileSnapshot,
    RelationKind,
)
from skillforge_kb.planning import CoursePlanner, PathStatus

ABILITY_IDS = (
    "theoretical_understanding",
    "coding_ability",
    "mathematical_foundation",
    "problem_solving",
)


def _profile(
    catalog,
    *,
    profile_id: str,
    default_mastery: float | None,
    ability: float | None,
    skipped_ids: set[str] | None = None,
) -> LearnerProfileSnapshot:
    skipped = skipped_ids or set()
    mastery = []
    if default_mastery is not None:
        mastery = [
            KnowledgeMastery(
                concept_id=concept.id,
                mastery_score=0.90 if concept.id in skipped else default_mastery,
                assessment_status=AssessmentStatus.ASSESSED,
                confidence=0.90,
                observed_at=datetime(2026, 7, 28, tzinfo=UTC),
                evidence_refs=[f"assessment-{profile_id}"],
            )
            for concept in catalog.concepts()
        ]
    abilities = {}
    if ability is not None:
        abilities = {
            dimension: AbilityScore(
                score=ability,
                confidence=0.90,
                assessment_run_id=f"assessment-{profile_id}",
            )
            for dimension in ABILITY_IDS
        }
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id=profile_id,
        learner_ref="2" * 64,
        graph_version=catalog.course_document.version,
        generated_at=datetime(2026, 7, 28, tzinfo=UTC),
        knowledge_mastery=mastery,
        abilities=abilities,
    )


def zero_profile(catalog) -> LearnerProfileSnapshot:
    return _profile(
        catalog,
        profile_id="zero",
        default_mastery=None,
        ability=None,
    )


def intermediate_profile(catalog) -> LearnerProfileSnapshot:
    return _profile(
        catalog,
        profile_id="intermediate",
        default_mastery=0.80,
        ability=0.70,
        skipped_ids={"math.linear-algebra.scalar"},
    )


def advanced_profile(catalog) -> LearnerProfileSnapshot:
    return _profile(
        catalog,
        profile_id="advanced",
        default_mastery=0.84,
        ability=0.90,
    )


@pytest.mark.parametrize(
    "profile_factory",
    [zero_profile, intermediate_profile, advanced_profile],
)
def test_every_profile_covers_all_required_concepts(catalog, profile_factory) -> None:
    decision = CoursePlanner(catalog).plan(profile_factory(catalog))
    required = {item.id for item in catalog.concepts() if item.required}

    assert {node.concept_id for node in decision.nodes} == required


def test_zero_profile_uses_only_intro_depth(catalog) -> None:
    decision = CoursePlanner(catalog).plan(zero_profile(catalog))

    assert {node.delivery_depth for node in decision.nodes} == {DepthLevel.INTRO}


def test_intermediate_profile_keeps_mastered_nodes_as_skipped(catalog) -> None:
    decision = CoursePlanner(catalog).plan(intermediate_profile(catalog))
    scalar = next(
        node for node in decision.nodes if node.concept_id == "math.linear-algebra.scalar"
    )

    assert scalar.status is PathStatus.SKIPPED
    assert scalar.delivery_depth is None
    assert any(node.delivery_depth is DepthLevel.INTERMEDIATE for node in decision.nodes)


def test_advanced_profile_can_reach_advanced_without_order_violations(catalog) -> None:
    decision = CoursePlanner(catalog).plan(advanced_profile(catalog))
    index = {node.concept_id: node.sequence for node in decision.nodes}

    assert all(node.delivery_depth is DepthLevel.ADVANCED for node in decision.nodes)
    for relation in catalog.relations(RelationKind.HARD_PREREQUISITE):
        if relation.source in index and relation.target in index:
            assert index[relation.source] < index[relation.target]
