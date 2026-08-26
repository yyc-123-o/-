import json
from enum import StrEnum
from hashlib import sha256
from itertools import pairwise, product
from math import fsum, isclose
from statistics import fmean
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .adaptation import (
    NodeWeightFeatures,
    NodeWeightPolicy,
    SupportIntensity,
    build_node_weight_policy_digest,
    score_node_support,
)

UnitFloat = Annotated[float, Field(ge=0, le=1)]


class CalibrationDataKind(StrEnum):
    SYNTHETIC = "synthetic"
    EXPERT_LABELLED = "expert_labelled"
    OBSERVED = "observed"


class NodeWeightFactor(StrEnum):
    MASTERY_GAP = "mastery_gap_weight"
    ERROR_RISK = "error_risk_weight"
    ABILITY_GAP = "ability_gap_weight"


class NodeWeightCalibrationExample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    features: NodeWeightFeatures
    expected_support_intensity: SupportIntensity
    target_support_need_score: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_blocked_label(self) -> "NodeWeightCalibrationExample":
        if (
            self.features.blocked
            and self.expected_support_intensity is not SupportIntensity.REMEDIATION
        ):
            raise ValueError("blocked examples must expect remediation")
        if (
            not self.features.blocked
            and self.expected_support_intensity is SupportIntensity.REMEDIATION
        ):
            raise ValueError("non-blocked examples cannot expect remediation")
        return self


class NodeWeightCalibrationDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["node-weight-calibration-dataset.v1"] = (
        "node-weight-calibration-dataset.v1"
    )
    dataset_id: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    data_kind: CalibrationDataKind
    examples: tuple[NodeWeightCalibrationExample, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> "NodeWeightCalibrationDataset":
        case_ids = tuple(item.case_id for item in self.examples)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("calibration case IDs must be unique")
        return self


class NodeWeightSearchSpace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version_prefix: str = Field(
        default="node-weight-policy.candidate.v1",
        min_length=1,
    )
    mastery_gap_weights: tuple[UnitFloat, ...] = Field(default=(0.55,), min_length=1)
    error_risk_weights: tuple[UnitFloat, ...] = Field(default=(0.25,), min_length=1)
    ability_gap_weights: tuple[UnitFloat, ...] = Field(default=(0.20,), min_length=1)
    compact_thresholds: tuple[UnitFloat, ...] = Field(default=(0.25,), min_length=1)
    scaffolded_thresholds: tuple[UnitFloat, ...] = Field(default=(0.60,), min_length=1)

    @model_validator(mode="after")
    def validate_axes(self) -> "NodeWeightSearchSpace":
        axis_names = (
            "mastery_gap_weights",
            "error_risk_weights",
            "ability_gap_weights",
            "compact_thresholds",
            "scaffolded_thresholds",
        )
        for axis_name in axis_names:
            values = getattr(self, axis_name)
            if any(left >= right for left, right in pairwise(values)):
                raise ValueError(f"{axis_name} must be strictly increasing")
        return self


class NodeWeightCaseResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    predicted_support_need_score: float = Field(ge=0, le=1)
    predicted_support_intensity: SupportIntensity
    intensity_matches: bool
    absolute_error: float | None = Field(default=None, ge=0, le=1)


class NodeWeightPolicyEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: NodeWeightPolicy
    policy_digest: str = Field(pattern=r"^node_policy_[0-9a-f]{64}$")
    case_count: int = Field(ge=1)
    exact_match_count: int = Field(ge=0)
    exact_match_rate: float = Field(ge=0, le=1)
    target_case_count: int = Field(ge=0)
    mean_absolute_error: float | None = Field(default=None, ge=0, le=1)
    case_results: tuple[NodeWeightCaseResult, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_metrics(self) -> "NodeWeightPolicyEvaluation":
        if self.policy_digest != build_node_weight_policy_digest(self.policy):
            raise ValueError("policy digest does not match policy")
        if self.case_count != len(self.case_results):
            raise ValueError("case count does not match case results")
        case_ids = tuple(item.case_id for item in self.case_results)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation case IDs must be unique")
        exact_match_count = sum(item.intensity_matches for item in self.case_results)
        if self.exact_match_count != exact_match_count:
            raise ValueError("exact match count does not match case results")
        expected_rate = exact_match_count / self.case_count
        if not isclose(self.exact_match_rate, expected_rate, abs_tol=1e-12):
            raise ValueError("exact match rate does not match case results")
        errors = tuple(
            item.absolute_error
            for item in self.case_results
            if item.absolute_error is not None
        )
        if self.target_case_count != len(errors):
            raise ValueError("target case count does not match case results")
        expected_error = fmean(errors) if errors else None
        if expected_error is None:
            if self.mean_absolute_error is not None:
                raise ValueError("mean absolute error requires target cases")
        elif self.mean_absolute_error is None or not isclose(
            self.mean_absolute_error,
            expected_error,
            abs_tol=1e-12,
        ):
            raise ValueError("mean absolute error does not match case results")
        return self


class NodeWeightCalibrationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["node-weight-calibration-report.v1"] = (
        "node-weight-calibration-report.v1"
    )
    dataset_id: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    data_kind: CalibrationDataKind
    dataset_digest: str = Field(pattern=r"^calibration_dataset_[0-9a-f]{64}$")
    baseline: NodeWeightPolicyEvaluation
    ranked_candidates: tuple[NodeWeightPolicyEvaluation, ...] = Field(min_length=1)
    best_fitting_candidate: NodeWeightPolicyEvaluation

    @model_validator(mode="after")
    def validate_best_candidate(self) -> "NodeWeightCalibrationReport":
        baseline_case_ids = _case_ids(self.baseline)
        baseline_target_coverage = _target_coverage(self.baseline)
        baseline_values = _tunable_values(self.baseline.policy)
        candidate_values: list[tuple[float, ...]] = []
        for candidate in self.ranked_candidates:
            if _case_ids(candidate) != baseline_case_ids:
                raise ValueError("all policy evaluations must use the same ordered cases")
            if _target_coverage(candidate) != baseline_target_coverage:
                raise ValueError("all policy evaluations must use the same target coverage")
            values = _tunable_values(candidate.policy)
            if values == baseline_values:
                raise ValueError("ranked candidates must exclude baseline tunables")
            candidate_values.append(values)
        if len(candidate_values) != len(set(candidate_values)):
            raise ValueError("ranked candidate tunables must be unique")
        expected_ranking = tuple(
            sorted(
                self.ranked_candidates,
                key=lambda item: _ranking_key(item, self.baseline.policy),
            )
        )
        if self.ranked_candidates != expected_ranking:
            raise ValueError("candidate ranking does not match documented ordering")
        if self.best_fitting_candidate != self.ranked_candidates[0]:
            raise ValueError("best fitting candidate must be the first ranked candidate")
        return self


class NodeWeightAblationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    removed_factor: NodeWeightFactor
    evaluation: NodeWeightPolicyEvaluation


class NodeWeightSensitivityPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    factor: NodeWeightFactor
    value: float = Field(ge=0, le=1)
    candidate_count: int = Field(ge=1)
    mean_exact_match_rate: float = Field(ge=0, le=1)
    mean_absolute_error: float | None = Field(default=None, ge=0, le=1)


def build_calibration_dataset_digest(dataset: NodeWeightCalibrationDataset) -> str:
    return f"calibration_dataset_{_hash(dataset.model_dump(mode='json'))}"


def generate_node_weight_policies(
    search_space: NodeWeightSearchSpace,
) -> tuple[NodeWeightPolicy, ...]:
    policies: list[NodeWeightPolicy] = []
    combinations = product(
        search_space.mastery_gap_weights,
        search_space.error_risk_weights,
        search_space.ability_gap_weights,
        search_space.compact_thresholds,
        search_space.scaffolded_thresholds,
    )
    for mastery, error, ability, compact, scaffolded in combinations:
        weight_sum = fsum((mastery, error, ability))
        if weight_sum > 1.0 or not isclose(
            weight_sum,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            continue
        if compact >= scaffolded:
            continue
        policies.append(
            NodeWeightPolicy(
                version=f"{search_space.policy_version_prefix}.{len(policies) + 1:04d}",
                mastery_gap_weight=mastery,
                error_risk_weight=error,
                ability_gap_weight=ability,
                compact_threshold=compact,
                scaffolded_threshold=scaffolded,
            )
        )
    if not policies:
        raise ValueError("search space contains no valid policy")
    return tuple(policies)


def evaluate_node_weight_policy(
    dataset: NodeWeightCalibrationDataset,
    policy: NodeWeightPolicy,
) -> NodeWeightPolicyEvaluation:
    case_results: list[NodeWeightCaseResult] = []
    for example in dataset.examples:
        score = score_node_support(example.features, policy)
        target = example.target_support_need_score
        case_results.append(
            NodeWeightCaseResult(
                case_id=example.case_id,
                predicted_support_need_score=score.support_need_score,
                predicted_support_intensity=score.support_intensity,
                intensity_matches=(
                    score.support_intensity is example.expected_support_intensity
                ),
                absolute_error=(
                    None
                    if target is None
                    else abs(score.support_need_score - target)
                ),
            )
        )
    results = tuple(case_results)
    exact_match_count = sum(item.intensity_matches for item in results)
    errors = tuple(item.absolute_error for item in results if item.absolute_error is not None)
    return NodeWeightPolicyEvaluation(
        policy=policy,
        policy_digest=build_node_weight_policy_digest(policy),
        case_count=len(results),
        exact_match_count=exact_match_count,
        exact_match_rate=exact_match_count / len(results),
        target_case_count=len(errors),
        mean_absolute_error=fmean(errors) if errors else None,
        case_results=results,
    )


def search_node_weight_policies(
    dataset: NodeWeightCalibrationDataset,
    search_space: NodeWeightSearchSpace,
    baseline: NodeWeightPolicy | None = None,
) -> NodeWeightCalibrationReport:
    baseline_policy = baseline or NodeWeightPolicy()
    baseline_values = _tunable_values(baseline_policy)
    alternatives = tuple(
        policy
        for policy in generate_node_weight_policies(search_space)
        if _tunable_values(policy) != baseline_values
    )
    if not alternatives:
        raise ValueError("search space contains no alternative policy")
    evaluations = [evaluate_node_weight_policy(dataset, policy) for policy in alternatives]

    ranked = tuple(
        sorted(
            evaluations,
            key=lambda item: _ranking_key(item, baseline_policy),
        )
    )
    return NodeWeightCalibrationReport(
        dataset_id=dataset.dataset_id,
        data_version=dataset.data_version,
        data_kind=dataset.data_kind,
        dataset_digest=build_calibration_dataset_digest(dataset),
        baseline=evaluate_node_weight_policy(dataset, baseline_policy),
        ranked_candidates=ranked,
        best_fitting_candidate=ranked[0],
    )


def evaluate_node_weight_ablations(
    dataset: NodeWeightCalibrationDataset,
    baseline: NodeWeightPolicy,
) -> tuple[NodeWeightAblationResult, ...]:
    results: list[NodeWeightAblationResult] = []
    for factor in NodeWeightFactor:
        removed_weight = getattr(baseline, factor.value)
        if removed_weight == 0:
            continue
        remaining_weight = sum(
            getattr(baseline, candidate.value)
            for candidate in NodeWeightFactor
            if candidate is not factor
        )
        if remaining_weight <= 0:
            raise ValueError("ablation leaves no positive remaining weight")
        updates = {
            candidate.value: (
                0.0
                if candidate is factor
                else getattr(baseline, candidate.value) / remaining_weight
            )
            for candidate in NodeWeightFactor
        }
        updates["version"] = (
            f"{baseline.version}.ablate-{factor.value.removesuffix('_weight')}"
        )
        policy = NodeWeightPolicy.model_validate(
            {**baseline.model_dump(), **updates}
        )
        results.append(
            NodeWeightAblationResult(
                removed_factor=factor,
                evaluation=evaluate_node_weight_policy(dataset, policy),
            )
        )
    return tuple(results)


def summarize_node_weight_sensitivity(
    report: NodeWeightCalibrationReport,
) -> tuple[NodeWeightSensitivityPoint, ...]:
    points: list[NodeWeightSensitivityPoint] = []
    for factor in NodeWeightFactor:
        values = sorted(
            {
                getattr(evaluation.policy, factor.value)
                for evaluation in report.ranked_candidates
            }
        )
        for value in values:
            matching = tuple(
                evaluation
                for evaluation in report.ranked_candidates
                if getattr(evaluation.policy, factor.value) == value
            )
            errors = tuple(
                evaluation.mean_absolute_error
                for evaluation in matching
                if evaluation.mean_absolute_error is not None
            )
            points.append(
                NodeWeightSensitivityPoint(
                    factor=factor,
                    value=value,
                    candidate_count=len(matching),
                    mean_exact_match_rate=fmean(
                        evaluation.exact_match_rate for evaluation in matching
                    ),
                    mean_absolute_error=fmean(errors) if errors else None,
                )
            )
    return tuple(points)


def _tunable_values(policy: NodeWeightPolicy) -> tuple[float, ...]:
    return (
        policy.mastery_gap_weight,
        policy.error_risk_weight,
        policy.ability_gap_weight,
        policy.compact_threshold,
        policy.scaffolded_threshold,
    )


def _policy_distance(left: NodeWeightPolicy, right: NodeWeightPolicy) -> float:
    return sum(
        abs(left_value - right_value)
        for left_value, right_value in zip(
            _tunable_values(left),
            _tunable_values(right),
            strict=True,
        )
    )


def _ranking_key(
    evaluation: NodeWeightPolicyEvaluation,
    baseline: NodeWeightPolicy,
) -> tuple[float, float, float, str]:
    error = evaluation.mean_absolute_error
    return (
        -evaluation.exact_match_rate,
        0.0 if error is None else error,
        _policy_distance(evaluation.policy, baseline),
        evaluation.policy_digest,
    )


def _case_ids(evaluation: NodeWeightPolicyEvaluation) -> tuple[str, ...]:
    return tuple(item.case_id for item in evaluation.case_results)


def _target_coverage(
    evaluation: NodeWeightPolicyEvaluation,
) -> tuple[tuple[str, bool], ...]:
    return tuple(
        (item.case_id, item.absolute_error is not None)
        for item in evaluation.case_results
    )


def _hash(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()
