from datetime import UTC, datetime

import pytest

from skillforge_kb.ontology.models import (
    AbilityScore,
    AssessmentStatus,
    DepthLevel,
    KnowledgeMastery,
    LearnerProfileSnapshot,
    LearningPreferences,
)
from skillforge_kb.planning.models import PathDecision, PathStatus, ReasonCode
from skillforge_kb.planning.ordering import PlanningError
from skillforge_kb.planning.planner import CoursePlanner

ABILITY_IDS = (
    "theoretical_understanding",
    "coding_ability",
    "mathematical_foundation",
    "problem_solving",
)


def make_profile(
    catalog,
    *,
    profile_id: str = "profile-test",
    mastery: list[KnowledgeMastery] | None = None,
    ability: float | None = None,
    ability_confidence: float = 0.90,
    graph_version: str | None = None,
) -> LearnerProfileSnapshot:
    abilities = {}
    if ability is not None:
        abilities = {
            dimension: AbilityScore(
                score=ability,
                confidence=ability_confidence,
                assessment_run_id="assessment-1",
            )
            for dimension in ABILITY_IDS
        }
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id=profile_id,
        learner_ref="0" * 64,
        graph_version=graph_version or catalog.course_document.version,
        generated_at=datetime(2026, 7, 28, tzinfo=UTC),
        knowledge_mastery=mastery or [],
        abilities=abilities,
    )


def assessed(
    concept_id: str,
    mastery: float,
    confidence: float = 0.90,
) -> KnowledgeMastery:
    return KnowledgeMastery(
        concept_id=concept_id,
        mastery_score=mastery,
        assessment_status=AssessmentStatus.ASSESSED,
        confidence=confidence,
        observed_at=datetime(2026, 7, 28, tzinfo=UTC),
        evidence_refs=["assessment-1"],
    )


def node_for(decision: PathDecision, concept_id: str):
    return next(node for node in decision.nodes if node.concept_id == concept_id)


def test_zero_data_profile_gets_complete_conservative_path(catalog) -> None:
    decision = CoursePlanner(catalog).plan(make_profile(catalog))
    required_count = sum(item.required for item in catalog.concepts())

    assert len(decision.nodes) == required_count
    assert all(
        node.delivery_depth is None or node.delivery_depth is DepthLevel.INTRO
        for node in decision.nodes
    )
    assert sum(node.status is PathStatus.AVAILABLE for node in decision.nodes) == 1


def test_recommendations_are_ranked_and_prerequisite_safe(catalog) -> None:
    decision = CoursePlanner(catalog).plan(make_profile(catalog))

    assert 1 <= len(decision.recommendations) <= 5
    assert [item.rank for item in decision.recommendations] == list(
        range(1, len(decision.recommendations) + 1)
    )
    node_by_id = {node.concept_id: node for node in decision.nodes}
    assert all(
        node_by_id[item.concept_id].status
        not in {PathStatus.BLOCKED, PathStatus.COMPLETED, PathStatus.SKIPPED}
        for item in decision.recommendations
    )
    assert "prerequisite_ready" in decision.recommendations[0].reason_codes


def test_recommendation_budget_keeps_a_minimum_actionable_queue(catalog) -> None:
    profile = make_profile(catalog).model_copy(
        update={"preferences": LearningPreferences(pace_hours_per_week=0.5)}
    )

    decision = CoursePlanner(catalog).plan(profile)

    assert len(decision.recommendations) >= min(3, len(decision.nodes))


def test_planned_node_exposes_chinese_concept_title(catalog) -> None:
    decision = CoursePlanner(catalog).plan(make_profile(catalog))

    node = node_for(decision, "math.linear-algebra.scalar")

    assert node.title == catalog.get_concept(node.concept_id).names.zh


def test_high_confidence_mastery_keeps_node_as_skipped(catalog) -> None:
    profile = make_profile(
        catalog,
        mastery=[assessed("math.linear-algebra.scalar", 0.90)],
        ability=0.90,
    )

    node = node_for(
        CoursePlanner(catalog).plan(profile),
        "math.linear-algebra.scalar",
    )

    assert node.status is PathStatus.SKIPPED
    assert node.delivery_depth is None
    assert node.reason_codes == (ReasonCode.MASTERY_SKIP_THRESHOLD_MET,)


def test_mastered_prerequisite_unlocks_successor(catalog) -> None:
    profile = make_profile(
        catalog,
        mastery=[assessed("math.linear-algebra.scalar", 0.90)],
        ability=0.90,
    )

    decision = CoursePlanner(catalog).plan(profile)

    scalar = node_for(decision, "math.linear-algebra.scalar")
    vector = node_for(decision, "math.linear-algebra.vector")
    assert scalar.status is PathStatus.SKIPPED
    assert vector.status is PathStatus.AVAILABLE
    assert vector.blocking_prerequisite_ids == ()


def test_complete_high_readiness_can_select_advanced(catalog) -> None:
    profile = make_profile(
        catalog,
        mastery=[assessed("math.linear-algebra.scalar", 0.84)],
        ability=0.90,
    )

    node = node_for(
        CoursePlanner(catalog).plan(profile),
        "math.linear-algebra.scalar",
    )

    assert node.delivery_depth is DepthLevel.ADVANCED
    assert node.reason_codes == (ReasonCode.READY_FOR_ADVANCED,)


def test_unassessed_hard_prerequisite_blocks_advanced_depth(catalog) -> None:
    profile = make_profile(
        catalog,
        mastery=[assessed("math.linear-algebra.vector", 0.84)],
        ability=0.90,
    )

    node = node_for(
        CoursePlanner(catalog).plan(profile),
        "math.linear-algebra.vector",
    )

    assert node.status is PathStatus.BLOCKED
    assert node.delivery_depth is DepthLevel.INTRO
    assert node.blocking_prerequisite_ids == ("math.linear-algebra.scalar",)
    assert ReasonCode.HARD_PREREQUISITE_UNASSESSED in node.reason_codes


def test_missing_ability_caps_depth_at_intro(catalog) -> None:
    profile = make_profile(
        catalog,
        mastery=[assessed("math.linear-algebra.scalar", 0.84)],
    )

    node = node_for(
        CoursePlanner(catalog).plan(profile),
        "math.linear-algebra.scalar",
    )

    assert node.delivery_depth is DepthLevel.INTRO
    assert ReasonCode.ABILITY_INCOMPLETE in node.reason_codes


def test_planning_rejects_profile_graph_version_mismatch(catalog) -> None:
    profile = make_profile(catalog, graph_version="ai-course-v2")

    with pytest.raises(PlanningError, match="profile graph version"):
        CoursePlanner(catalog).plan(profile)


def test_planning_rejects_duplicate_mastery_records(catalog) -> None:
    profile = make_profile(
        catalog,
        mastery=[
            assessed("math.linear-algebra.scalar", 0.50),
            assessed("math.linear-algebra.scalar", 0.60),
        ],
    )

    with pytest.raises(PlanningError, match="duplicate mastery concept"):
        CoursePlanner(catalog).plan(profile)


def test_repeated_planning_is_semantically_identical(catalog) -> None:
    profile = make_profile(catalog)
    planner = CoursePlanner(catalog)

    assert planner.plan(profile) == planner.plan(profile)


def test_targeted_planning_keeps_complete_path_and_marks_focus(catalog) -> None:
    profile = make_profile(
        catalog,
        mastery=[
            assessed("math.linear-algebra.scalar", 0.95),
            assessed("math.linear-algebra.vector", 0.95),
            assessed("math.linear-algebra.matrix", 0.95),
            assessed("math.linear-algebra.tensor", 0.95),
            assessed("math.linear-algebra.matrix-operations", 0.95),
            assessed("math.calculus.derivative-gradient", 0.95),
            assessed("dl.feedforward.mlp", 0.95),
            assessed("dl.vision.image-tensor", 0.95),
        ],
        ability=0.90,
    )

    decision = CoursePlanner(catalog).plan(
        profile,
        target_concept_id="dl.cnn.convolution",
    )

    concept_ids = {node.concept_id for node in decision.nodes}
    assert decision.target_concept_id == "dl.cnn.convolution"
    assert "dl.cnn.convolution" in concept_ids
    assert "dl.vision.image-tensor" in concept_ids
    assert len(decision.nodes) == len(CoursePlanner(catalog).plan(profile).nodes)
    assert "nlp.rnn" in concept_ids


def test_targeted_planning_rejects_unknown_concept(catalog) -> None:
    with pytest.raises(PlanningError, match="unknown target concept"):
        CoursePlanner(catalog).plan(
            make_profile(catalog),
            target_concept_id="nonexistent.concept",
        )
