"""自包含的实验性知识追踪实现。"""

from __future__ import annotations

import json
import math
import random
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from itertools import product
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from skillforge_kb.assessment.update import (
        AssessmentErrorKind as ProjectAssessmentErrorKind,
    )
    from skillforge_kb.assessment.update import (
        AssessmentEvent as ProjectAssessmentEvent,
    )
    from skillforge_kb.assessment.update import (
        AssessmentLedger as ProjectAssessmentLedger,
    )
    from skillforge_kb.assessment.update import (
        AssessmentUpdateResult as ProjectAssessmentUpdateResult,
    )
    from skillforge_kb.ontology.catalog import OntologyCatalog
    from skillforge_kb.ontology.concept_attributes import ConceptAttributeCatalog
    from skillforge_kb.ontology.models import LearnerProfileSnapshot
    from skillforge_kb.planning.adaptation import NodeWeightPolicy
    from skillforge_kb.planning.models import PathDecision, PlannerPolicy


ErrorKind = Literal[
    "concept_confusion",
    "logic_gap",
    "calculation_error",
    "missed_condition",
    "code_shape_error",
]

AssessmentDepth = Literal["intro", "intermediate", "advanced"]


@runtime_checkable
class SupportsToDict(Protocol):
    def to_dict(self) -> dict[str, object]:
        """返回可 JSON 序列化的字典。"""


@dataclass(frozen=True)
class AssessmentItemMetadata:
    """可选的题目级证据，用于让观测更新更有区分度。"""

    item_id: str
    difficulty: float | None = None
    discrimination: float | None = None
    target_depth: AssessmentDepth | None = None
    expected_time_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValueError("item_id must not be empty")
        if self.difficulty is not None and not 0 <= self.difficulty <= 1:
            raise ValueError("item difficulty must be within [0, 1]")
        if self.discrimination is not None and self.discrimination <= 0:
            raise ValueError("item discrimination must be positive")
        if self.expected_time_ms is not None and self.expected_time_ms < 0:
            raise ValueError("expected_time_ms must be non-negative")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> AssessmentItemMetadata:
        return cls(
            item_id=_required_string(payload, "item_id"),
            difficulty=_optional_float(payload.get("difficulty")),
            discrimination=_optional_float(payload.get("discrimination")),
            target_depth=_optional_depth(payload.get("target_depth")),
            expected_time_ms=_optional_int(payload.get("expected_time_ms")),
        )


ItemMetadataRegistry = Mapping[str, AssessmentItemMetadata | Mapping[str, object]]


def clamp_probability(value: float) -> float:
    """将数值限制在概率区间内。"""
    if math.isnan(value):
        raise ValueError("probability cannot be NaN")
    return min(1.0, max(0.0, value))


def stable_digest(prefix: str, payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return f"{prefix}_{sha256(canonical.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True)
class BKTParameters:
    """版本化的 Bayesian Knowledge Tracing 参数。"""

    version: str = "bkt-default.v1"
    prior_mastery: float = 0.35
    learn_probability: float = 0.12
    guess_probability: float = 0.20
    slip_probability: float = 0.10
    hint_guess_boost: float = 0.06
    retry_guess_boost: float = 0.04
    maximum_penalized_hints: int = 3
    maximum_penalized_retries: int = 3
    confidence_gain: float = 0.16
    minimum_observed_confidence: float = 0.25

    def __post_init__(self) -> None:
        for name in (
            "prior_mastery",
            "learn_probability",
            "guess_probability",
            "slip_probability",
            "hint_guess_boost",
            "retry_guess_boost",
            "confidence_gain",
            "minimum_observed_confidence",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be within [0, 1]")
        if self.maximum_penalized_hints < 0:
            raise ValueError("maximum_penalized_hints must be non-negative")
        if self.maximum_penalized_retries < 0:
            raise ValueError("maximum_penalized_retries must be non-negative")

    @property
    def digest(self) -> str:
        return stable_digest("bkt_policy", self.__dict__)


@dataclass(frozen=True)
class ForgettingParameters:
    """基于有效掌握度的指数遗忘参数。"""

    version: str = "forgetting-exp.v1"
    enabled: bool = True
    decay_rate_per_day: float = 0.018
    prior_floor: float = 0.15
    evidence_resistance_weight: float = 0.18
    confidence_resistance_weight: float = 0.50

    def __post_init__(self) -> None:
        if self.decay_rate_per_day < 0:
            raise ValueError("decay_rate_per_day must be non-negative")
        for name in (
            "prior_floor",
            "evidence_resistance_weight",
            "confidence_resistance_weight",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be within [0, 1]")

    @property
    def digest(self) -> str:
        return stable_digest("forgetting_policy", self.__dict__)


@dataclass(frozen=True)
class KnowledgeTracingPolicy:
    """用于报告和策略审查的组合版本化策略。"""

    version: str = "knowledge-tracing-policy.v2"
    bkt: BKTParameters = field(default_factory=BKTParameters)
    forgetting: ForgettingParameters = field(default_factory=ForgettingParameters)
    low_confidence_threshold: float = 0.60
    high_mastery_threshold: float = 0.85
    enable_concept_difficulty_adjustment: bool = True
    prior_difficulty_weight: float = 0.06
    learn_difficulty_weight: float = 0.015
    guess_difficulty_weight: float = 0.02
    slip_difficulty_weight: float = 0.015

    def __post_init__(self) -> None:
        for name in (
            "low_confidence_threshold",
            "high_mastery_threshold",
            "prior_difficulty_weight",
            "learn_difficulty_weight",
            "guess_difficulty_weight",
            "slip_difficulty_weight",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be within [0, 1]")

    @property
    def digest(self) -> str:
        return stable_digest(
            "kt_policy",
            {
                "version": self.version,
                "bkt": self.bkt.__dict__,
                "forgetting": self.forgetting.__dict__,
                "low_confidence_threshold": self.low_confidence_threshold,
                "high_mastery_threshold": self.high_mastery_threshold,
                "enable_concept_difficulty_adjustment": (
                    self.enable_concept_difficulty_adjustment
                ),
                "prior_difficulty_weight": self.prior_difficulty_weight,
                "learn_difficulty_weight": self.learn_difficulty_weight,
                "guess_difficulty_weight": self.guess_difficulty_weight,
                "slip_difficulty_weight": self.slip_difficulty_weight,
            },
        )

    @property
    def assessment_policy_digest(self) -> str:
        """与项目 AssessmentUpdateResult 兼容的策略摘要前缀。"""
        return stable_digest(
            "assessment_policy",
            {
                "version": self.version,
                "bkt": self.bkt.__dict__,
                "forgetting": self.forgetting.__dict__,
                "low_confidence_threshold": self.low_confidence_threshold,
                "high_mastery_threshold": self.high_mastery_threshold,
                "enable_concept_difficulty_adjustment": (
                    self.enable_concept_difficulty_adjustment
                ),
                "prior_difficulty_weight": self.prior_difficulty_weight,
                "learn_difficulty_weight": self.learn_difficulty_weight,
                "guess_difficulty_weight": self.guess_difficulty_weight,
                "slip_difficulty_weight": self.slip_difficulty_weight,
            },
        )


@dataclass(frozen=True)
class KTEvent:
    """这个实验文件使用的最小答题事件契约。"""

    event_id: str
    profile_id: str
    graph_version: str
    concept_ids: tuple[str, ...]
    correct: bool
    timestamp: datetime
    response_time_ms: int = 0
    hint_count: int = 0
    attempt_count: int = 1
    error_kind: ErrorKind | None = None
    evidence_refs: tuple[str, ...] = ()
    item_difficulty: float | None = None
    item_discrimination: float | None = None
    target_depth: AssessmentDepth | None = None
    expected_time_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must not be empty")
        if not self.profile_id.strip():
            raise ValueError("profile_id must not be empty")
        if not self.graph_version.strip():
            raise ValueError("graph_version must not be empty")
        if not self.concept_ids:
            raise ValueError("event requires at least one concept")
        if len(self.concept_ids) != len(set(self.concept_ids)):
            raise ValueError("concept_ids must be unique")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.response_time_ms < 0:
            raise ValueError("response_time_ms must be non-negative")
        if self.hint_count < 0:
            raise ValueError("hint_count must be non-negative")
        if self.attempt_count < 1:
            raise ValueError("attempt_count must be at least one")
        if self.correct and self.error_kind is not None:
            raise ValueError("correct events cannot carry error_kind")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs must be unique")
        if self.item_difficulty is not None and not 0 <= self.item_difficulty <= 1:
            raise ValueError("item_difficulty must be within [0, 1]")
        if self.item_discrimination is not None and self.item_discrimination <= 0:
            raise ValueError("item_discrimination must be positive")
        if self.expected_time_ms is not None and self.expected_time_ms < 0:
            raise ValueError("expected_time_ms must be non-negative")

    @property
    def digest(self) -> str:
        return stable_digest("kt_event", event_to_dict(self))


@dataclass(frozen=True)
class KTConceptState:
    """单个课程知识点的学习者追踪状态。"""

    concept_id: str
    mastery_score: float
    confidence: float
    evidence_count: int
    last_observed_at: datetime | None = None
    evidence_refs: tuple[str, ...] = ()
    error_counts: Mapping[str, int] = field(default_factory=dict)
    model_version: str = "bkt.v1"
    parameter_version: str = "bkt-default.v1"
    input_snapshot_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.concept_id.strip():
            raise ValueError("concept_id must not be empty")
        if not 0 <= self.mastery_score <= 1:
            raise ValueError("mastery_score must be within [0, 1]")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be within [0, 1]")
        if self.evidence_count < 0:
            raise ValueError("evidence_count must be non-negative")
        if self.last_observed_at is not None and (
            self.last_observed_at.tzinfo is None
            or self.last_observed_at.utcoffset() is None
        ):
            raise ValueError("last_observed_at must be timezone-aware")
        if any(value < 0 for value in self.error_counts.values()):
            raise ValueError("error counts must be non-negative")

    @property
    def error_risk(self) -> float:
        total_errors = sum(self.error_counts.values())
        if self.evidence_count <= 0:
            return 0.0
        return clamp_probability(total_errors / self.evidence_count)

    def to_profile_mastery_fact(self) -> dict[str, object]:
        """返回一个与 ontology.models.KnowledgeMastery 形状一致的字典。"""
        return {
            "concept_id": self.concept_id,
            "mastery_score": round(self.mastery_score, 6),
            "assessment_status": "assessed",
            "confidence": round(self.confidence, 6),
            "observed_at": (
                self.last_observed_at.isoformat()
                if self.last_observed_at is not None
                else None
            ),
            "evidence_refs": list(self.evidence_refs),
        }

    def planning_features(self, at_time: datetime | None = None) -> dict[str, object]:
        """暴露给规划侧使用的事实，但不改变课程路径逻辑。"""
        return {
            "concept_id": self.concept_id,
            "mastery_score": round(self.mastery_score, 6),
            "confidence": round(self.confidence, 6),
            "error_risk": round(self.error_risk, 6),
            "evidence_count": self.evidence_count,
            "last_observed_at": (
                self.last_observed_at.isoformat()
                if self.last_observed_at is not None
                else None
            ),
            "effective_at": at_time.isoformat() if at_time is not None else None,
            "model_version": self.model_version,
            "parameter_version": self.parameter_version,
            "input_snapshot_digest": self.input_snapshot_digest,
        }


@dataclass(frozen=True)
class KTLedger:
    """用于事件回放去重的小型不可变账本。"""

    profile_id: str
    graph_version: str
    concept_states: Mapping[str, KTConceptState] = field(default_factory=dict)
    processed_events: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("profile_id must not be empty")
        if not self.graph_version.strip():
            raise ValueError("graph_version must not be empty")
        for concept_id, state in self.concept_states.items():
            if concept_id != state.concept_id:
                raise ValueError("concept state key must match state concept_id")

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "graph_version": self.graph_version,
            "concept_states": {
                concept_id: state_to_dict(state)
                for concept_id, state in sorted(self.concept_states.items())
            },
            "processed_events": dict(sorted(self.processed_events.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> KTLedger:
        states_raw = payload.get("concept_states", {})
        if not isinstance(states_raw, Mapping):
            raise ValueError("concept_states must be a mapping")
        processed_raw = payload.get("processed_events", {})
        if not isinstance(processed_raw, Mapping):
            raise ValueError("processed_events must be a mapping")
        return cls(
            profile_id=_required_string(payload, "profile_id"),
            graph_version=_required_string(payload, "graph_version"),
            concept_states={
                str(concept_id): state_from_dict(_require_mapping(raw_state))
                for concept_id, raw_state in states_raw.items()
            },
            processed_events={
                str(event_id): str(digest)
                for event_id, digest in processed_raw.items()
            },
        )


@dataclass(frozen=True)
class ConceptUpdate:
    concept_id: str
    mastery_before: float
    mastery_after: float
    effective_mastery_before: float
    confidence_before: float
    confidence_after: float
    error_risk_after: float
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class KTUpdateResult:
    ledger: KTLedger
    applied: bool
    event_digest: str
    bkt_policy_digest: str
    forgetting_policy_digest: str
    concept_updates: tuple[ConceptUpdate, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "ledger": self.ledger.to_dict(),
            "applied": self.applied,
            "event_digest": self.event_digest,
            "bkt_policy_digest": self.bkt_policy_digest,
            "forgetting_policy_digest": self.forgetting_policy_digest,
            "concept_updates": [asdict(item) for item in self.concept_updates],
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class PredictionRecord:
    concept_id: str
    correct: bool
    timestamp: datetime
    hint_count: int = 0
    attempt_count: int = 1
    latent_mastery: float | None = None


@dataclass(frozen=True)
class EvaluationMetrics:
    count: int
    brier_score: float
    log_loss: float
    accuracy_at_half: float
    expected_calibration_error: float


@dataclass(frozen=True)
class PFAParameters:
    """Performance Factors Analysis（PFA）基线参数。"""

    version: str = "pfa-default.v1"
    intercept: float = -0.40
    success_weight: float = 0.85
    failure_weight: float = -0.65
    hint_penalty: float = 0.18
    retry_penalty: float = 0.12

    @property
    def digest(self) -> str:
        return stable_digest("pfa_policy", self.__dict__)


@dataclass(frozen=True)
class PFAConceptState:
    concept_id: str
    successes: int = 0
    failures: int = 0

    def __post_init__(self) -> None:
        if not self.concept_id.strip():
            raise ValueError("concept_id must not be empty")
        if self.successes < 0:
            raise ValueError("successes must be non-negative")
        if self.failures < 0:
            raise ValueError("failures must be non-negative")


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_prediction: float
    empirical_accuracy: float
    absolute_gap: float


@dataclass(frozen=True)
class ParameterSearchResult:
    parameters: BKTParameters
    forgetting: ForgettingParameters
    metrics: EvaluationMetrics

    def to_dict(self) -> dict[str, object]:
        return {
            "parameters": self.parameters.__dict__,
            "forgetting": self.forgetting.__dict__,
            "metrics": asdict(self.metrics),
        }


@dataclass(frozen=True)
class PFASearchResult:
    parameters: PFAParameters
    metrics: EvaluationMetrics

    def to_dict(self) -> dict[str, object]:
        return {
            "parameters": self.parameters.__dict__,
            "metrics": asdict(self.metrics),
        }


@dataclass(frozen=True)
class ModelComparisonResult:
    """可解释 KT 基线之间的离线对比结果。"""

    schema_version: str
    dataset_id: str
    record_count: int
    bkt: ParameterSearchResult
    pfa: PFASearchResult
    preferred_model: Literal["bkt", "pfa", "tie"]
    selection_metric: Literal["log_loss", "brier_score"]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "record_count": self.record_count,
            "bkt": self.bkt.to_dict(),
            "pfa": self.pfa.to_dict(),
            "preferred_model": self.preferred_model,
            "selection_metric": self.selection_metric,
        }


@dataclass(frozen=True)
class KnowledgeTracingExperimentReport:
    """用于合成数据或带标签实验的机器可读报告。"""

    schema_version: str
    dataset_id: str
    dataset_kind: Literal["synthetic", "expert_labelled", "observed"]
    generated_at: datetime
    record_count: int
    baseline: ParameterSearchResult
    ranked_candidates: tuple[ParameterSearchResult, ...]
    calibration_bins: tuple[CalibrationBin, ...]
    notes: tuple[str, ...]
    validation: dict[str, object] = field(default_factory=dict)

    @property
    def report_id(self) -> str:
        return stable_digest("kt_report", self.to_dict(include_id=False))

    def to_dict(self, *, include_id: bool = True) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "dataset_kind": self.dataset_kind,
            "generated_at": self.generated_at.isoformat(),
            "record_count": self.record_count,
            "baseline": self.baseline.to_dict(),
            "ranked_candidates": [item.to_dict() for item in self.ranked_candidates],
            "calibration_bins": [asdict(item) for item in self.calibration_bins],
            "notes": list(self.notes),
            "validation": self.validation,
        }
        if include_id:
            payload["report_id"] = self.report_id
        return payload


@dataclass(frozen=True)
class ProjectKTOptimizationReport:
    """用于判断下一步应优先尝试哪种 KT 升级的可读报告。"""

    schema_version: str
    policy_version: str
    concept_count: int
    difficulty_counts: Mapping[str, int]
    implemented_optimizations: tuple[str, ...]
    recommended_next_steps: tuple[str, ...]
    paper_anchors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "concept_count": self.concept_count,
            "difficulty_counts": dict(self.difficulty_counts),
            "implemented_optimizations": list(self.implemented_optimizations),
            "recommended_next_steps": list(self.recommended_next_steps),
            "paper_anchors": list(self.paper_anchors),
        }


@dataclass(frozen=True)
class KTStateFact:
    """面向项目的 KT 事实，包含任务书要求的字段。"""

    concept_id: str
    mastery_score: float
    effective_mastery: float
    confidence: float
    error_risk: float
    evidence_count: int
    model_version: str
    parameter_version: str
    input_snapshot_digest: str | None
    reason_codes: tuple[str, ...]
    updated_at: datetime | None

    def to_dict(self) -> dict[str, object]:
        return {
            "concept_id": self.concept_id,
            "mastery_score": self.mastery_score,
            "effective_mastery": self.effective_mastery,
            "confidence": self.confidence,
            "error_risk": self.error_risk,
            "evidence_count": self.evidence_count,
            "model_version": self.model_version,
            "parameter_version": self.parameter_version,
            "input_snapshot_digest": self.input_snapshot_digest,
            "reason_codes": list(self.reason_codes),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(frozen=True)
class ProjectKTBatchUpdateResult:
    """将多条答题事件回放到学习者画像后得到的结果。"""

    final_ledger: ProjectAssessmentLedger
    event_results: tuple[ProjectAssessmentUpdateResult, ...]
    kt_state_facts: tuple[KTStateFact, ...]
    applied_count: int
    duplicate_count: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "final_ledger": _model_dump(self.final_ledger),
            "event_results": [_model_dump(item) for item in self.event_results],
            "kt_state_facts": [item.to_dict() for item in self.kt_state_facts],
            "applied_count": self.applied_count,
            "duplicate_count": self.duplicate_count,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ProjectKTPlanningSignal:
    """带有 KT 信息的路径节点信号。"""

    concept_id: str
    sequence: int
    path_status: str
    delivery_depth: str | None
    mastery_score: float | None
    effective_mastery: float | None
    confidence: float | None
    error_risk: float
    support_need_score: float | None
    support_intensity: str | None
    readiness_score: float | None
    blocking_prerequisite_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "concept_id": self.concept_id,
            "sequence": self.sequence,
            "path_status": self.path_status,
            "delivery_depth": self.delivery_depth,
            "mastery_score": self.mastery_score,
            "effective_mastery": self.effective_mastery,
            "confidence": self.confidence,
            "error_risk": self.error_risk,
            "support_need_score": self.support_need_score,
            "support_intensity": self.support_intensity,
            "readiness_score": self.readiness_score,
            "blocking_prerequisite_ids": list(self.blocking_prerequisite_ids),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class ProjectKTPlanningSupportReport:
    """从 KT 状态映射到规划优先级的项目侧桥接结果。"""

    schema_version: str
    profile_id: str
    graph_version: str
    generated_at: datetime
    path_id: str
    kt_policy_version: str
    path_node_count: int
    signals: tuple[ProjectKTPlanningSignal, ...]
    remediation_queue: tuple[str, ...]
    available_queue: tuple[str, ...]
    blocked_count: int
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "graph_version": self.graph_version,
            "generated_at": self.generated_at.isoformat(),
            "path_id": self.path_id,
            "kt_policy_version": self.kt_policy_version,
            "path_node_count": self.path_node_count,
            "signals": [item.to_dict() for item in self.signals],
            "remediation_queue": list(self.remediation_queue),
            "available_queue": list(self.available_queue),
            "blocked_count": self.blocked_count,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class KGLearningPathPolicy:
    """知识图谱学习路径推荐的可审计评分策略。"""

    version: str = "kg-learning-path-policy.v1"
    mastery_gap_weight: float = 0.42
    confidence_gap_weight: float = 0.16
    error_risk_weight: float = 0.18
    prerequisite_gap_weight: float = 0.18
    soft_prerequisite_weight: float = 0.08
    confusion_relation_weight: float = 0.10
    contrast_relation_weight: float = 0.04
    path_availability_weight: float = 0.06
    max_recommendations: int = 12
    minimum_reliable_confidence: float = 0.60
    review_mastery_threshold: float = 0.70

    def __post_init__(self) -> None:
        for name in (
            "mastery_gap_weight",
            "confidence_gap_weight",
            "error_risk_weight",
            "prerequisite_gap_weight",
            "soft_prerequisite_weight",
            "confusion_relation_weight",
            "contrast_relation_weight",
            "path_availability_weight",
            "minimum_reliable_confidence",
            "review_mastery_threshold",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be within [0, 1]")
        if self.max_recommendations < 1:
            raise ValueError("max_recommendations must be positive")

    @property
    def digest(self) -> str:
        return stable_digest("kg_path_policy", self.__dict__)


@dataclass(frozen=True)
class KGLearningPathRecommendation:
    """知识图谱路径推荐中的单个概念候选。"""

    concept_id: str
    rank: int
    score: float
    path_status: str
    recommendation_kind: str
    target_concept_ids: tuple[str, ...]
    prerequisite_gap_ids: tuple[str, ...]
    relation_kinds: tuple[str, ...]
    explanation_paths: tuple[str, ...]
    mastery_score: float | None
    effective_mastery: float | None
    confidence: float | None
    error_risk: float
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "concept_id": self.concept_id,
            "rank": self.rank,
            "score": self.score,
            "path_status": self.path_status,
            "recommendation_kind": self.recommendation_kind,
            "target_concept_ids": list(self.target_concept_ids),
            "prerequisite_gap_ids": list(self.prerequisite_gap_ids),
            "relation_kinds": list(self.relation_kinds),
            "explanation_paths": list(self.explanation_paths),
            "mastery_score": self.mastery_score,
            "effective_mastery": self.effective_mastery,
            "confidence": self.confidence,
            "error_risk": self.error_risk,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class KGLearningPathRecommendationReport:
    """基于 KT 画像和知识图谱的学习路径推荐报告。"""

    schema_version: str
    profile_id: str
    graph_version: str
    generated_at: datetime
    policy_version: str
    policy_digest: str
    target_concept_ids: tuple[str, ...]
    recommendations: tuple[KGLearningPathRecommendation, ...]
    blocked_target_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "graph_version": self.graph_version,
            "generated_at": self.generated_at.isoformat(),
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
            "target_concept_ids": list(self.target_concept_ids),
            "recommendations": [item.to_dict() for item in self.recommendations],
            "blocked_target_ids": list(self.blocked_target_ids),
            "reason_codes": list(self.reason_codes),
        }


class KnowledgeTracingEngine:
    """带有可选遗忘机制的实验性 BKT 引擎。"""

    def __init__(
        self,
        bkt_parameters: BKTParameters | None = None,
        forgetting_parameters: ForgettingParameters | None = None,
    ) -> None:
        self.bkt_parameters = bkt_parameters or BKTParameters()
        self.forgetting_parameters = forgetting_parameters or ForgettingParameters()

    def apply_event(self, ledger: KTLedger, event: KTEvent) -> KTUpdateResult:
        return self.apply_event_with_parameter_resolver(ledger, event)

    def apply_event_with_parameter_resolver(
        self,
        ledger: KTLedger,
        event: KTEvent,
        parameter_resolver: Callable[[str], BKTParameters] | None = None,
    ) -> KTUpdateResult:
        self._validate_scope(ledger, event)
        event_digest = event.digest
        existing_digest = ledger.processed_events.get(event.event_id)
        if existing_digest is not None:
            if existing_digest != event_digest:
                raise ValueError("event_id was already processed with different content")
            return KTUpdateResult(
                ledger=ledger,
                applied=False,
                event_digest=event_digest,
                bkt_policy_digest=self.bkt_parameters.digest,
                forgetting_policy_digest=self.forgetting_parameters.digest,
                reason_codes=("duplicate_event",),
            )

        states = dict(ledger.concept_states)
        updates: list[ConceptUpdate] = []
        for concept_id in event.concept_ids:
            concept_params = (
                parameter_resolver(concept_id)
                if parameter_resolver is not None
                else self.bkt_parameters
            )
            previous = states.get(concept_id) or self._cold_start_state(
                concept_id,
                concept_params,
            )
            updated, update = self._update_concept(previous, event, concept_params)
            states[concept_id] = updated
            updates.append(update)

        processed_events = dict(ledger.processed_events)
        processed_events[event.event_id] = event_digest
        return KTUpdateResult(
            ledger=KTLedger(
                profile_id=ledger.profile_id,
                graph_version=ledger.graph_version,
                concept_states=states,
                processed_events=processed_events,
            ),
            applied=True,
            event_digest=event_digest,
            bkt_policy_digest=self.bkt_parameters.digest,
            forgetting_policy_digest=self.forgetting_parameters.digest,
            concept_updates=tuple(updates),
            reason_codes=("bkt_update_applied",),
        )

    def predict_correct_probability(
        self,
        state: KTConceptState | None,
        at_time: datetime | None = None,
    ) -> float:
        current = state or self._cold_start_state("__cold_start__")
        mastery = (
            self.effective_mastery(current, at_time)
            if at_time is not None
            else current.mastery_score
        )
        params = self.bkt_parameters
        return clamp_probability(
            mastery * (1 - params.slip_probability)
            + (1 - mastery) * params.guess_probability
        )

    def effective_mastery(self, state: KTConceptState, at_time: datetime) -> float:
        params = self.forgetting_parameters
        if not params.enabled or state.last_observed_at is None:
            return state.mastery_score
        if at_time < state.last_observed_at:
            raise ValueError("at_time cannot be earlier than last observation")
        elapsed_days = (at_time - state.last_observed_at).total_seconds() / 86400
        resistance = (
            1.0
            + math.log1p(state.evidence_count) * params.evidence_resistance_weight
            + state.confidence * params.confidence_resistance_weight
        )
        decayed = state.mastery_score * math.exp(
            -params.decay_rate_per_day * elapsed_days / resistance
        )
        return clamp_probability(max(params.prior_floor, decayed))

    def _validate_scope(self, ledger: KTLedger, event: KTEvent) -> None:
        if ledger.profile_id != event.profile_id:
            raise ValueError("event profile_id does not match ledger")
        if ledger.graph_version != event.graph_version:
            raise ValueError("event graph_version does not match ledger")

    def _cold_start_state(
        self,
        concept_id: str,
        params: BKTParameters | None = None,
    ) -> KTConceptState:
        active_params = params or self.bkt_parameters
        return KTConceptState(
            concept_id=concept_id,
            mastery_score=active_params.prior_mastery,
            confidence=0.0,
            evidence_count=0,
            parameter_version=active_params.version,
        )

    def _update_concept(
        self,
        previous: KTConceptState,
        event: KTEvent,
        params: BKTParameters,
    ) -> tuple[KTConceptState, ConceptUpdate]:
        effective_before = self.effective_mastery(previous, event.timestamp)
        guess_probability, slip_probability, observation_reasons = (
            _adjusted_observation_parameters(params, event)
        )
        posterior = bkt_posterior(
            prior_mastery=effective_before,
            correct=event.correct,
            guess_probability=guess_probability,
            slip_probability=slip_probability,
        )
        mastery_after = bkt_learning_transition(posterior, params.learn_probability)
        confidence_after = _updated_confidence(previous, params)
        error_counts = Counter(previous.error_counts)
        classified_error = None if event.correct else classify_error(event)
        if classified_error is not None:
            error_counts[classified_error] += 1
        evidence_refs = _unique_refs(
            previous.evidence_refs,
            (event.event_id,),
            event.evidence_refs,
        )
        snapshot_payload = {
            "previous": state_to_dict(previous),
            "event": event_to_dict(event),
            "effective_mastery_before": effective_before,
            "bkt_policy_digest": params.digest,
            "forgetting_policy_digest": self.forgetting_parameters.digest,
        }
        updated = KTConceptState(
            concept_id=previous.concept_id,
            mastery_score=mastery_after,
            confidence=confidence_after,
            evidence_count=previous.evidence_count + 1,
            last_observed_at=event.timestamp,
            evidence_refs=evidence_refs,
            error_counts=dict(error_counts),
            model_version="bkt.v1",
            parameter_version=params.version,
            input_snapshot_digest=stable_digest("kt_input", snapshot_payload),
        )
        reasons = ["correct_observation" if event.correct else "incorrect_observation"]
        if previous.evidence_count == 0:
            reasons.append("cold_start_prior_used")
        if effective_before < previous.mastery_score:
            reasons.append("forgetting_decay_applied")
        if event.correct and (event.hint_count > 0 or event.attempt_count > 1):
            reasons.append("assisted_correct_answer_downweighted")
        if classified_error is not None:
            reasons.append(f"error_classified_{classified_error}")
        if params.version != self.bkt_parameters.version:
            reasons.append("concept_difficulty_adjusted")
        reasons.extend(observation_reasons)
        return updated, ConceptUpdate(
            concept_id=previous.concept_id,
            mastery_before=previous.mastery_score,
            mastery_after=updated.mastery_score,
            effective_mastery_before=effective_before,
            confidence_before=previous.confidence,
            confidence_after=updated.confidence,
            error_risk_after=updated.error_risk,
            reason_codes=tuple(reasons),
        )


def bkt_posterior(
    *,
    prior_mastery: float,
    correct: bool,
    guess_probability: float,
    slip_probability: float,
) -> float:
    """BKT 学习转移之前的贝叶斯观测后验计算。"""
    p = clamp_probability(prior_mastery)
    guess = clamp_probability(guess_probability)
    slip = clamp_probability(slip_probability)
    if correct:
        numerator = p * (1 - slip)
        denominator = numerator + (1 - p) * guess
    else:
        numerator = p * slip
        denominator = numerator + (1 - p) * (1 - guess)
    if denominator == 0:
        return p
    return clamp_probability(numerator / denominator)


def bkt_learning_transition(posterior_mastery: float, learn_probability: float) -> float:
    posterior = clamp_probability(posterior_mastery)
    learn = clamp_probability(learn_probability)
    return clamp_probability(posterior + (1 - posterior) * learn)


def difficulty_adjusted_bkt_parameters(
    base: BKTParameters,
    *,
    difficulty: int,
    policy: KnowledgeTracingPolicy,
) -> BKTParameters:
    """根据课程图谱中的知识点难度调整 BKT 参数。"""
    if not 1 <= difficulty <= 4:
        raise ValueError("concept difficulty must be within [1, 4]")
    if not policy.enable_concept_difficulty_adjustment:
        return base

    centered = difficulty - 2.5
    return replace(
        base,
        version=f"{base.version}.difficulty-d{difficulty}",
        prior_mastery=clamp_probability(
            base.prior_mastery - centered * policy.prior_difficulty_weight
        ),
        learn_probability=clamp_probability(
            base.learn_probability - centered * policy.learn_difficulty_weight
        ),
        guess_probability=clamp_probability(
            base.guess_probability + centered * policy.guess_difficulty_weight
        ),
        slip_probability=clamp_probability(
            base.slip_probability + centered * policy.slip_difficulty_weight
        ),
    )


def classify_error(event: KTEvent) -> ErrorKind:
    if event.error_kind is not None:
        return event.error_kind
    if event.hint_count >= 2:
        return "concept_confusion"
    if event.response_time_ms >= 120000:
        return "logic_gap"
    if event.attempt_count >= 2:
        return "calculation_error"
    return "missed_condition"


def evaluate_bkt_sequence(
    records: Sequence[PredictionRecord],
    parameters: BKTParameters,
    forgetting: ForgettingParameters | None = None,
) -> EvaluationMetrics:
    """使用在线 BKT 更新评估下一次作答预测。"""
    probabilities, labels = predict_bkt_sequence(records, parameters, forgetting)
    return prediction_metrics(probabilities, labels)


def predict_bkt_sequence(
    records: Sequence[PredictionRecord],
    parameters: BKTParameters,
    forgetting: ForgettingParameters | None = None,
) -> tuple[tuple[float, ...], tuple[int, ...]]:
    """返回在线下一次作答概率和二值标签。"""
    engine = KnowledgeTracingEngine(parameters, forgetting or ForgettingParameters(enabled=False))
    ledger = KTLedger(profile_id="offline-eval", graph_version="offline")
    probabilities: list[float] = []
    labels: list[int] = []
    for index, record in enumerate(records):
        state = ledger.concept_states.get(record.concept_id)
        probabilities.append(engine.predict_correct_probability(state, record.timestamp))
        labels.append(1 if record.correct else 0)
        event = KTEvent(
            event_id=f"offline-event-{index}",
            profile_id=ledger.profile_id,
            graph_version=ledger.graph_version,
            concept_ids=(record.concept_id,),
            correct=record.correct,
            timestamp=record.timestamp,
            hint_count=record.hint_count,
            attempt_count=record.attempt_count,
        )
        ledger = engine.apply_event(ledger, event).ledger
    return tuple(probabilities), tuple(labels)


def prediction_metrics(
    probabilities: Sequence[float],
    labels: Sequence[int],
) -> EvaluationMetrics:
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels must have the same length")
    if not probabilities:
        raise ValueError("at least one prediction is required")
    eps = 1e-12
    clipped = [min(1 - eps, max(eps, probability)) for probability in probabilities]
    brier = sum(
        (probability - label) ** 2
        for probability, label in zip(clipped, labels, strict=False)
    ) / len(labels)
    log_loss = -sum(
        label * math.log(probability) + (1 - label) * math.log(1 - probability)
        for probability, label in zip(clipped, labels, strict=False)
    ) / len(labels)
    accuracy = sum(
        (probability >= 0.5) == bool(label)
        for probability, label in zip(clipped, labels, strict=False)
    ) / len(labels)
    return EvaluationMetrics(
        count=len(labels),
        brier_score=round(brier, 8),
        log_loss=round(log_loss, 8),
        accuracy_at_half=round(accuracy, 8),
        expected_calibration_error=round(expected_calibration_error(clipped, labels), 8),
    )


def calibration_bins(
    probabilities: Sequence[float],
    labels: Sequence[int],
    *,
    bin_count: int = 10,
) -> tuple[CalibrationBin, ...]:
    """用于校准分析的可靠性分箱表。"""
    if bin_count < 1:
        raise ValueError("bin_count must be positive")
    if len(probabilities) != len(labels):
        raise ValueError("probabilities and labels must have the same length")
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bin_count)]
    for probability, label in zip(probabilities, labels, strict=False):
        p = clamp_probability(probability)
        index = min(bin_count - 1, int(p * bin_count))
        buckets[index].append((p, int(label)))
    result: list[CalibrationBin] = []
    for index, bucket in enumerate(buckets):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        if not bucket:
            result.append(
                CalibrationBin(
                    lower=round(lower, 6),
                    upper=round(upper, 6),
                    count=0,
                    mean_prediction=0.0,
                    empirical_accuracy=0.0,
                    absolute_gap=0.0,
                )
            )
            continue
        mean_prediction = sum(item[0] for item in bucket) / len(bucket)
        empirical_accuracy = sum(item[1] for item in bucket) / len(bucket)
        result.append(
            CalibrationBin(
                lower=round(lower, 6),
                upper=round(upper, 6),
                count=len(bucket),
                mean_prediction=round(mean_prediction, 8),
                empirical_accuracy=round(empirical_accuracy, 8),
                absolute_gap=round(abs(mean_prediction - empirical_accuracy), 8),
            )
        )
    return tuple(result)


def expected_calibration_error(
    probabilities: Sequence[float],
    labels: Sequence[int],
    *,
    bin_count: int = 10,
) -> float:
    bins = calibration_bins(probabilities, labels, bin_count=bin_count)
    total = sum(item.count for item in bins)
    if total == 0:
        raise ValueError("at least one prediction is required")
    return sum(item.count * item.absolute_gap for item in bins) / total


def pfa_predict_correct_probability(
    state: PFAConceptState | None,
    params: PFAParameters,
    *,
    hint_count: int = 0,
    attempt_count: int = 1,
) -> float:
    """使用 PFA 风格的逻辑模型预测答对概率。"""
    active_state = state or PFAConceptState("__cold_start__")
    logit = (
        params.intercept
        + params.success_weight * active_state.successes
        + params.failure_weight * active_state.failures
        - params.hint_penalty * max(hint_count, 0)
        - params.retry_penalty * max(attempt_count - 1, 0)
    )
    return clamp_probability(_logistic(logit))


def predict_pfa_sequence(
    records: Sequence[PredictionRecord],
    params: PFAParameters | None = None,
) -> tuple[tuple[float, ...], tuple[int, ...]]:
    """按时间顺序回放记录，并输出 PFA 观测前预测。"""
    active_params = params or PFAParameters()
    states: dict[str, PFAConceptState] = {}
    probabilities: list[float] = []
    labels: list[int] = []
    for record in sorted(records, key=lambda item: item.timestamp):
        state = states.get(record.concept_id)
        probabilities.append(
            pfa_predict_correct_probability(
                state,
                active_params,
                hint_count=record.hint_count,
                attempt_count=record.attempt_count,
            )
        )
        labels.append(1 if record.correct else 0)
        previous = state or PFAConceptState(record.concept_id)
        states[record.concept_id] = PFAConceptState(
            concept_id=record.concept_id,
            successes=previous.successes + (1 if record.correct else 0),
            failures=previous.failures + (0 if record.correct else 1),
        )
    return tuple(probabilities), tuple(labels)


def evaluate_pfa_sequence(
    records: Sequence[PredictionRecord],
    params: PFAParameters | None = None,
) -> EvaluationMetrics:
    probabilities, labels = predict_pfa_sequence(records, params)
    return prediction_metrics(probabilities, labels)


def grid_search_pfa_parameters(
    records: Sequence[PredictionRecord],
    *,
    intercept_values: Iterable[float] = (-0.80, -0.40, 0.00),
    success_values: Iterable[float] = (0.55, 0.85, 1.15),
    failure_values: Iterable[float] = (-1.00, -0.65, -0.35),
    hint_penalty_values: Iterable[float] = (0.10, 0.18, 0.28),
    retry_penalty_values: Iterable[float] = (0.06, 0.12, 0.20),
    base: PFAParameters | None = None,
    top_k: int = 10,
) -> tuple[PFASearchResult, ...]:
    """PFA 基线的确定性网格搜索。"""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    seed = base or PFAParameters()
    results: list[PFASearchResult] = []
    for intercept, success, failure, hint_penalty, retry_penalty in product(
        intercept_values,
        success_values,
        failure_values,
        hint_penalty_values,
        retry_penalty_values,
    ):
        params = replace(
            seed,
            intercept=intercept,
            success_weight=success,
            failure_weight=failure,
            hint_penalty=hint_penalty,
            retry_penalty=retry_penalty,
        )
        results.append(
            PFASearchResult(
                parameters=params,
                metrics=evaluate_pfa_sequence(records, params),
            )
        )
    return tuple(
        sorted(
            results,
            key=lambda item: (item.metrics.log_loss, item.metrics.brier_score),
        )[:top_k]
    )


def compare_bkt_and_pfa(
    records: Sequence[PredictionRecord],
    *,
    dataset_id: str,
    bkt_parameters: BKTParameters | None = None,
    forgetting: ForgettingParameters | None = None,
    pfa_parameters: PFAParameters | None = None,
    selection_metric: Literal["log_loss", "brier_score"] = "log_loss",
) -> ModelComparisonResult:
    """在同一组时间顺序记录上比较 BKT 和 PFA。"""
    if not records:
        raise ValueError("records cannot be empty")
    if selection_metric not in {"log_loss", "brier_score"}:
        raise ValueError("unsupported selection metric")

    active_bkt = bkt_parameters or BKTParameters()
    active_forgetting = forgetting or ForgettingParameters(enabled=False)
    active_pfa = pfa_parameters or PFAParameters()
    bkt = ParameterSearchResult(
        parameters=active_bkt,
        forgetting=active_forgetting,
        metrics=evaluate_bkt_sequence(records, active_bkt, active_forgetting),
    )
    pfa = PFASearchResult(
        parameters=active_pfa,
        metrics=evaluate_pfa_sequence(records, active_pfa),
    )
    bkt_score = getattr(bkt.metrics, selection_metric)
    pfa_score = getattr(pfa.metrics, selection_metric)
    if math.isclose(bkt_score, pfa_score, rel_tol=1e-9, abs_tol=1e-9):
        preferred: Literal["bkt", "pfa", "tie"] = "tie"
    else:
        preferred = "bkt" if bkt_score < pfa_score else "pfa"
    return ModelComparisonResult(
        schema_version="kt-model-comparison.v1",
        dataset_id=dataset_id,
        record_count=len(records),
        bkt=bkt,
        pfa=pfa,
        preferred_model=preferred,
        selection_metric=selection_metric,
    )


def grid_search_bkt_parameters(
    records: Sequence[PredictionRecord],
    *,
    prior_values: Iterable[float] = (0.20, 0.35, 0.50),
    learn_values: Iterable[float] = (0.06, 0.12, 0.20),
    guess_values: Iterable[float] = (0.10, 0.20, 0.30),
    slip_values: Iterable[float] = (0.05, 0.10, 0.20),
    base: BKTParameters | None = None,
    forgetting: ForgettingParameters | None = None,
    top_k: int = 10,
) -> tuple[ParameterSearchResult, ...]:
    """面向早期合成数据或专家标注数据的确定性小网格搜索。"""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    seed = base or BKTParameters()
    active_forgetting = forgetting or ForgettingParameters(enabled=False)
    results: list[ParameterSearchResult] = []
    for prior, learn, guess, slip in product(
        prior_values,
        learn_values,
        guess_values,
        slip_values,
    ):
        params = replace(
            seed,
            prior_mastery=prior,
            learn_probability=learn,
            guess_probability=guess,
            slip_probability=slip,
        )
        metrics = evaluate_bkt_sequence(records, params, active_forgetting)
        results.append(
            ParameterSearchResult(
                parameters=params,
                forgetting=active_forgetting,
                metrics=metrics,
            )
        )
    results.sort(
        key=lambda item: (
            item.metrics.log_loss,
            item.metrics.brier_score,
            item.parameters.prior_mastery,
            item.parameters.learn_probability,
            item.parameters.guess_probability,
            item.parameters.slip_probability,
        )
    )
    return tuple(results[:top_k])


def grid_search_forgetting_parameters(
    records: Sequence[PredictionRecord],
    *,
    bkt_parameters: BKTParameters | None = None,
    decay_values: Iterable[float] = (0.0, 0.006, 0.012, 0.018, 0.03),
    floor_values: Iterable[float] = (0.05, 0.15, 0.25),
    evidence_resistance_values: Iterable[float] = (0.0, 0.18, 0.35),
    confidence_resistance_values: Iterable[float] = (0.0, 0.50, 0.80),
    top_k: int = 10,
) -> tuple[ParameterSearchResult, ...]:
    """在固定 BKT 参数的情况下搜索遗忘参数。"""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    bkt = bkt_parameters or BKTParameters()
    results: list[ParameterSearchResult] = []
    for decay, floor_value, evidence_weight, confidence_weight in product(
        decay_values,
        floor_values,
        evidence_resistance_values,
        confidence_resistance_values,
    ):
        forgetting = ForgettingParameters(
            enabled=decay > 0,
            decay_rate_per_day=decay,
            prior_floor=floor_value,
            evidence_resistance_weight=evidence_weight,
            confidence_resistance_weight=confidence_weight,
        )
        metrics = evaluate_bkt_sequence(records, bkt, forgetting)
        results.append(
            ParameterSearchResult(
                parameters=bkt,
                forgetting=forgetting,
                metrics=metrics,
            )
        )
    results.sort(
        key=lambda item: (
            item.metrics.log_loss,
            item.metrics.brier_score,
            item.metrics.expected_calibration_error,
            item.forgetting.decay_rate_per_day,
            item.forgetting.prior_floor,
        )
    )
    return tuple(results[:top_k])


def two_stage_parameter_search(
    records: Sequence[PredictionRecord],
    *,
    bkt_top_k: int = 4,
    final_top_k: int = 5,
    validation_fraction: float = 0.30,
) -> tuple[ParameterSearchResult, ...]:
    """先搜索 BKT，再搜索遗忘参数，并按时间顺序验证集排序。"""
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between zero and one")
    train, validation = chronological_split(records, validation_fraction=validation_fraction)
    bkt_candidates = grid_search_bkt_parameters(train, top_k=bkt_top_k)
    candidates: list[ParameterSearchResult] = []
    for candidate in bkt_candidates:
        forgetting_candidates = grid_search_forgetting_parameters(
            train,
            bkt_parameters=candidate.parameters,
            top_k=max(1, min(final_top_k, 5)),
        )
        candidates.extend(forgetting_candidates)
    reranked: list[ParameterSearchResult] = []
    for candidate in candidates:
        metrics = evaluate_bkt_sequence(
            validation,
            candidate.parameters,
            candidate.forgetting,
        )
        reranked.append(
            ParameterSearchResult(
                parameters=candidate.parameters,
                forgetting=candidate.forgetting,
                metrics=metrics,
            )
        )
    reranked.sort(
        key=lambda item: (
            item.metrics.log_loss,
            item.metrics.brier_score,
            item.metrics.expected_calibration_error,
            item.parameters.prior_mastery,
        )
    )
    return tuple(reranked[:final_top_k])


def chronological_split(
    records: Sequence[PredictionRecord],
    *,
    validation_fraction: float = 0.30,
) -> tuple[tuple[PredictionRecord, ...], tuple[PredictionRecord, ...]]:
    if not records:
        raise ValueError("records cannot be empty")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between zero and one")
    ordered = tuple(sorted(records, key=lambda item: item.timestamp))
    validation_count = max(1, int(round(len(ordered) * validation_fraction)))
    if validation_count >= len(ordered):
        validation_count = len(ordered) - 1
    if validation_count < 1:
        raise ValueError("not enough records for train/validation split")
    return ordered[:-validation_count], ordered[-validation_count:]


def build_experiment_report(
    records: Sequence[PredictionRecord],
    *,
    dataset_id: str,
    dataset_kind: Literal["synthetic", "expert_labelled", "observed"],
    baseline_parameters: BKTParameters | None = None,
    baseline_forgetting: ForgettingParameters | None = None,
    ranked_candidates: Sequence[ParameterSearchResult] | None = None,
    top_k: int = 10,
) -> KnowledgeTracingExperimentReport:
    if not records:
        raise ValueError("records cannot be empty")
    baseline_bkt = baseline_parameters or BKTParameters()
    baseline_decay = baseline_forgetting or ForgettingParameters(enabled=False)
    baseline_metrics = evaluate_bkt_sequence(records, baseline_bkt, baseline_decay)
    baseline = ParameterSearchResult(
        parameters=baseline_bkt,
        forgetting=baseline_decay,
        metrics=baseline_metrics,
    )
    candidates = (
        tuple(ranked_candidates)
        if ranked_candidates is not None
        else grid_search_bkt_parameters(
            records,
            base=baseline_bkt,
            forgetting=baseline_decay,
            top_k=top_k,
        )
    )
    best = candidates[0] if candidates else baseline
    probabilities, labels = predict_bkt_sequence(
        records,
        best.parameters,
        best.forgetting,
    )
    return KnowledgeTracingExperimentReport(
        schema_version="knowledge-tracing-experiment-report.v1",
        dataset_id=dataset_id,
        dataset_kind=dataset_kind,
        generated_at=datetime.now(UTC),
        record_count=len(records),
        baseline=baseline,
        ranked_candidates=candidates,
        calibration_bins=calibration_bins(probabilities, labels),
        notes=(
            "Synthetic/offline metrics are regression evidence, not real teaching-effect claims.",
            "Promotion requires expert-labelled or observed data and path-invariant checks.",
        ),
    )


def build_validated_experiment_report(
    records: Sequence[PredictionRecord],
    *,
    dataset_id: str,
    dataset_kind: Literal["synthetic", "expert_labelled", "observed"],
    validation_fraction: float = 0.30,
    top_k: int = 10,
) -> KnowledgeTracingExperimentReport:
    """使用训练/验证拆分生成策略晋升式报告。"""
    train, validation = chronological_split(records, validation_fraction=validation_fraction)
    ranked = two_stage_parameter_search(
        records,
        final_top_k=top_k,
        validation_fraction=validation_fraction,
    )
    baseline_bkt = BKTParameters()
    baseline_forgetting = ForgettingParameters(enabled=False)
    baseline_validation = evaluate_bkt_sequence(
        validation,
        baseline_bkt,
        baseline_forgetting,
    )
    report = build_experiment_report(
        validation,
        dataset_id=dataset_id,
        dataset_kind=dataset_kind,
        baseline_parameters=baseline_bkt,
        baseline_forgetting=baseline_forgetting,
        ranked_candidates=ranked,
        top_k=top_k,
    )
    return KnowledgeTracingExperimentReport(
        schema_version=report.schema_version,
        dataset_id=report.dataset_id,
        dataset_kind=report.dataset_kind,
        generated_at=report.generated_at,
        record_count=len(records),
        baseline=ParameterSearchResult(
            parameters=baseline_bkt,
            forgetting=baseline_forgetting,
            metrics=baseline_validation,
        ),
        ranked_candidates=report.ranked_candidates,
        calibration_bins=report.calibration_bins,
        notes=(
            *report.notes,
            "Candidates were selected on the validation tail after tuning on earlier records.",
        ),
        validation={
            "validation_fraction": validation_fraction,
            "train_count": len(train),
            "validation_count": len(validation),
            "split": "chronological_tail",
        },
    )


def synthetic_bkt_records(
    *,
    concept_ids: Sequence[str],
    learner_count: int = 12,
    events_per_learner: int = 24,
    seed: int = 20260814,
    start_time: datetime | None = None,
    true_parameters: BKTParameters | None = None,
) -> tuple[PredictionRecord, ...]:
    """生成可复现的合成答题记录，用于算法回归测试。"""
    if not concept_ids:
        raise ValueError("concept_ids cannot be empty")
    if learner_count < 1:
        raise ValueError("learner_count must be positive")
    if events_per_learner < 1:
        raise ValueError("events_per_learner must be positive")
    rng = random.Random(seed)
    params = true_parameters or BKTParameters()
    timestamp = start_time or datetime(2026, 8, 14, tzinfo=UTC)
    records: list[PredictionRecord] = []
    latent: dict[tuple[int, str], float] = {}
    for learner_index in range(learner_count):
        for concept_id in concept_ids:
            latent[(learner_index, concept_id)] = clamp_probability(
                rng.betavariate(2.0, 3.0)
            )
        for event_index in range(events_per_learner):
            concept_id = concept_ids[(learner_index + event_index) % len(concept_ids)]
            key = (learner_index, concept_id)
            mastery = latent[key]
            p_correct = (
                mastery * (1 - params.slip_probability)
                + (1 - mastery) * params.guess_probability
            )
            correct = rng.random() < p_correct
            hint_count = 0 if correct and rng.random() > 0.18 else rng.randint(0, 2)
            attempt_count = 1 if correct and rng.random() > 0.12 else rng.randint(1, 3)
            records.append(
                PredictionRecord(
                    concept_id=concept_id,
                    correct=correct,
                    timestamp=timestamp
                    + timedelta(days=learner_index, hours=event_index * 6),
                    hint_count=hint_count,
                    attempt_count=attempt_count,
                    latent_mastery=round(mastery, 6),
                )
            )
            posterior = bkt_posterior(
                prior_mastery=mastery,
                correct=correct,
                guess_probability=params.guess_probability,
                slip_probability=params.slip_probability,
            )
            latent[key] = bkt_learning_transition(
                posterior,
                params.learn_probability,
            )
    return tuple(records)


def ledger_from_learner_profile(
    profile: object,
    *,
    processed_events: Mapping[str, str] | None = None,
) -> KTLedger:
    """读取项目中的 LearnerProfileSnapshot 风格对象并转成本 KT 账本。"""
    profile_id = str(_get_field(profile, "profile_id"))
    graph_version = str(_get_field(profile, "graph_version"))
    error_counts_by_concept: dict[str, Counter[str]] = {}
    for pattern in _get_field(profile, "error_patterns", default=()):
        code = str(_get_field(pattern, "code"))
        count = int(_get_field(pattern, "count", default=0))
        for concept_id in _get_field(pattern, "concept_ids", default=()):
            concept_counts = error_counts_by_concept.setdefault(str(concept_id), Counter())
            concept_counts[code] += count

    states: dict[str, KTConceptState] = {}
    for item in _get_field(profile, "knowledge_mastery", default=()):
        concept_id = str(_get_field(item, "concept_id"))
        mastery = _get_field(item, "mastery_score", default=None)
        confidence = _get_field(item, "confidence", default=0.0)
        observed_at = _get_field(item, "observed_at", default=None)
        evidence_refs = tuple(str(value) for value in _get_field(item, "evidence_refs", default=()))
        if mastery is None:
            continue
        states[concept_id] = KTConceptState(
            concept_id=concept_id,
            mastery_score=float(mastery),
            confidence=float(confidence),
            evidence_count=max(1, len(evidence_refs)),
            last_observed_at=observed_at,
            evidence_refs=evidence_refs,
            error_counts=dict(error_counts_by_concept.get(concept_id, Counter())),
            model_version="imported-profile",
            parameter_version="unknown",
        )
    return KTLedger(
        profile_id=profile_id,
        graph_version=graph_version,
        concept_states=states,
        processed_events=processed_events or {},
    )


def profile_with_kt_states(profile: object, ledger: KTLedger) -> object:
    """返回一个 knowledge_mastery 来自 KT 状态的画像副本。"""
    if str(_get_field(profile, "profile_id")) != ledger.profile_id:
        raise ValueError("profile_id does not match KT ledger")
    if str(_get_field(profile, "graph_version")) != ledger.graph_version:
        raise ValueError("graph_version does not match KT ledger")
    existing = {
        str(_get_field(item, "concept_id")): item
        for item in _get_field(profile, "knowledge_mastery", default=())
    }
    merged: list[object] = []
    seen: set[str] = set()
    for concept_id, item in existing.items():
        state = ledger.concept_states.get(concept_id)
        if state is None:
            merged.append(item)
        else:
            merged.append(_make_project_mastery_fact(state))
        seen.add(concept_id)
    for concept_id, state in sorted(ledger.concept_states.items()):
        if concept_id not in seen:
            merged.append(_make_project_mastery_fact(state))
    if hasattr(profile, "model_copy"):
        return profile.model_copy(update={"knowledge_mastery": merged}, deep=True)
    payload = _mapping_payload(profile)
    payload["knowledge_mastery"] = merged
    return payload


def event_from_project_assessment_event(
    event: object,
    item_metadata: AssessmentItemMetadata | ItemMetadataRegistry | None = None,
) -> KTEvent:
    """把现有 AssessmentEvent 契约转换为 KTEvent。"""
    metadata = _resolve_item_metadata(event, item_metadata)
    return KTEvent(
        event_id=str(_get_field(event, "event_id")),
        profile_id=str(_get_field(event, "profile_id")),
        graph_version=str(_get_field(event, "graph_version")),
        concept_ids=tuple(str(item) for item in _get_field(event, "concept_ids")),
        correct=bool(_get_field(event, "correct")),
        timestamp=_get_field(event, "timestamp"),
        response_time_ms=int(_get_field(event, "response_time_ms", default=0)),
        hint_count=int(_get_field(event, "hint_count", default=0)),
        attempt_count=int(_get_field(event, "attempt_count", default=1)),
        error_kind=_normalize_error_kind(_get_field(event, "error_kind", default=None)),
        evidence_refs=tuple(str(item) for item in _get_field(event, "evidence_refs", default=())),
        item_difficulty=metadata.difficulty if metadata is not None else None,
        item_discrimination=metadata.discrimination if metadata is not None else None,
        target_depth=metadata.target_depth if metadata is not None else None,
        expected_time_ms=metadata.expected_time_ms if metadata is not None else None,
    )


def apply_project_assessment_event(
    profile: object,
    event: object,
    *,
    processed_events: Mapping[str, str] | None = None,
    engine: KnowledgeTracingEngine | None = None,
    known_concept_ids: Iterable[str] | None = None,
    item_metadata: AssessmentItemMetadata | ItemMetadataRegistry | None = None,
) -> tuple[object, KTUpdateResult]:
    """将 KT 应用于项目形状的画像和事件对象，并返回画像副本。"""
    kt_event = event_from_project_assessment_event(event, item_metadata)
    if known_concept_ids is not None:
        unknown = set(kt_event.concept_ids) - set(known_concept_ids)
        if unknown:
            raise ValueError(f"unknown assessment concept: {sorted(unknown)[0]}")
    active_engine = engine or KnowledgeTracingEngine()
    ledger = ledger_from_learner_profile(profile, processed_events=processed_events)
    result = active_engine.apply_event(ledger, kt_event)
    return profile_with_kt_states(profile, result.ledger), result


def apply_bkt_assessment_event(
    catalog: OntologyCatalog,
    ledger: ProjectAssessmentLedger | Mapping[str, object],
    event: ProjectAssessmentEvent | Mapping[str, object],
    policy: KnowledgeTracingPolicy | None = None,
    item_metadata: AssessmentItemMetadata | ItemMetadataRegistry | None = None,
) -> ProjectAssessmentUpdateResult:
    """面向项目的 BKT 更新入口，可替代规则化评估更新器。"""
    from skillforge_kb.assessment.update import (
        AssessmentLedger,
        AssessmentUpdateResult,
        build_assessment_event_digest,
    )

    active_policy = policy or KnowledgeTracingPolicy()
    project_ledger = AssessmentLedger.model_validate(_model_dump(ledger))
    project_event = _validate_project_assessment_event(event)
    _validate_project_scope(catalog, project_ledger, project_event)
    event_digest = build_assessment_event_digest(project_event)
    if project_event.event_id in project_ledger.processed_event_ids:
        return AssessmentUpdateResult(
            ledger=project_ledger,
            policy_version=active_policy.version,
            policy_digest=active_policy.assessment_policy_digest,
            event_digest=event_digest,
            applied=False,
            reason_codes=("duplicate_event",),
        )

    engine = KnowledgeTracingEngine(
        active_policy.bkt,
        active_policy.forgetting,
    )
    kt_ledger = ledger_from_learner_profile(project_ledger.profile)
    kt_event = event_from_project_assessment_event(project_event, item_metadata)
    kt_result = engine.apply_event_with_parameter_resolver(
        kt_ledger,
        kt_event,
        _project_bkt_parameter_resolver(catalog, active_policy),
    )
    updated_profile = _profile_with_project_kt_result(
        project_ledger.profile,
        kt_result.ledger,
        affected_concept_ids=project_event.concept_ids,
    )
    updated_ledger = AssessmentLedger(
        profile=updated_profile,
        processed_event_ids=(
            *project_ledger.processed_event_ids,
            project_event.event_id,
        ),
    )
    updates_by_id = {item.concept_id: item for item in kt_result.concept_updates}
    mastery_before = tuple(
        (concept_id, updates_by_id[concept_id].mastery_before)
        for concept_id in project_event.concept_ids
    )
    mastery_after = tuple(
        (concept_id, updates_by_id[concept_id].mastery_after)
        for concept_id in project_event.concept_ids
    )
    classified_error = None if project_event.correct else classify_error(kt_event)
    reason_codes = tuple(
        dict.fromkeys(
            (
                "bkt_update_applied",
                "forgetting_enabled" if active_policy.forgetting.enabled else "forgetting_disabled",
                *(
                    code
                    for update in kt_result.concept_updates
                    for code in update.reason_codes
                ),
            )
        )
    )
    return AssessmentUpdateResult(
        ledger=updated_ledger,
        policy_version=active_policy.version,
        policy_digest=active_policy.assessment_policy_digest,
        event_digest=event_digest,
        applied=True,
        affected_concept_ids=project_event.concept_ids,
        mastery_before=mastery_before,
        mastery_after=mastery_after,
        classified_error_kind=_project_error_kind(classified_error),
        reason_codes=reason_codes,
    )


def apply_bkt_assessment_event_and_plan(
    catalog: OntologyCatalog,
    ledger: ProjectAssessmentLedger | Mapping[str, object],
    event: ProjectAssessmentEvent | Mapping[str, object],
    *,
    kt_policy: KnowledgeTracingPolicy | None = None,
    planner_policy: PlannerPolicy | None = None,
    item_metadata: AssessmentItemMetadata | ItemMetadataRegistry | None = None,
    completed_concept_ids: set[str] | None = None,
    allow_skips: bool = True,
) -> tuple[ProjectAssessmentUpdateResult, PathDecision]:
    """把 KT 应用到一次评估事件后，再基于更新画像生成规划。"""
    from skillforge_kb.planning.planner import CoursePlanner

    update_result = apply_bkt_assessment_event(
        catalog,
        ledger,
        event,
        policy=kt_policy,
        item_metadata=item_metadata,
    )
    decision = CoursePlanner(catalog, policy=planner_policy).plan(
        update_result.ledger.profile,
        completed_concept_ids=completed_concept_ids,
        allow_skips=allow_skips,
    )
    return update_result, decision


def replay_bkt_assessment_events(
    catalog: OntologyCatalog,
    ledger: ProjectAssessmentLedger | Mapping[str, object],
    events: Sequence[ProjectAssessmentEvent | Mapping[str, object]],
    *,
    policy: KnowledgeTracingPolicy | None = None,
    item_metadata: AssessmentItemMetadata | ItemMetadataRegistry | None = None,
    sort_chronologically: bool = True,
    state_fact_time: datetime | None = None,
) -> ProjectKTBatchUpdateResult:
    """将一段评估历史回放到最终项目账本中。"""
    from skillforge_kb.assessment.update import AssessmentLedger

    active_policy = policy or KnowledgeTracingPolicy()
    current = AssessmentLedger.model_validate(_model_dump(ledger))
    internal_engine = KnowledgeTracingEngine(active_policy.bkt, active_policy.forgetting)
    internal_ledger = ledger_from_learner_profile(current.profile)
    project_events = tuple(_validate_project_assessment_event(event) for event in events)
    ordered_events = (
        tuple(sorted(project_events, key=lambda item: item.timestamp))
        if sort_chronologically
        else project_events
    )
    results: list[ProjectAssessmentUpdateResult] = []
    for event in ordered_events:
        already_processed = event.event_id in current.processed_event_ids
        result = apply_bkt_assessment_event(
            catalog,
            current,
            event,
            policy=active_policy,
            item_metadata=item_metadata,
        )
        results.append(result)
        if result.applied and not already_processed:
            internal_ledger = internal_engine.apply_event_with_parameter_resolver(
                internal_ledger,
                event_from_project_assessment_event(event, item_metadata),
                _project_bkt_parameter_resolver(catalog, active_policy),
            ).ledger
        current = result.ledger

    facts = kt_state_facts(
        internal_ledger,
        at_time=state_fact_time,
        policy=active_policy,
    )
    applied_count = sum(1 for item in results if item.applied)
    duplicate_count = sum(1 for item in results if not item.applied)
    return ProjectKTBatchUpdateResult(
        final_ledger=current,
        event_results=tuple(results),
        kt_state_facts=facts,
        applied_count=applied_count,
        duplicate_count=duplicate_count,
        reason_codes=tuple(
            _unique_strings(
                [
                    "assessment_history_replayed",
                    *(("duplicate_events_seen",) if duplicate_count else ()),
                ]
            )
        ),
    )


def kt_state_facts(
    ledger: KTLedger,
    *,
    at_time: datetime | None = None,
    policy: KnowledgeTracingPolicy | None = None,
) -> tuple[KTStateFact, ...]:
    """返回任务书要求的每个已追踪知识点 KT 事实。"""
    active_policy = policy or KnowledgeTracingPolicy()
    engine = KnowledgeTracingEngine(active_policy.bkt, active_policy.forgetting)
    fact_time = at_time or datetime.now(UTC)
    facts: list[KTStateFact] = []
    for concept_id, state in sorted(ledger.concept_states.items()):
        effective_mastery = engine.effective_mastery(state, fact_time)
        facts.append(
            KTStateFact(
                concept_id=concept_id,
                mastery_score=round(state.mastery_score, 6),
                effective_mastery=round(effective_mastery, 6),
                confidence=round(state.confidence, 6),
                error_risk=round(state.error_risk, 6),
                evidence_count=state.evidence_count,
                model_version=state.model_version,
                parameter_version=state.parameter_version,
                input_snapshot_digest=state.input_snapshot_digest,
                reason_codes=_kt_state_reason_codes(
                    state,
                    effective_mastery=effective_mastery,
                    policy=active_policy,
                ),
                updated_at=state.last_observed_at,
            )
        )
    return tuple(facts)


def build_kt_planning_support_report(
    catalog: OntologyCatalog,
    profile: LearnerProfileSnapshot,
    *,
    kt_policy: KnowledgeTracingPolicy | None = None,
    planner_policy: PlannerPolicy | None = None,
    node_weight_policy: NodeWeightPolicy | None = None,
    attributes: ConceptAttributeCatalog | None = None,
    completed_concept_ids: set[str] | None = None,
    allow_skips: bool = True,
    at_time: datetime | None = None,
) -> ProjectKTPlanningSupportReport:
    """在不改变路径的前提下，构建带 KT 信息的规划优先级。"""
    from skillforge_kb.ontology.concept_attributes import load_concept_attributes
    from skillforge_kb.planning.adaptation import NodeWeightEngine
    from skillforge_kb.planning.models import PathStatus
    from skillforge_kb.planning.planner import CoursePlanner

    active_kt_policy = kt_policy or KnowledgeTracingPolicy()
    generated_at = at_time or datetime.now(UTC)
    decision = CoursePlanner(catalog, policy=planner_policy).plan(
        profile,
        completed_concept_ids=completed_concept_ids,
        allow_skips=allow_skips,
    )
    active_attributes = attributes or load_concept_attributes(
        catalog,
        _default_concept_attributes_path(),
    )
    weight_engine = NodeWeightEngine(
        catalog,
        active_attributes,
        policy=planner_policy,
        node_weight_policy=node_weight_policy,
    )
    facts_by_id = {
        fact.concept_id: fact
        for fact in kt_state_facts(
            ledger_from_learner_profile(profile),
            at_time=generated_at,
            policy=active_kt_policy,
        )
    }
    error_risk_by_id = _profile_error_risk_index(profile)
    signals: list[ProjectKTPlanningSignal] = []
    for node in decision.nodes:
        fact = facts_by_id.get(node.concept_id)
        adaptation = None
        if (
            node.status not in {PathStatus.SKIPPED, PathStatus.COMPLETED}
            and node.delivery_depth is not None
        ):
            adaptation = weight_engine.evaluate(
                profile,
                node,
                completed_concept_ids=completed_concept_ids,
            )
        node_reasons = tuple(str(getattr(code, "value", code)) for code in node.reason_codes)
        fact_reasons = fact.reason_codes if fact is not None else ("kt_mastery_missing",)
        adaptation_reasons = (
            tuple(str(code) for code in adaptation.reason_codes)
            if adaptation is not None
            else ()
        )
        signals.append(
            ProjectKTPlanningSignal(
                concept_id=node.concept_id,
                sequence=node.sequence,
                path_status=str(getattr(node.status, "value", node.status)),
                delivery_depth=(
                    str(getattr(node.delivery_depth, "value", node.delivery_depth))
                    if node.delivery_depth is not None
                    else None
                ),
                mastery_score=fact.mastery_score if fact is not None else None,
                effective_mastery=fact.effective_mastery if fact is not None else None,
                confidence=fact.confidence if fact is not None else None,
                error_risk=(
                    fact.error_risk
                    if fact is not None
                    else error_risk_by_id.get(node.concept_id, 0.0)
                ),
                support_need_score=(
                    adaptation.support_need_score if adaptation is not None else None
                ),
                support_intensity=(
                    str(
                        getattr(
                            adaptation.support_intensity,
                            "value",
                            adaptation.support_intensity,
                        )
                    )
                    if adaptation is not None
                    else None
                ),
                readiness_score=adaptation.readiness_score if adaptation is not None else None,
                blocking_prerequisite_ids=tuple(node.blocking_prerequisite_ids),
                reason_codes=tuple(
                    _unique_strings([*node_reasons, *fact_reasons, *adaptation_reasons])
                ),
            )
        )
    remediation_queue = tuple(
        item.concept_id
        for item in sorted(
            (
                signal
                for signal in signals
                if _needs_kt_remediation(signal)
            ),
            key=_remediation_sort_key,
        )
    )
    available_queue = tuple(
        signal.concept_id
        for signal in signals
        if signal.path_status == "available"
    )
    blocked_count = sum(1 for signal in signals if signal.path_status == "blocked")
    return ProjectKTPlanningSupportReport(
        schema_version="project-kt-planning-support-report.v1",
        profile_id=profile.profile_id,
        graph_version=profile.graph_version,
        generated_at=generated_at,
        path_id=decision.path_id,
        kt_policy_version=active_kt_policy.version,
        path_node_count=len(decision.nodes),
        signals=tuple(signals),
        remediation_queue=remediation_queue,
        available_queue=available_queue,
        blocked_count=blocked_count,
        reason_codes=(
            "kt_profile_analyzed",
            "planner_path_preserved",
            "node_weight_support_scored",
        ),
    )


def recommend_kg_learning_path(
    catalog: OntologyCatalog,
    profile: LearnerProfileSnapshot,
    *,
    target_concept_ids: Sequence[str] | None = None,
    completed_concept_ids: set[str] | None = None,
    kt_policy: KnowledgeTracingPolicy | None = None,
    planner_policy: PlannerPolicy | None = None,
    recommendation_policy: KGLearningPathPolicy | None = None,
    at_time: datetime | None = None,
    max_recommendations: int | None = None,
) -> KGLearningPathRecommendationReport:
    """基于 KT 画像和课程知识图谱推荐下一批学习概念。"""
    from skillforge_kb.planning.models import PathStatus
    from skillforge_kb.planning.planner import CoursePlanner

    active_kt_policy = kt_policy or KnowledgeTracingPolicy()
    active_policy = recommendation_policy or KGLearningPathPolicy()
    generated_at = at_time or datetime.now(UTC)
    known_ids = {concept.id for concept in catalog.concepts()}
    targets = tuple(dict.fromkeys(target_concept_ids or ()))
    unknown_targets = [concept_id for concept_id in targets if concept_id not in known_ids]
    if unknown_targets:
        raise ValueError(f"unknown target concept: {unknown_targets[0]}")

    completed = completed_concept_ids or set()
    decision = CoursePlanner(catalog, policy=planner_policy).plan(
        profile,
        completed_concept_ids=completed,
        allow_skips=True,
    )
    hard_prerequisites = _hard_prerequisite_index(catalog)
    facts_by_id = {
        fact.concept_id: fact
        for fact in kt_state_facts(
            ledger_from_learner_profile(profile),
            at_time=generated_at,
            policy=active_kt_policy,
        )
    }
    target_gap_index = _target_prerequisite_gap_index(
        targets,
        hard_prerequisites,
        facts_by_id,
        completed,
        active_policy,
    )
    candidate_target_map = _candidate_target_map(target_gap_index)
    relation_candidate_map = _kg_relation_candidate_map(catalog, targets)
    blocked_targets = tuple(
        target for target, gaps in target_gap_index.items() if gaps
    )
    scored: list[tuple[float, int, KGLearningPathRecommendation]] = []
    max_items = max_recommendations or active_policy.max_recommendations
    for node in decision.nodes:
        if node.status in {PathStatus.SKIPPED, PathStatus.COMPLETED}:
            continue
        target_links = candidate_target_map.get(node.concept_id, ())
        relation_context = relation_candidate_map.get(node.concept_id, ())
        relation_target_links = tuple(item[0] for item in relation_context)
        if (
            targets
            and node.concept_id not in targets
            and not target_links
            and not relation_context
        ):
            continue
        fact = facts_by_id.get(node.concept_id)
        prerequisite_gaps = tuple(
            concept_id
            for concept_id in _direct_prerequisite_gaps(
                node.concept_id,
                hard_prerequisites,
                facts_by_id,
                completed,
                active_policy,
            )
        )
        score, reasons, kind = _score_kg_candidate(
            node_status=str(getattr(node.status, "value", node.status)),
            fact=fact,
            prerequisite_gap_ids=prerequisite_gaps,
            linked_target_ids=target_links,
            relation_kinds=tuple(item[1] for item in relation_context),
            is_explicit_target=node.concept_id in targets,
            policy=active_policy,
        )
        explicit_target_links = ((node.concept_id,) if node.concept_id in targets else ())
        recommendation_targets = _unique_strings(
            [*target_links, *relation_target_links, *explicit_target_links]
        )
        recommendation = KGLearningPathRecommendation(
            concept_id=node.concept_id,
            rank=0,
            score=round(score, 6),
            path_status=str(getattr(node.status, "value", node.status)),
            recommendation_kind=kind,
            target_concept_ids=recommendation_targets,
            prerequisite_gap_ids=prerequisite_gaps,
            relation_kinds=_unique_strings(item[1] for item in relation_context),
            explanation_paths=tuple(item[2] for item in relation_context),
            mastery_score=fact.mastery_score if fact is not None else None,
            effective_mastery=fact.effective_mastery if fact is not None else None,
            confidence=fact.confidence if fact is not None else None,
            error_risk=fact.error_risk if fact is not None else 0.0,
            reason_codes=tuple(
                _unique_strings(
                    [
                        *reasons,
                        *(str(getattr(code, "value", code)) for code in node.reason_codes),
                    ]
                )
            ),
        )
        scored.append((-score, node.sequence, recommendation))

    ranked = []
    for rank, (_neg_score, _sequence, item) in enumerate(sorted(scored)[:max_items], start=1):
        ranked.append(replace(item, rank=rank))

    return KGLearningPathRecommendationReport(
        schema_version="kg-learning-path-recommendation-report.v1",
        profile_id=profile.profile_id,
        graph_version=profile.graph_version,
        generated_at=generated_at,
        policy_version=active_policy.version,
        policy_digest=active_policy.digest,
        target_concept_ids=targets,
        recommendations=tuple(ranked),
        blocked_target_ids=blocked_targets,
        reason_codes=(
            "kt_mastery_used",
            "knowledge_graph_prerequisites_used",
            "hard_prerequisites_preserved",
        ),
    )


def build_project_kt_optimization_report(
    catalog: OntologyCatalog,
    policy: KnowledgeTracingPolicy | None = None,
) -> ProjectKTOptimizationReport:
    """总结本项目已实现和建议继续实现的 KT 优化。"""
    active_policy = policy or KnowledgeTracingPolicy()
    concepts = catalog.concepts()
    difficulty_counts = Counter(
        str(int(_get_field(concept, "difficulty")))
        for concept in concepts
    )
    implemented = (
        "bayesian_knowledge_tracing_mastery_update",
        "forgetting_aware_effective_mastery",
        "hint_retry_assisted_correct_downweighting",
        "ontology_difficulty_adjusted_bkt_parameters",
        "performance_factors_analysis_baseline",
        "bkt_pfa_offline_model_comparison",
        "knowledge_graph_prerequisite_constrained_recommendation",
        "kt_based_learning_path_priority_queue",
        "project_assessment_result_contract_bridge",
        "planner_safe_profile_only_update",
    )
    recommended = (
        "collect expert-labelled assessment logs and calibrate difficulty weights",
        "add item-level difficulty/discrimination metadata when assessment items are available",
        "select BKT or PFA policy by log_loss, brier_score, and calibration error",
        "calibrate KG recommendation weights with expert-labelled target paths",
        "keep DKT/AKT/SAKT as later candidates until interaction data is large enough",
        "validate every promoted policy with path-invariant and prerequisite-safety tests",
    )
    anchors = (
        "Corbett-Anderson Bayesian Knowledge Tracing",
        "Pardos-Heffernan individualized BKT",
        "Pavlik-Cen-Koedinger Performance Factors Analysis",
        "Qiu et al. time-aware BKT",
        "Piech et al. Deep Knowledge Tracing",
        "Ghosh et al. Attentive Knowledge Tracing",
    )
    return ProjectKTOptimizationReport(
        schema_version="project-kt-optimization-report.v1",
        policy_version=active_policy.version,
        concept_count=len(concepts),
        difficulty_counts=dict(sorted(difficulty_counts.items())),
        implemented_optimizations=implemented,
        recommended_next_steps=recommended,
        paper_anchors=anchors,
    )


def planning_feature_table(
    ledger: KTLedger,
    *,
    at_time: datetime | None = None,
    engine: KnowledgeTracingEngine | None = None,
) -> tuple[dict[str, object], ...]:
    """返回对路径规划有用、但不修改路径的事实。"""
    active_engine = engine or KnowledgeTracingEngine()
    rows: list[dict[str, object]] = []
    for _concept_id, state in sorted(ledger.concept_states.items()):
        row = state.planning_features(at_time)
        if at_time is not None:
            row["effective_mastery"] = round(active_engine.effective_mastery(state, at_time), 6)
        row["low_confidence"] = (
            state.confidence < active_engine.bkt_parameters.minimum_observed_confidence
        )
        rows.append(row)
    return tuple(rows)


def save_json(path: str | Path, payload: object) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = payload.to_dict() if isinstance(payload, SupportsToDict) else payload
    destination.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    return destination


def load_ledger_json(path: str | Path) -> KTLedger:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("ledger JSON root must be an object")
    return KTLedger.from_dict(payload)


def _hard_prerequisite_index(catalog: OntologyCatalog) -> dict[str, tuple[object, ...]]:
    from skillforge_kb.ontology.models import RelationKind

    result: dict[str, list[object]] = {}
    for relation in catalog.relations(RelationKind.HARD_PREREQUISITE):
        result.setdefault(str(_get_field(relation, "target")), []).append(relation)
    return {
        concept_id: tuple(sorted(relations, key=lambda item: str(_get_field(item, "source"))))
        for concept_id, relations in result.items()
    }


def _target_prerequisite_gap_index(
    targets: Sequence[str],
    hard_prerequisites: Mapping[str, Sequence[object]],
    facts_by_id: Mapping[str, KTStateFact],
    completed_concept_ids: set[str],
    policy: KGLearningPathPolicy,
) -> dict[str, tuple[str, ...]]:
    return {
        target: tuple(
            _recursive_prerequisite_gaps(
                target,
                hard_prerequisites,
                facts_by_id,
                completed_concept_ids,
                policy,
                seen=set(),
            )
        )
        for target in targets
    }


def _recursive_prerequisite_gaps(
    concept_id: str,
    hard_prerequisites: Mapping[str, Sequence[object]],
    facts_by_id: Mapping[str, KTStateFact],
    completed_concept_ids: set[str],
    policy: KGLearningPathPolicy,
    *,
    seen: set[str],
) -> tuple[str, ...]:
    if concept_id in seen:
        return ()
    seen.add(concept_id)
    gaps: list[str] = []
    for relation in hard_prerequisites.get(concept_id, ()):
        source = str(_get_field(relation, "source"))
        if _kg_prerequisite_satisfied(source, relation, facts_by_id, completed_concept_ids, policy):
            continue
        gaps.extend(
            _recursive_prerequisite_gaps(
                source,
                hard_prerequisites,
                facts_by_id,
                completed_concept_ids,
                policy,
                seen=seen,
            )
        )
        gaps.append(source)
    return _unique_strings(gaps)


def _direct_prerequisite_gaps(
    concept_id: str,
    hard_prerequisites: Mapping[str, Sequence[object]],
    facts_by_id: Mapping[str, KTStateFact],
    completed_concept_ids: set[str],
    policy: KGLearningPathPolicy,
) -> tuple[str, ...]:
    gaps: list[str] = []
    for relation in hard_prerequisites.get(concept_id, ()):
        source = str(_get_field(relation, "source"))
        if not _kg_prerequisite_satisfied(
            source,
            relation,
            facts_by_id,
            completed_concept_ids,
            policy,
        ):
            gaps.append(source)
    return _unique_strings(gaps)


def _kg_prerequisite_satisfied(
    concept_id: str,
    relation: object,
    facts_by_id: Mapping[str, KTStateFact],
    completed_concept_ids: set[str],
    policy: KGLearningPathPolicy,
) -> bool:
    if concept_id in completed_concept_ids:
        return True
    fact = facts_by_id.get(concept_id)
    if fact is None or fact.effective_mastery is None or fact.confidence is None:
        return False
    min_mastery = _get_field(relation, "min_mastery", default=None)
    threshold = (
        float(cast(Any, min_mastery))
        if min_mastery is not None
        else policy.review_mastery_threshold
    )
    return (
        fact.effective_mastery >= threshold
        and fact.confidence >= policy.minimum_reliable_confidence
    )


def _candidate_target_map(
    target_gap_index: Mapping[str, Sequence[str]],
) -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for target, gaps in target_gap_index.items():
        for concept_id in gaps:
            result.setdefault(concept_id, []).append(target)
    return {
        concept_id: tuple(targets)
        for concept_id, targets in result.items()
    }


def _kg_relation_candidate_map(
    catalog: OntologyCatalog,
    targets: Sequence[str],
) -> dict[str, tuple[tuple[str, str, str], ...]]:
    if not targets:
        return {}
    target_set = set(targets)
    result: dict[str, list[tuple[str, str, str]]] = {}
    for relation in catalog.relations():
        source = str(_get_field(relation, "source"))
        target = str(_get_field(relation, "target"))
        kind = str(getattr(_get_field(relation, "kind"), "value", _get_field(relation, "kind")))
        if kind == "hard_prerequisite":
            continue
        if target in target_set:
            path = f"{source} -[{kind}]-> {target}"
            result.setdefault(source, []).append((target, kind, path))
        if kind in {"confused_with", "contrasts_with"} and source in target_set:
            path = f"{source} -[{kind}]-> {target}"
            result.setdefault(target, []).append((source, kind, path))
    return {
        concept_id: tuple(_unique_relation_context(rows))
        for concept_id, rows in result.items()
    }


def _unique_relation_context(
    rows: Iterable[tuple[str, str, str]],
) -> tuple[tuple[str, str, str], ...]:
    result: list[tuple[str, str, str]] = []
    for row in rows:
        if row not in result:
            result.append(row)
    return tuple(result)


def _score_kg_candidate(
    *,
    node_status: str,
    fact: KTStateFact | None,
    prerequisite_gap_ids: Sequence[str],
    linked_target_ids: Sequence[str],
    relation_kinds: Sequence[str],
    is_explicit_target: bool,
    policy: KGLearningPathPolicy,
) -> tuple[float, tuple[str, ...], str]:
    mastery_gap = 1.0 if fact is None else 1.0 - clamp_probability(fact.effective_mastery)
    confidence_gap = 1.0 if fact is None else 1.0 - clamp_probability(fact.confidence)
    error_risk = 0.0 if fact is None else fact.error_risk
    prerequisite_priority = 1.0 if linked_target_ids else 0.0
    relation_priority = _kg_relation_priority(relation_kinds, policy)
    availability_priority = 1.0 if node_status == "available" else 0.35
    score = (
        policy.mastery_gap_weight * mastery_gap
        + policy.confidence_gap_weight * confidence_gap
        + policy.error_risk_weight * error_risk
        + policy.prerequisite_gap_weight * prerequisite_priority
        + relation_priority
        + policy.path_availability_weight * availability_priority
    )
    reasons = ["kg_recommendation_scored"]
    if linked_target_ids:
        reasons.append("target_prerequisite_gap")
        kind = "remediate_prerequisite"
    elif prerequisite_gap_ids:
        reasons.append("candidate_has_unmet_prerequisite")
        kind = "blocked_target"
    elif is_explicit_target:
        reasons.append("explicit_target_concept")
        kind = "learn_target"
    elif relation_kinds:
        reasons.append("knowledge_graph_relation_context")
        kind = "relation_neighbor"
    elif node_status == "available":
        reasons.append("current_available_node")
        kind = "learn_next"
    else:
        reasons.append("weak_pending_concept")
        kind = "review_weak"
    if fact is None:
        reasons.append("kt_mastery_missing")
    elif fact.confidence < policy.minimum_reliable_confidence:
        reasons.append("kt_confidence_low")
    if error_risk >= 0.35:
        reasons.append("kt_error_risk_high")
    for relation_kind in relation_kinds:
        reasons.append(f"kg_relation_{relation_kind}")
    return clamp_probability(score), tuple(_unique_strings(reasons)), kind


def _kg_relation_priority(
    relation_kinds: Sequence[str],
    policy: KGLearningPathPolicy,
) -> float:
    score = 0.0
    for relation_kind in set(relation_kinds):
        if relation_kind == "soft_prerequisite":
            score += policy.soft_prerequisite_weight
        elif relation_kind == "confused_with":
            score += policy.confusion_relation_weight
        elif relation_kind == "contrasts_with":
            score += policy.contrast_relation_weight
    return clamp_probability(score)


def _kt_state_reason_codes(
    state: KTConceptState,
    *,
    effective_mastery: float,
    policy: KnowledgeTracingPolicy,
) -> tuple[str, ...]:
    reasons = ["kt_state_fact"]
    if state.confidence < policy.low_confidence_threshold:
        reasons.append("low_confidence")
    if effective_mastery < state.mastery_score:
        reasons.append("forgetting_decay_visible")
    if state.error_risk >= 0.50:
        reasons.append("high_error_risk")
    if state.mastery_score >= policy.high_mastery_threshold:
        reasons.append("high_mastery")
    if state.evidence_count <= 1:
        reasons.append("limited_evidence")
    return tuple(_unique_strings(reasons))


def _profile_error_risk_index(profile: LearnerProfileSnapshot) -> dict[str, float]:
    risks: dict[str, float] = {}
    for pattern in profile.error_patterns:
        for concept_id in pattern.concept_ids:
            risks[concept_id] = clamp_probability(
                risks.get(concept_id, 0.0) + pattern.ratio
            )
    return risks


def _needs_kt_remediation(signal: ProjectKTPlanningSignal) -> bool:
    if signal.path_status == "blocked":
        return True
    if signal.support_intensity in {"remediation", "scaffolded"}:
        return True
    if signal.effective_mastery is not None and signal.effective_mastery < 0.55:
        return True
    if signal.confidence is None or signal.confidence < 0.60:
        return True
    return signal.error_risk >= 0.35


def _remediation_sort_key(signal: ProjectKTPlanningSignal) -> tuple[int, float, int]:
    blocked_rank = 0 if signal.path_status == "blocked" else 1
    support = signal.support_need_score if signal.support_need_score is not None else 1.0
    return (blocked_rank, -support, signal.sequence)


def _default_concept_attributes_path() -> Path:
    return Path(__file__).parents[3] / "resources" / "ontology" / "concept_attributes_v1.yaml"


def _resolve_item_metadata(
    event: object,
    item_metadata: AssessmentItemMetadata | ItemMetadataRegistry | None,
) -> AssessmentItemMetadata | None:
    if item_metadata is None:
        return None
    if isinstance(item_metadata, AssessmentItemMetadata):
        return item_metadata

    event_id = str(_get_field(event, "event_id"))
    evidence_refs = tuple(str(item) for item in _get_field(event, "evidence_refs", default=()))
    for key in (event_id, *evidence_refs):
        raw = item_metadata.get(key)
        if raw is not None:
            return _coerce_item_metadata(key, raw)
    return None


def _coerce_item_metadata(
    fallback_item_id: str,
    value: AssessmentItemMetadata | Mapping[str, object],
) -> AssessmentItemMetadata:
    if isinstance(value, AssessmentItemMetadata):
        return value
    payload = dict(value)
    payload.setdefault("item_id", fallback_item_id)
    return AssessmentItemMetadata.from_mapping(payload)


def _validate_project_assessment_event(
    event: ProjectAssessmentEvent | Mapping[str, object],
) -> ProjectAssessmentEvent:
    from skillforge_kb.assessment.update import AssessmentEvent

    if hasattr(event, "model_dump"):
        return AssessmentEvent.model_validate(event.model_dump())
    return AssessmentEvent.model_validate(event)


def _validate_project_scope(catalog: object, ledger: object, event: object) -> None:
    profile = _get_field(ledger, "profile")
    if _get_field(event, "profile_id") != _get_field(profile, "profile_id"):
        raise ValueError("event profile ID does not match ledger")
    catalog_version = _get_field(_get_field(catalog, "course_document"), "version")
    if _get_field(profile, "graph_version") != catalog_version:
        raise ValueError("ledger graph version does not match catalog")
    if _get_field(event, "graph_version") != catalog_version:
        raise ValueError("event graph version does not match catalog")
    concepts = catalog.concepts() if hasattr(catalog, "concepts") else ()
    known_ids = {str(_get_field(concept, "id")) for concept in concepts}
    if known_ids:
        unknown = [
            concept_id
            for concept_id in _get_field(event, "concept_ids")
            if concept_id not in known_ids
        ]
        if unknown:
            raise ValueError(f"unknown assessment concept: {unknown[0]}")


def _project_bkt_parameter_resolver(
    catalog: OntologyCatalog,
    policy: KnowledgeTracingPolicy,
) -> Callable[[str], BKTParameters]:
    def resolve(concept_id: str) -> BKTParameters:
        try:
            concept = catalog.get_concept(concept_id)
            difficulty = int(_get_field(concept, "difficulty"))
        except Exception:
            difficulty = 2
        return difficulty_adjusted_bkt_parameters(
            policy.bkt,
            difficulty=difficulty,
            policy=policy,
        )

    return resolve


def _profile_with_project_kt_result(
    profile: LearnerProfileSnapshot,
    ledger: KTLedger,
    *,
    affected_concept_ids: Sequence[str],
) -> LearnerProfileSnapshot:
    with_mastery = _profile_with_project_kt_states(
        profile,
        ledger,
        affected_concept_ids=affected_concept_ids,
    )
    error_patterns = _merge_project_error_patterns(
        _get_field(profile, "error_patterns", default=()),
        ledger,
        affected_concept_ids=affected_concept_ids,
    )
    if hasattr(with_mastery, "model_copy"):
        return with_mastery.model_copy(
            update={"error_patterns": error_patterns},
            deep=True,
        )
    payload = _mapping_payload(with_mastery)
    payload["error_patterns"] = error_patterns
    from skillforge_kb.ontology.models import LearnerProfileSnapshot

    return LearnerProfileSnapshot.model_validate(payload)


def _profile_with_project_kt_states(
    profile: LearnerProfileSnapshot,
    ledger: KTLedger,
    *,
    affected_concept_ids: Sequence[str],
) -> LearnerProfileSnapshot:
    """复制掌握度事实，同时保持项目 updater 的顺序。"""
    if str(_get_field(profile, "profile_id")) != ledger.profile_id:
        raise ValueError("profile_id does not match KT ledger")
    if str(_get_field(profile, "graph_version")) != ledger.graph_version:
        raise ValueError("graph_version does not match KT ledger")

    merged: list[object] = []
    seen: set[str] = set()
    for item in _get_field(profile, "knowledge_mastery", default=()):
        concept_id = str(_get_field(item, "concept_id"))
        state = ledger.concept_states.get(concept_id)
        merged.append(_make_project_mastery_fact(state) if state is not None else item)
        seen.add(concept_id)

    for concept_id in affected_concept_ids:
        state = ledger.concept_states.get(concept_id)
        if state is not None and concept_id not in seen:
            merged.append(_make_project_mastery_fact(state))
            seen.add(concept_id)

    for concept_id, state in sorted(ledger.concept_states.items()):
        if concept_id not in seen:
            merged.append(_make_project_mastery_fact(state))
            seen.add(concept_id)

    if hasattr(profile, "model_copy"):
        return profile.model_copy(update={"knowledge_mastery": merged}, deep=True)
    payload = _mapping_payload(profile)
    payload["knowledge_mastery"] = merged
    from skillforge_kb.ontology.models import LearnerProfileSnapshot

    return LearnerProfileSnapshot.model_validate(payload)


def _merge_project_error_patterns(
    existing_patterns: object,
    ledger: KTLedger,
    *,
    affected_concept_ids: Sequence[str],
) -> list[object]:
    affected = set(affected_concept_ids)
    preserved: list[object] = []
    if isinstance(existing_patterns, Sequence) and not isinstance(existing_patterns, str):
        for pattern in existing_patterns:
            concept_ids = {
                str(item)
                for item in _get_field(pattern, "concept_ids", default=())
            }
            if concept_ids.isdisjoint(affected):
                preserved.append(pattern)
    rebuilt: list[object] = []
    for concept_id in affected_concept_ids:
        state = ledger.concept_states.get(concept_id)
        if state is None:
            continue
        total = sum(state.error_counts.values())
        if total <= 0:
            continue
        for code, count in sorted(state.error_counts.items()):
            rebuilt.append(
                _make_project_error_pattern(
                    code=code,
                    count=count,
                    ratio=count / total,
                    concept_id=concept_id,
                    evidence_refs=state.evidence_refs,
                )
            )
    return [*preserved, *rebuilt]


def _make_project_error_pattern(
    *,
    code: str,
    count: int,
    ratio: float,
    concept_id: str,
    evidence_refs: Sequence[str],
) -> object:
    try:
        from skillforge_kb.ontology.models import ErrorPattern

        return ErrorPattern(
            code=code,
            count=count,
            ratio=clamp_probability(ratio),
            concept_ids=[concept_id],
            evidence_refs=list(evidence_refs),
        )
    except Exception:
        return {
            "code": code,
            "count": count,
            "ratio": clamp_probability(ratio),
            "concept_ids": [concept_id],
            "evidence_refs": list(evidence_refs),
        }


def _project_error_kind(value: ErrorKind | None) -> ProjectAssessmentErrorKind | None:
    if value is None:
        return None
    from skillforge_kb.assessment.update import AssessmentErrorKind

    return AssessmentErrorKind(value)


def _logistic(value: float) -> float:
    if value >= 0:
        scale = math.exp(-value)
        return 1 / (1 + scale)
    scale = math.exp(value)
    return scale / (1 + scale)


def _model_dump(value: object) -> object:
    return value.model_dump() if hasattr(value, "model_dump") else value


def _mapping_payload(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    raise TypeError("expected a mapping or Pydantic-like model")


def state_to_dict(state: KTConceptState) -> dict[str, object]:
    return {
        "concept_id": state.concept_id,
        "mastery_score": state.mastery_score,
        "confidence": state.confidence,
        "evidence_count": state.evidence_count,
        "last_observed_at": (
            state.last_observed_at.isoformat()
            if state.last_observed_at is not None
            else None
        ),
        "evidence_refs": list(state.evidence_refs),
        "error_counts": dict(state.error_counts),
        "model_version": state.model_version,
        "parameter_version": state.parameter_version,
        "input_snapshot_digest": state.input_snapshot_digest,
    }


def state_from_dict(payload: Mapping[str, object]) -> KTConceptState:
    observed = payload.get("last_observed_at")
    observed_at = _parse_datetime(observed)
    evidence_refs = payload.get("evidence_refs", ())
    if not isinstance(evidence_refs, Sequence) or isinstance(evidence_refs, str):
        raise ValueError("evidence_refs must be a sequence")
    error_counts = payload.get("error_counts", {})
    if not isinstance(error_counts, Mapping):
        raise ValueError("error_counts must be a mapping")
    return KTConceptState(
        concept_id=_required_string(payload, "concept_id"),
        mastery_score=float(cast(Any, payload.get("mastery_score", 0.0))),
        confidence=float(cast(Any, payload.get("confidence", 0.0))),
        evidence_count=int(cast(Any, payload.get("evidence_count", 0))),
        last_observed_at=observed_at,
        evidence_refs=tuple(str(item) for item in evidence_refs),
        error_counts={str(key): int(value) for key, value in error_counts.items()},
        model_version=str(payload.get("model_version", "bkt.v1")),
        parameter_version=str(payload.get("parameter_version", "unknown")),
        input_snapshot_digest=(
            str(payload["input_snapshot_digest"])
            if payload.get("input_snapshot_digest") is not None
            else None
        ),
    )


def event_to_dict(event: KTEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "profile_id": event.profile_id,
        "graph_version": event.graph_version,
        "concept_ids": list(event.concept_ids),
        "correct": event.correct,
        "timestamp": event.timestamp.isoformat(),
        "response_time_ms": event.response_time_ms,
        "hint_count": event.hint_count,
        "attempt_count": event.attempt_count,
        "error_kind": event.error_kind,
        "evidence_refs": list(event.evidence_refs),
        "item_difficulty": event.item_difficulty,
        "item_discrimination": event.item_discrimination,
        "target_depth": event.target_depth,
        "expected_time_ms": event.expected_time_ms,
    }


def _adjusted_guess(params: BKTParameters, event: KTEvent) -> float:
    if not event.correct:
        return params.guess_probability
    hint_boost = params.hint_guess_boost * min(
        event.hint_count,
        params.maximum_penalized_hints,
    )
    retry_boost = params.retry_guess_boost * min(
        max(event.attempt_count - 1, 0),
        params.maximum_penalized_retries,
    )
    return clamp_probability(params.guess_probability + hint_boost + retry_boost)


def _adjusted_observation_parameters(
    params: BKTParameters,
    event: KTEvent,
) -> tuple[float, float, tuple[str, ...]]:
    guess = _adjusted_guess(params, event)
    slip = params.slip_probability
    reasons: list[str] = []

    if event.item_difficulty is not None:
        centered_difficulty = event.item_difficulty - 0.5
        guess = clamp_probability(guess - 0.10 * centered_difficulty)
        slip = clamp_probability(slip + 0.10 * centered_difficulty)
        reasons.append("item_difficulty_adjusted_observation")

    if event.item_discrimination is not None:
        discrimination = max(0.25, min(4.0, event.item_discrimination))
        noise_scale = 1 / math.sqrt(discrimination)
        guess = clamp_probability(guess * noise_scale)
        slip = clamp_probability(slip * noise_scale)
        reasons.append("item_discrimination_adjusted_observation")

    if event.expected_time_ms is not None and event.expected_time_ms > 0:
        time_ratio = event.response_time_ms / event.expected_time_ms
        if event.correct and time_ratio < 0.35:
            guess = clamp_probability(guess + 0.04)
            reasons.append("very_fast_correct_downweighted")
        elif not event.correct and time_ratio > 1.75:
            slip = clamp_probability(slip * 0.85)
            reasons.append("slow_incorrect_treated_as_gap")

    return guess, slip, tuple(reasons)


def _updated_confidence(previous: KTConceptState, params: BKTParameters) -> float:
    base = max(previous.confidence, params.minimum_observed_confidence)
    return clamp_probability(base + params.confidence_gain * (1 - base))


def _unique_refs(*groups: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for group in groups:
        for item in group:
            if item not in result:
                result.append(item)
    return tuple(result)


def _unique_strings(items: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return tuple(result)


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"object is not JSON serializable: {type(value).__name__}")


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(cast(Any, value))


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(cast(Any, value))


def _optional_depth(value: object) -> AssessmentDepth | None:
    if value is None:
        return None
    raw = str(value)
    if raw not in {"intro", "intermediate", "advanced"}:
        raise ValueError(f"unknown assessment depth: {raw}")
    return cast(AssessmentDepth, raw)


def _require_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("expected mapping")
    return value


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("datetime string must include timezone")
        return parsed
    raise ValueError("invalid datetime value")


def _get_field(value: object, name: str, default: object = ...) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    elif hasattr(value, name):
        return getattr(value, name)
    if default is not ...:
        return default
    raise ValueError(f"missing field: {name}")


def _normalize_error_kind(value: object) -> ErrorKind | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    if raw in {
        "concept_confusion",
        "logic_gap",
        "calculation_error",
        "missed_condition",
        "code_shape_error",
    }:
        return raw  # type: ignore[return-value]
    raise ValueError(f"unknown error kind: {raw}")


def _make_project_mastery_fact(state: KTConceptState) -> object:
    try:
        from skillforge_kb.ontology.models import AssessmentStatus, KnowledgeMastery

        return KnowledgeMastery(
            concept_id=state.concept_id,
            mastery_score=state.mastery_score,
            assessment_status=AssessmentStatus.ASSESSED,
            confidence=state.confidence,
            observed_at=state.last_observed_at,
            evidence_refs=list(state.evidence_refs),
        )
    except Exception:
        return state.to_profile_mastery_fact()
