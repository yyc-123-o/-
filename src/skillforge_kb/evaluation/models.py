import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from math import isclose
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from skillforge_kb.ontology.models import (
    CONCEPT_ID_PATTERN,
    DepthLevel,
    LearnerProfileSnapshot,
)

_JSON_ADAPTER = TypeAdapter(object)


class ScenarioCohort(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    UNEVEN = "uneven"
    LOW_CONFIDENCE = "low_confidence"
    MISSING_EVIDENCE = "missing_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    BOUNDARY = "boundary"


class ExpectedNodeDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    should_skip: bool
    delivery_depth: DepthLevel | None

    @model_validator(mode="after")
    def validate_skip_depth(self) -> "ExpectedNodeDecision":
        if self.should_skip and self.delivery_depth is not None:
            raise ValueError("expected skipped nodes must not have a delivery depth")
        if not self.should_skip and self.delivery_depth is None:
            raise ValueError("expected learning nodes require a delivery depth")
        return self


class SyntheticPlanningCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    cohort: ScenarioCohort
    tags: tuple[str, ...] = Field(min_length=1)
    profile: LearnerProfileSnapshot
    expected_nodes: tuple[ExpectedNodeDecision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case(self) -> "SyntheticPlanningCase":
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("synthetic case tags must be unique")
        concept_ids = [item.concept_id for item in self.expected_nodes]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("expected concept IDs must be unique")
        return self


class SyntheticPlanningDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["synthetic-planning-dataset.v1"] = (
        "synthetic-planning-dataset.v1"
    )
    data_kind: Literal["synthetic"] = "synthetic"
    data_version: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")
    seed: int
    generated_at: datetime
    cases: tuple[SyntheticPlanningCase, ...] = Field(min_length=8)
    dataset_digest: str = Field(pattern=r"^synthetic_dataset_[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_dataset(self) -> "SyntheticPlanningDataset":
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("synthetic case IDs must be unique")
        for case in self.cases:
            if case.profile.graph_version != self.graph_version:
                raise ValueError("synthetic case graph version mismatch")
        expected = build_synthetic_dataset_digest(
            self.model_dump(mode="json", exclude={"dataset_digest"})
        )
        if self.dataset_digest != expected:
            raise ValueError("synthetic dataset digest does not match content")
        return self


def build_synthetic_dataset_digest(payload: object) -> str:
    serializable = _JSON_ADAPTER.dump_python(payload, mode="json")
    canonical = json.dumps(
        serializable,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"synthetic_dataset_{sha256(canonical.encode('utf-8')).hexdigest()}"


SYNTHETIC_DISCLAIMER: Literal[
    "Synthetic regression results; not evidence of real student learning effectiveness."
] = (
    "Synthetic regression results; not evidence of real student learning effectiveness."
)


class PathEvaluationCaseResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(pattern=r"^[a-z][a-z0-9_-]+$")
    cohort: ScenarioCohort
    tags: tuple[str, ...] = Field(min_length=1)
    path_id: str = Field(pattern=r"^path_[0-9a-f]{64}$")
    required_concept_count: int = Field(ge=1)
    returned_concept_count: int = Field(ge=0)
    covered_concept_count: int = Field(ge=0)
    learning_node_count: int = Field(ge=0)
    skipped_node_count: int = Field(ge=0)
    hard_prerequisite_edge_count: int = Field(ge=0)
    hard_prerequisite_violation_count: int = Field(ge=0)
    skip_evaluable_count: int = Field(ge=1)
    skip_match_count: int = Field(ge=0)
    depth_evaluable_count: int = Field(ge=0)
    depth_match_count: int = Field(ge=0)
    order_stable: bool
    low_confidence_conservative: bool | None = None
    missing_concept_ids: tuple[str, ...] = ()
    unexpected_concept_ids: tuple[str, ...] = ()
    prerequisite_violation_pairs: tuple[tuple[str, str], ...] = ()
    skip_mismatch_ids: tuple[str, ...] = ()
    depth_mismatch_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_counts(self) -> "PathEvaluationCaseResult":
        if self.returned_concept_count != self.learning_node_count + self.skipped_node_count:
            raise ValueError("returned count must equal learning plus skipped counts")
        if self.covered_concept_count != self.required_concept_count - len(
            self.missing_concept_ids
        ):
            raise ValueError("covered count does not match missing concepts")
        if self.hard_prerequisite_violation_count != len(
            self.prerequisite_violation_pairs
        ):
            raise ValueError("prerequisite violation count does not match pairs")
        if self.skip_evaluable_count - self.skip_match_count != len(
            self.skip_mismatch_ids
        ):
            raise ValueError("skip mismatch count does not match IDs")
        if self.depth_evaluable_count - self.depth_match_count != len(
            self.depth_mismatch_ids
        ):
            raise ValueError("depth mismatch count does not match IDs")
        if self.cohort is ScenarioCohort.LOW_CONFIDENCE:
            if self.low_confidence_conservative is None:
                raise ValueError("low-confidence cases require a conservative result")
        elif self.low_confidence_conservative is not None:
            raise ValueError("only low-confidence cases have a conservative result")
        return self


class PathEvaluationMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_count: int = Field(ge=1)
    required_concept_total: int = Field(ge=1)
    covered_concept_total: int = Field(ge=0)
    hard_prerequisite_edge_total: int = Field(ge=0)
    hard_prerequisite_violation_total: int = Field(ge=0)
    skip_evaluable_total: int = Field(ge=1)
    skip_match_total: int = Field(ge=0)
    depth_evaluable_total: int = Field(ge=1)
    depth_match_total: int = Field(ge=0)
    stable_order_case_count: int = Field(ge=0)
    low_confidence_case_count: int = Field(ge=1)
    low_confidence_conservative_count: int = Field(ge=0)
    learning_node_total: int = Field(ge=0)
    skipped_node_total: int = Field(ge=0)
    hard_prerequisite_violation_rate: float = Field(ge=0, le=1)
    required_concept_coverage_rate: float = Field(ge=0, le=1)
    skip_accuracy: float = Field(ge=0, le=1)
    delivery_depth_accuracy: float = Field(ge=0, le=1)
    path_order_stability_rate: float = Field(ge=0, le=1)
    low_confidence_conservative_rate: float = Field(ge=0, le=1)
    mean_learning_node_count: float = Field(ge=0)
    mean_skipped_node_count: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_rates(self) -> "PathEvaluationMetrics":
        expected = (
            (
                "hard prerequisite violation rate",
                self.hard_prerequisite_violation_rate,
                self.hard_prerequisite_violation_total,
                self.hard_prerequisite_edge_total,
            ),
            (
                "required concept coverage rate",
                self.required_concept_coverage_rate,
                self.covered_concept_total,
                self.required_concept_total,
            ),
            (
                "skip accuracy",
                self.skip_accuracy,
                self.skip_match_total,
                self.skip_evaluable_total,
            ),
            (
                "delivery depth accuracy",
                self.delivery_depth_accuracy,
                self.depth_match_total,
                self.depth_evaluable_total,
            ),
            (
                "path order stability rate",
                self.path_order_stability_rate,
                self.stable_order_case_count,
                self.case_count,
            ),
            (
                "low confidence conservative rate",
                self.low_confidence_conservative_rate,
                self.low_confidence_conservative_count,
                self.low_confidence_case_count,
            ),
        )
        for label, rate, part, whole in expected:
            if not isclose(rate, _rate(part, whole), abs_tol=1e-12):
                raise ValueError(f"path evaluation {label} does not match counts")
        if not isclose(
            self.mean_learning_node_count,
            self.learning_node_total / self.case_count,
            abs_tol=1e-12,
        ):
            raise ValueError("mean learning node count does not match total")
        if not isclose(
            self.mean_skipped_node_count,
            self.skipped_node_total / self.case_count,
            abs_tol=1e-12,
        ):
            raise ValueError("mean skipped node count does not match total")
        return self


class PathEvaluationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["path-evaluation-report.v1"] = "path-evaluation-report.v1"
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
    case_results: tuple[PathEvaluationCaseResult, ...] = Field(min_length=8)
    metrics: PathEvaluationMetrics
    report_digest: str = Field(pattern=r"^path_evaluation_[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_report(self) -> "PathEvaluationReport":
        case_ids = [item.case_id for item in self.case_results]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("path evaluation case IDs must be unique")
        expected_metrics = reconstruct_path_evaluation_metrics(self.case_results)
        if not isclose(
            self.metrics.skip_accuracy,
            expected_metrics.skip_accuracy,
            abs_tol=1e-12,
        ):
            raise ValueError("path evaluation skip accuracy does not match case results")
        if self.metrics != expected_metrics:
            raise ValueError("path evaluation metrics do not match case results")
        expected_digest = build_path_evaluation_report_digest(
            self.model_dump(mode="json", exclude={"report_digest"})
        )
        if self.report_digest != expected_digest:
            raise ValueError("path evaluation report digest does not match content")
        return self


def reconstruct_path_evaluation_metrics(
    results: tuple[PathEvaluationCaseResult, ...],
) -> PathEvaluationMetrics:
    case_count = len(results)
    required_total = sum(item.required_concept_count for item in results)
    covered_total = sum(item.covered_concept_count for item in results)
    edge_total = sum(item.hard_prerequisite_edge_count for item in results)
    violation_total = sum(item.hard_prerequisite_violation_count for item in results)
    skip_evaluable_total = sum(item.skip_evaluable_count for item in results)
    skip_match_total = sum(item.skip_match_count for item in results)
    depth_evaluable_total = sum(item.depth_evaluable_count for item in results)
    depth_match_total = sum(item.depth_match_count for item in results)
    stable_count = sum(item.order_stable for item in results)
    low_confidence_results = tuple(
        item for item in results if item.cohort is ScenarioCohort.LOW_CONFIDENCE
    )
    low_confidence_count = len(low_confidence_results)
    conservative_count = sum(
        item.low_confidence_conservative is True for item in low_confidence_results
    )
    learning_total = sum(item.learning_node_count for item in results)
    skipped_total = sum(item.skipped_node_count for item in results)
    return PathEvaluationMetrics(
        case_count=case_count,
        required_concept_total=required_total,
        covered_concept_total=covered_total,
        hard_prerequisite_edge_total=edge_total,
        hard_prerequisite_violation_total=violation_total,
        skip_evaluable_total=skip_evaluable_total,
        skip_match_total=skip_match_total,
        depth_evaluable_total=depth_evaluable_total,
        depth_match_total=depth_match_total,
        stable_order_case_count=stable_count,
        low_confidence_case_count=low_confidence_count,
        low_confidence_conservative_count=conservative_count,
        learning_node_total=learning_total,
        skipped_node_total=skipped_total,
        hard_prerequisite_violation_rate=_rate(violation_total, edge_total),
        required_concept_coverage_rate=_rate(covered_total, required_total),
        skip_accuracy=_rate(skip_match_total, skip_evaluable_total),
        delivery_depth_accuracy=_rate(depth_match_total, depth_evaluable_total),
        path_order_stability_rate=_rate(stable_count, case_count),
        low_confidence_conservative_rate=_rate(
            conservative_count,
            low_confidence_count,
        ),
        mean_learning_node_count=learning_total / case_count,
        mean_skipped_node_count=skipped_total / case_count,
    )


def build_path_evaluation_report_digest(payload: object) -> str:
    serializable = _JSON_ADAPTER.dump_python(payload, mode="json")
    canonical = json.dumps(
        serializable,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"path_evaluation_{sha256(canonical.encode('utf-8')).hexdigest()}"


def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0
