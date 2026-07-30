import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from itertools import pairwise
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.planning.models import AbilityWeights, PlannerPolicy
from skillforge_kb.planning.serialization import build_policy_digest

from .models import (
    SYNTHETIC_DISCLAIMER,
    PathEvaluationMetrics,
    SyntheticPlanningDataset,
    reconstruct_path_evaluation_metrics,
)
from .path_evaluation import evaluate_course_path_cases

UnitFloat = Annotated[float, Field(ge=0, le=1)]
_JSON_ADAPTER = TypeAdapter(object)


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


class PlannerPolicyEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: PlannerPolicy
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")
    changed_coordinate: PlannerPolicyCoordinate | None
    baseline_values: tuple[float, ...] = ()
    candidate_values: tuple[float, ...] = ()
    metrics: PathEvaluationMetrics
    skip_mismatch_case_ids: tuple[str, ...] = ()
    depth_mismatch_case_ids: tuple[str, ...] = ()
    invariant_failure_case_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_evaluation(self) -> "PlannerPolicyEvaluation":
        if self.policy_digest != build_policy_digest(self.policy):
            raise ValueError("planner policy evaluation digest does not match policy")
        if self.changed_coordinate is None:
            if self.baseline_values or self.candidate_values:
                raise ValueError("baseline evaluation must not have changed values")
        elif (
            not self.baseline_values
            or not self.candidate_values
            or len(self.baseline_values) != len(self.candidate_values)
        ):
            raise ValueError("candidate evaluation requires matching changed values")
        for field_name in (
            "skip_mismatch_case_ids",
            "depth_mismatch_case_ids",
            "invariant_failure_case_ids",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be unique")
        return self


class PlannerPolicyCalibrationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["planner-policy-calibration-report.v1"] = (
        "planner-policy-calibration-report.v1"
    )
    data_kind: Literal["synthetic"] = "synthetic"
    disclaimer: Literal[
        "Synthetic regression results; not evidence of real student learning effectiveness."
    ] = SYNTHETIC_DISCLAIMER
    data_version: str = Field(min_length=1)
    dataset_digest: str = Field(pattern=r"^synthetic_dataset_[0-9a-f]{64}$")
    graph_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")
    seed: int
    generated_at: datetime
    search_space_digest: str = Field(pattern=r"^planner_search_[0-9a-f]{64}$")
    baseline: PlannerPolicyEvaluation
    ranked_candidates: tuple[PlannerPolicyEvaluation, ...] = Field(min_length=1)
    best_fitting_candidate: PlannerPolicyEvaluation
    report_digest: str = Field(pattern=r"^planner_calibration_[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_report(self) -> "PlannerPolicyCalibrationReport":
        if self.baseline.changed_coordinate is not None:
            raise ValueError("calibration baseline must not have a changed coordinate")
        if any(
            item.metrics.case_count != self.baseline.metrics.case_count
            for item in self.ranked_candidates
        ):
            raise ValueError("calibration candidate metrics case count mismatch")
        candidate_digests = [item.policy_digest for item in self.ranked_candidates]
        if len(candidate_digests) != len(set(candidate_digests)):
            raise ValueError("calibration candidate policy digests must be unique")
        baseline_tunables = _tunable_values(self.baseline.policy)
        if any(
            _tunable_values(item.policy) == baseline_tunables
            for item in self.ranked_candidates
        ):
            raise ValueError("calibration candidates must exclude the baseline")
        expected = tuple(
            sorted(
                self.ranked_candidates,
                key=lambda item: _ranking_key(item, self.baseline.policy),
            )
        )
        if expected != self.ranked_candidates:
            raise ValueError("calibration candidate ranking does not match metrics")
        if self.best_fitting_candidate != self.ranked_candidates[0]:
            raise ValueError("calibration best candidate does not match ranking")
        expected_digest = build_planner_calibration_report_digest(
            self.model_dump(mode="json", exclude={"report_digest"})
        )
        if self.report_digest != expected_digest:
            raise ValueError("planner calibration report digest does not match content")
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


def evaluate_planner_policy(
    catalog: OntologyCatalog,
    dataset: SyntheticPlanningDataset,
    policy: PlannerPolicy,
    candidate: PlannerPolicyCandidate | None = None,
) -> PlannerPolicyEvaluation:
    if not isinstance(catalog, OntologyCatalog):
        raise TypeError("catalog must be an OntologyCatalog")
    dataset = SyntheticPlanningDataset.model_validate(dataset.model_dump())
    active_policy = PlannerPolicy.model_validate(policy.model_dump())
    if dataset.graph_version != catalog.course_document.version:
        raise ValueError("synthetic dataset graph version does not match catalog")
    policy_digest = build_policy_digest(active_policy)
    if candidate is None:
        if (
            dataset.policy_version != active_policy.version
            or dataset.policy_digest != policy_digest
        ):
            raise ValueError("synthetic dataset baseline policy does not match policy")
    else:
        if candidate.policy != active_policy or candidate.policy_digest != policy_digest:
            raise ValueError("planner policy candidate does not match policy")
    case_results = evaluate_course_path_cases(catalog, dataset, active_policy)
    metrics = reconstruct_path_evaluation_metrics(case_results)
    return PlannerPolicyEvaluation(
        policy=active_policy,
        policy_digest=policy_digest,
        changed_coordinate=(None if candidate is None else candidate.changed_coordinate),
        baseline_values=() if candidate is None else candidate.baseline_values,
        candidate_values=() if candidate is None else candidate.candidate_values,
        metrics=metrics,
        skip_mismatch_case_ids=tuple(
            item.case_id for item in case_results if item.skip_mismatch_ids
        ),
        depth_mismatch_case_ids=tuple(
            item.case_id for item in case_results if item.depth_mismatch_ids
        ),
        invariant_failure_case_ids=tuple(
            item.case_id
            for item in case_results
            if (
                item.missing_concept_ids
                or item.unexpected_concept_ids
                or item.prerequisite_violation_pairs
                or not item.order_stable
            )
        ),
    )


def search_planner_policies(
    catalog: OntologyCatalog,
    dataset: SyntheticPlanningDataset,
    search_space: PlannerPolicySearchSpace | None = None,
    baseline: PlannerPolicy | None = None,
) -> PlannerPolicyCalibrationReport:
    if not isinstance(catalog, OntologyCatalog):
        raise TypeError("catalog must be an OntologyCatalog")
    active_baseline = PlannerPolicy.model_validate(
        (baseline or PlannerPolicy()).model_dump()
    )
    dataset = SyntheticPlanningDataset.model_validate(dataset.model_dump())
    if dataset.graph_version != catalog.course_document.version:
        raise ValueError("synthetic dataset graph version does not match catalog")
    if (
        dataset.policy_version != active_baseline.version
        or dataset.policy_digest != build_policy_digest(active_baseline)
    ):
        raise ValueError("synthetic dataset baseline policy does not match policy")
    active_space = search_space or default_planner_policy_search_space(active_baseline)
    active_space = PlannerPolicySearchSpace.model_validate(active_space.model_dump())
    baseline_evaluation = evaluate_planner_policy(catalog, dataset, active_baseline)
    candidates = generate_planner_policy_candidates(active_space, active_baseline)
    evaluations = tuple(
        evaluate_planner_policy(catalog, dataset, item.policy, item)
        for item in candidates
    )
    ranked = tuple(
        sorted(
            evaluations,
            key=lambda item: _ranking_key(item, active_baseline),
        )
    )
    payload = {
        "schema_version": "planner-policy-calibration-report.v1",
        "data_kind": "synthetic",
        "disclaimer": SYNTHETIC_DISCLAIMER,
        "data_version": dataset.data_version,
        "dataset_digest": dataset.dataset_digest,
        "graph_version": dataset.graph_version,
        "policy_version": active_baseline.version,
        "policy_digest": build_policy_digest(active_baseline),
        "seed": dataset.seed,
        "generated_at": dataset.generated_at,
        "search_space_digest": build_planner_search_space_digest(active_space),
        "baseline": baseline_evaluation,
        "ranked_candidates": ranked,
        "best_fitting_candidate": ranked[0],
    }
    return PlannerPolicyCalibrationReport(
        data_version=dataset.data_version,
        dataset_digest=dataset.dataset_digest,
        graph_version=dataset.graph_version,
        policy_version=active_baseline.version,
        policy_digest=build_policy_digest(active_baseline),
        seed=dataset.seed,
        generated_at=dataset.generated_at,
        search_space_digest=build_planner_search_space_digest(active_space),
        baseline=baseline_evaluation,
        ranked_candidates=ranked,
        best_fitting_candidate=ranked[0],
        report_digest=build_planner_calibration_report_digest(payload),
    )


def build_planner_search_space_digest(search_space: PlannerPolicySearchSpace) -> str:
    canonical = json.dumps(
        search_space.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"planner_search_{sha256(canonical.encode('utf-8')).hexdigest()}"


def build_planner_calibration_report_digest(payload: object) -> str:
    serializable = _JSON_ADAPTER.dump_python(payload, mode="json")
    canonical = json.dumps(
        serializable,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"planner_calibration_{sha256(canonical.encode('utf-8')).hexdigest()}"


def _ranking_key(
    evaluation: PlannerPolicyEvaluation,
    baseline: PlannerPolicy,
) -> tuple[int, float, float, float, float, str]:
    return (
        len(evaluation.invariant_failure_case_ids),
        -evaluation.metrics.skip_accuracy,
        -evaluation.metrics.delivery_depth_accuracy,
        -evaluation.metrics.low_confidence_conservative_rate,
        _policy_distance(evaluation.policy, baseline),
        evaluation.policy_digest,
    )


def _policy_distance(left: PlannerPolicy, right: PlannerPolicy) -> float:
    left_values = _tunable_values(left)
    right_values = _tunable_values(right)
    return sum(abs(a - b) for a, b in zip(left_values, right_values, strict=True)) / len(
        left_values
    )




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
