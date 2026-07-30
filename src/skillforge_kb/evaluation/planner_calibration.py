import json
from enum import StrEnum
from hashlib import sha256
from itertools import pairwise
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from skillforge_kb.planning.models import AbilityWeights, PlannerPolicy
from skillforge_kb.planning.serialization import build_policy_digest

UnitFloat = Annotated[float, Field(ge=0, le=1)]


class PlannerPolicyCoordinate(StrEnum):
    MINIMUM_CONFIDENCE = "minimum_confidence"
    SKIP_MASTERY = "skip_mastery"
    SKIP_CONFIDENCE = "skip_confidence"
    READINESS_WEIGHTS = "readiness_weights"
    INTERMEDIATE_THRESHOLD = "intermediate_threshold"
    ADVANCED_THRESHOLD = "advanced_threshold"
    ABILITY_WEIGHTS = "ability_weights"


class PlannerPolicyCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: PlannerPolicy
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")
    changed_coordinate: PlannerPolicyCoordinate
    baseline_values: tuple[float, ...] = Field(min_length=1)
    candidate_values: tuple[float, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate(self) -> "PlannerPolicyCandidate":
        if self.policy_digest != build_policy_digest(self.policy):
            raise ValueError("planner candidate policy digest does not match policy")
        if self.baseline_values == self.candidate_values:
            raise ValueError("planner candidate coordinate must change")
        if len(self.baseline_values) != len(self.candidate_values):
            raise ValueError("planner candidate coordinate value shapes must match")
        return self


class PlannerPolicySearchSpace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version_prefix: str = Field(
        default="planner-policy.candidate.v1",
        min_length=1,
    )
    minimum_confidences: tuple[UnitFloat, ...] = Field(min_length=1)
    skip_masteries: tuple[UnitFloat, ...] = Field(min_length=1)
    skip_confidences: tuple[UnitFloat, ...] = Field(min_length=1)
    mastery_weights: tuple[UnitFloat, ...] = Field(min_length=1)
    intermediate_thresholds: tuple[UnitFloat, ...] = Field(min_length=1)
    advanced_thresholds: tuple[UnitFloat, ...] = Field(min_length=1)
    ability_weight_options: tuple[AbilityWeights, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_space(self) -> "PlannerPolicySearchSpace":
        axis_names = (
            "minimum_confidences",
            "skip_masteries",
            "skip_confidences",
            "mastery_weights",
            "intermediate_thresholds",
            "advanced_thresholds",
        )
        for axis_name in axis_names:
            values = getattr(self, axis_name)
            if any(left >= right for left, right in pairwise(values)):
                raise ValueError(f"{axis_name} must be strictly increasing")
        ability_values = [option.values() for option in self.ability_weight_options]
        if len(ability_values) != len(set(ability_values)):
            raise ValueError("ability weight options must be unique")
        return self


def default_planner_policy_search_space(
    baseline: PlannerPolicy,
) -> PlannerPolicySearchSpace:
    baseline = PlannerPolicy.model_validate(baseline.model_dump())
    ability_options = _unique_ability_weights(
        (
            baseline.ability_weights,
            AbilityWeights(
                theoretical_understanding=0.35,
                coding_ability=0.25,
                mathematical_foundation=0.20,
                problem_solving=0.20,
            ),
            AbilityWeights(
                theoretical_understanding=0.25,
                coding_ability=0.35,
                mathematical_foundation=0.20,
                problem_solving=0.20,
            ),
        )
    )
    return PlannerPolicySearchSpace(
        minimum_confidences=_local_axis(baseline.minimum_confidence),
        skip_masteries=_local_axis(baseline.skip_mastery),
        skip_confidences=_local_axis(baseline.skip_confidence),
        mastery_weights=_local_axis(baseline.mastery_weight),
        intermediate_thresholds=_local_axis(baseline.intermediate_threshold),
        advanced_thresholds=_local_axis(baseline.advanced_threshold),
        ability_weight_options=ability_options,
    )


def generate_planner_policy_candidates(
    search_space: PlannerPolicySearchSpace,
    baseline: PlannerPolicy,
) -> tuple[PlannerPolicyCandidate, ...]:
    search_space = PlannerPolicySearchSpace.model_validate(search_space.model_dump())
    baseline = PlannerPolicy.model_validate(baseline.model_dump())
    baseline_tunables = _tunable_values(baseline)
    candidates: list[PlannerPolicyCandidate] = []
    seen: set[tuple[float, ...]] = set()

    def add_candidate(
        coordinate: PlannerPolicyCoordinate,
        baseline_values: tuple[float, ...],
        candidate_values: tuple[float, ...],
        updates: dict[str, object],
    ) -> None:
        provisional_version = f"{search_space.policy_version_prefix}.provisional"
        try:
            provisional = PlannerPolicy.model_validate(
                {
                    **baseline.model_dump(),
                    **updates,
                    "version": provisional_version,
                }
            )
        except ValidationError:
            return
        tunables = _tunable_values(provisional)
        if tunables == baseline_tunables or tunables in seen:
            return
        seen.add(tunables)
        policy = provisional.model_copy(
            update={
                "version": (
                    f"{search_space.policy_version_prefix}.{len(candidates) + 1:04d}"
                )
            }
        )
        candidates.append(
            PlannerPolicyCandidate(
                policy=policy,
                policy_digest=build_policy_digest(policy),
                changed_coordinate=coordinate,
                baseline_values=baseline_values,
                candidate_values=candidate_values,
            )
        )

    direct_axes = (
        (
            PlannerPolicyCoordinate.MINIMUM_CONFIDENCE,
            "minimum_confidence",
            search_space.minimum_confidences,
        ),
        (
            PlannerPolicyCoordinate.SKIP_MASTERY,
            "skip_mastery",
            search_space.skip_masteries,
        ),
        (
            PlannerPolicyCoordinate.SKIP_CONFIDENCE,
            "skip_confidence",
            search_space.skip_confidences,
        ),
        (
            PlannerPolicyCoordinate.INTERMEDIATE_THRESHOLD,
            "intermediate_threshold",
            search_space.intermediate_thresholds,
        ),
        (
            PlannerPolicyCoordinate.ADVANCED_THRESHOLD,
            "advanced_threshold",
            search_space.advanced_thresholds,
        ),
    )
    for coordinate, field_name, values in direct_axes:
        baseline_value = float(getattr(baseline, field_name))
        for value in values:
            add_candidate(
                coordinate,
                (baseline_value,),
                (value,),
                {field_name: value},
            )

    for mastery_weight in search_space.mastery_weights:
        ability_weight = 1.0 - mastery_weight
        add_candidate(
            PlannerPolicyCoordinate.READINESS_WEIGHTS,
            (baseline.mastery_weight, baseline.ability_weight),
            (mastery_weight, ability_weight),
            {
                "mastery_weight": mastery_weight,
                "ability_weight": ability_weight,
            },
        )

    for ability_weights in search_space.ability_weight_options:
        add_candidate(
            PlannerPolicyCoordinate.ABILITY_WEIGHTS,
            baseline.ability_weights.values(),
            ability_weights.values(),
            {"ability_weights": ability_weights},
        )

    if not candidates:
        raise ValueError("planner policy search space contains no alternative")
    return tuple(candidates)


def build_planner_search_space_digest(search_space: PlannerPolicySearchSpace) -> str:
    canonical = json.dumps(
        search_space.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"planner_search_{sha256(canonical.encode('utf-8')).hexdigest()}"


def _local_axis(value: float) -> tuple[float, ...]:
    return tuple(sorted({_clamp(round(value + offset, 10)) for offset in (-0.05, 0.0, 0.05)}))


def _unique_ability_weights(
    values: tuple[AbilityWeights, ...],
) -> tuple[AbilityWeights, ...]:
    result: list[AbilityWeights] = []
    seen: set[tuple[float, ...]] = set()
    for value in values:
        key = value.values()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


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


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
