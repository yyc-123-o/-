from datetime import UTC, datetime

import pytest

from skillforge_kb.ontology.models import (
    AbilityScore,
    AssessmentStatus,
    DepthLevel,
    KnowledgeMastery,
    LearnerProfileSnapshot,
)
from skillforge_kb.planning.models import PathStatus
from skillforge_kb.planning.ordering import PlanningError
from skillforge_kb.planning.planner import CoursePlanner
from skillforge_kb.planning.updater import DepthUpdater

ABILITY_IDS = (
    "theoretical_understanding",
    "coding_ability",
    "mathematical_foundation",
    "problem_solving",
)


def profile(
    catalog,
    *,
    profile_id: str = "profile-update",
    scalar_mastery: float | None = None,
    vector_mastery: float | None = None,
    ability: float = 0.70,
) -> LearnerProfileSnapshot:
    mastery = []
    for concept_id, score in (
        ("math.linear-algebra.scalar", scalar_mastery),
        ("math.linear-algebra.vector", vector_mastery),
    ):
        if score is not None:
            mastery.append(
                KnowledgeMastery(
                    concept_id=concept_id,
                    mastery_score=score,
                    assessment_status=AssessmentStatus.ASSESSED,
                    confidence=0.90,
                    observed_at=datetime(2026, 7, 28, tzinfo=UTC),
                    evidence_refs=["assessment-update"],
                )
            )
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id=profile_id,
        learner_ref="1" * 64,
        graph_version=catalog.course_document.version,
        generated_at=datetime(2026, 7, 28, tzinfo=UTC),
        knowledge_mastery=mastery,
        abilities={
            dimension: AbilityScore(
                score=ability,
                confidence=0.90,
                assessment_run_id="assessment-update",
            )
            for dimension in ABILITY_IDS
        },
    )


def node_for(decision, concept_id: str):
    return next(node for node in decision.nodes if node.concept_id == concept_id)


def test_update_preserves_identity_order_and_completed_depth(catalog) -> None:
    existing = CoursePlanner(catalog).plan(
        profile(catalog, scalar_mastery=0.50, ability=0.70)
    )
    original_scalar = node_for(existing, "math.linear-algebra.scalar")

    updated = DepthUpdater(catalog).update(
        existing,
        profile(catalog, vector_mastery=0.84, ability=0.90),
        {"math.linear-algebra.scalar"},
    )

    assert updated.path_id == existing.path_id
    assert [node.concept_id for node in updated.nodes] == [
        node.concept_id for node in existing.nodes
    ]
    completed = node_for(updated, "math.linear-algebra.scalar")
    assert completed.status is PathStatus.COMPLETED
    assert completed.delivery_depth == original_scalar.delivery_depth


def test_completed_prerequisite_unblocks_high_readiness_successor(catalog) -> None:
    existing = CoursePlanner(catalog).plan(profile(catalog, scalar_mastery=0.50))

    updated = DepthUpdater(catalog).update(
        existing,
        profile(catalog, vector_mastery=0.84, ability=0.90),
        {"math.linear-algebra.scalar"},
    )

    vector = node_for(updated, "math.linear-algebra.vector")
    assert vector.blocking_prerequisite_ids == []
    assert vector.status is PathStatus.AVAILABLE
    assert vector.delivery_depth is DepthLevel.ADVANCED


def test_update_rejects_another_profile(catalog) -> None:
    existing = CoursePlanner(catalog).plan(profile(catalog))

    with pytest.raises(PlanningError, match="profile ID"):
        DepthUpdater(catalog).update(
            existing,
            profile(catalog, profile_id="another-profile"),
            set(),
        )


def test_update_rejects_unknown_completed_concept(catalog) -> None:
    existing = CoursePlanner(catalog).plan(profile(catalog))

    with pytest.raises(PlanningError, match="completed concept is not in path"):
        DepthUpdater(catalog).update(existing, profile(catalog), {"unknown.concept"})


def test_update_rejects_tampered_course_position(catalog) -> None:
    existing = CoursePlanner(catalog).plan(profile(catalog))
    first = existing.nodes[0].model_copy(update={"chapter_id": "chapter.99.tampered"})
    tampered = existing.model_copy(update={"nodes": [first, *existing.nodes[1:]]})

    with pytest.raises(PlanningError, match="path no longer matches catalog"):
        DepthUpdater(catalog).update(tampered, profile(catalog), set())


def test_update_does_not_create_new_skipped_nodes(catalog) -> None:
    existing = CoursePlanner(catalog).plan(profile(catalog, scalar_mastery=0.50))

    updated = DepthUpdater(catalog).update(
        existing,
        profile(catalog, scalar_mastery=0.95, ability=0.95),
        set(),
    )

    scalar = node_for(updated, "math.linear-algebra.scalar")
    assert scalar.status is not PathStatus.SKIPPED
    assert scalar.delivery_depth is DepthLevel.ADVANCED


def test_previous_completed_nodes_remain_prerequisite_evidence(catalog) -> None:
    existing = CoursePlanner(catalog).plan(profile(catalog, scalar_mastery=0.50))
    first_update = DepthUpdater(catalog).update(
        existing,
        profile(catalog, vector_mastery=0.84, ability=0.90),
        {"math.linear-algebra.scalar"},
    )

    second_update = DepthUpdater(catalog).update(
        first_update,
        profile(catalog, vector_mastery=0.84, ability=0.90),
        set(),
    )

    scalar = node_for(second_update, "math.linear-algebra.scalar")
    vector = node_for(second_update, "math.linear-algebra.vector")
    assert scalar.status is PathStatus.COMPLETED
    assert vector.blocking_prerequisite_ids == []
