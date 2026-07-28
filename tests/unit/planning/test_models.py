import pytest
from pydantic import ValidationError

from skillforge_kb.ontology.models import DepthLevel
from skillforge_kb.planning.models import PathNode, PathStatus, PlannerPolicy


def test_default_policy_uses_reviewed_v1_thresholds() -> None:
    policy = PlannerPolicy()

    assert policy.version == "planner-policy.v1"
    assert policy.minimum_confidence == 0.60
    assert policy.skip_mastery == 0.85
    assert policy.skip_confidence == 0.80
    assert sum(policy.ability_weights.values()) == pytest.approx(1.0)


def test_policy_rejects_invalid_weight_sums() -> None:
    with pytest.raises(ValidationError, match="ability weights must sum to 1"):
        PlannerPolicy(
            ability_weights={
                "theoretical_understanding": 0.30,
                "coding_ability": 0.30,
                "mathematical_foundation": 0.30,
                "problem_solving": 0.30,
            }
        )


def test_skipped_node_requires_null_depth() -> None:
    with pytest.raises(
        ValidationError, match="skipped nodes must not have a delivery depth"
    ):
        PathNode(
            concept_id="math.linear-algebra.vector",
            chapter_id="chapter.01.math-foundations",
            section_id="section.01.linear-algebra",
            sequence=1,
            status=PathStatus.SKIPPED,
            delivery_depth=DepthLevel.INTRO,
        )


def test_learning_node_requires_a_depth() -> None:
    with pytest.raises(
        ValidationError, match="learning nodes require a delivery depth"
    ):
        PathNode(
            concept_id="math.linear-algebra.vector",
            chapter_id="chapter.01.math-foundations",
            section_id="section.01.linear-algebra",
            sequence=1,
            status=PathStatus.PENDING,
            delivery_depth=None,
        )


def test_policy_ability_weights_are_deeply_immutable() -> None:
    policy = PlannerPolicy()

    with pytest.raises(ValidationError, match="Instance is frozen"):
        policy.ability_weights.coding_ability = 0.90
