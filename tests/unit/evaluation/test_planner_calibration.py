import pytest
from pydantic import ValidationError

from skillforge_kb.evaluation import (
    PlannerPolicyCoordinate,
    PlannerPolicySearchSpace,
    build_planner_search_space_digest,
    default_planner_policy_search_space,
    generate_planner_policy_candidates,
)
from skillforge_kb.planning import AbilityWeights, PlannerPolicy


def test_default_candidates_are_deterministic_legal_and_complete() -> None:
    baseline = PlannerPolicy()
    space = default_planner_policy_search_space(baseline)

    first = generate_planner_policy_candidates(space, baseline)
    second = generate_planner_policy_candidates(space, baseline)

    assert first == second
    assert {item.changed_coordinate for item in first} == set(PlannerPolicyCoordinate)
    assert all(_tunable_values(item.policy) != _tunable_values(baseline) for item in first)
    assert len({_tunable_values(item.policy) for item in first}) == len(first)
    assert all(
        item.policy.intermediate_threshold < item.policy.advanced_threshold
        for item in first
    )
    assert all(
        sum(item.policy.ability_weights.values()) == pytest.approx(1.0)
        for item in first
    )


def test_each_candidate_changes_exactly_one_coordinate_group() -> None:
    baseline = PlannerPolicy()
    candidates = generate_planner_policy_candidates(
        default_planner_policy_search_space(baseline),
        baseline,
    )

    for candidate in candidates:
        assert _changed_coordinates(baseline, candidate.policy) == {
            candidate.changed_coordinate
        }
        assert candidate.baseline_values != candidate.candidate_values


def test_numeric_search_axes_must_be_strictly_increasing() -> None:
    baseline = default_planner_policy_search_space(PlannerPolicy())

    with pytest.raises(ValidationError, match="minimum_confidences"):
        PlannerPolicySearchSpace.model_validate(
            {
                **baseline.model_dump(),
                "minimum_confidences": (0.60, 0.60),
            }
        )


def test_ability_weight_options_must_be_unique() -> None:
    baseline = default_planner_policy_search_space(PlannerPolicy())
    duplicate = AbilityWeights()

    with pytest.raises(ValidationError, match="ability weight options"):
        PlannerPolicySearchSpace.model_validate(
            {
                **baseline.model_dump(),
                "ability_weight_options": (duplicate, duplicate),
            }
        )


def test_generation_rejects_a_space_without_an_alternative() -> None:
    policy = PlannerPolicy()
    space = PlannerPolicySearchSpace(
        minimum_confidences=(policy.minimum_confidence,),
        skip_masteries=(policy.skip_mastery,),
        skip_confidences=(policy.skip_confidence,),
        mastery_weights=(policy.mastery_weight,),
        intermediate_thresholds=(policy.intermediate_threshold,),
        advanced_thresholds=(policy.advanced_threshold,),
        ability_weight_options=(policy.ability_weights,),
    )

    with pytest.raises(ValueError, match="no alternative"):
        generate_planner_policy_candidates(space, policy)


def test_search_space_digest_is_stable_and_content_sensitive() -> None:
    first = default_planner_policy_search_space(PlannerPolicy())
    same = PlannerPolicySearchSpace.model_validate(first.model_dump())
    changed = first.model_copy(
        update={"minimum_confidences": (*first.minimum_confidences, 0.70)}
    )

    assert build_planner_search_space_digest(first) == build_planner_search_space_digest(same)
    assert build_planner_search_space_digest(first) != build_planner_search_space_digest(changed)


def _tunable_values(policy: PlannerPolicy) -> tuple[float, ...]:
    return (
        policy.minimum_confidence,
        policy.skip_mastery,
        policy.skip_confidence,
        policy.mastery_weight,
        policy.ability_weight,
        policy.intermediate_threshold,
        policy.advanced_threshold,
        *policy.ability_weights.values(),
    )


def _changed_coordinates(
    baseline: PlannerPolicy,
    candidate: PlannerPolicy,
) -> set[PlannerPolicyCoordinate]:
    changed: set[PlannerPolicyCoordinate] = set()
    if baseline.minimum_confidence != candidate.minimum_confidence:
        changed.add(PlannerPolicyCoordinate.MINIMUM_CONFIDENCE)
    if baseline.skip_mastery != candidate.skip_mastery:
        changed.add(PlannerPolicyCoordinate.SKIP_MASTERY)
    if baseline.skip_confidence != candidate.skip_confidence:
        changed.add(PlannerPolicyCoordinate.SKIP_CONFIDENCE)
    if (
        baseline.mastery_weight != candidate.mastery_weight
        or baseline.ability_weight != candidate.ability_weight
    ):
        changed.add(PlannerPolicyCoordinate.READINESS_WEIGHTS)
    if baseline.intermediate_threshold != candidate.intermediate_threshold:
        changed.add(PlannerPolicyCoordinate.INTERMEDIATE_THRESHOLD)
    if baseline.advanced_threshold != candidate.advanced_threshold:
        changed.add(PlannerPolicyCoordinate.ADVANCED_THRESHOLD)
    if baseline.ability_weights != candidate.ability_weights:
        changed.add(PlannerPolicyCoordinate.ABILITY_WEIGHTS)
    return changed
