import json
from datetime import datetime
from hashlib import sha256
from math import isfinite, log
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from skillforge_kb.ontology.models import CONCEPT_ID_PATTERN

_JSON_ADAPTER = TypeAdapter(object)
_LOG_EPSILON = 1e-15
_DISCLAIMER = "Offline prediction metrics do not equal real learning effectiveness."


class KnowledgeTracingObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observation_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    model_version: str = Field(min_length=1)
    predicted_mastery: float = Field(ge=0, le=1)
    correct: bool
    observed_at: datetime

    @model_validator(mode="after")
    def validate_observation(self) -> "KnowledgeTracingObservation":
        if not isfinite(self.predicted_mastery):
            raise ValueError("predicted mastery must be finite")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observation timestamp must be timezone-aware")
        return self


class KnowledgeTracingMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_count: int = Field(ge=1)
    positive_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    brier_score: float = Field(ge=0, le=1)
    log_loss: float = Field(ge=0)
    auc: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_counts(self) -> "KnowledgeTracingMetrics":
        if self.positive_count + self.negative_count != self.sample_count:
            raise ValueError("positive and negative counts must equal samples")
        if not isfinite(self.brier_score) or not isfinite(self.log_loss):
            raise ValueError("knowledge tracing metrics must be finite")
        if self.auc is not None and not isfinite(self.auc):
            raise ValueError("AUC must be finite")
        return self


class KnowledgeTracingEvaluationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["knowledge-tracing-evaluation.v1"] = (
        "knowledge-tracing-evaluation.v1"
    )
    data_kind: Literal["observed_predictions"] = "observed_predictions"
    disclaimer: Literal[
        "Offline prediction metrics do not equal real learning effectiveness."
    ] = _DISCLAIMER
    data_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    observations: tuple[KnowledgeTracingObservation, ...] = Field(min_length=1)
    metrics: KnowledgeTracingMetrics
    report_digest: str = Field(pattern=r"^knowledge_tracing_evaluation_[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_report(self) -> "KnowledgeTracingEvaluationReport":
        ids = [item.observation_id for item in self.observations]
        if len(ids) != len(set(ids)):
            raise ValueError("knowledge tracing observation IDs must be unique")
        if any(item.model_version != self.model_version for item in self.observations):
            raise ValueError("report model version does not match observations")
        expected = build_knowledge_tracing_report_digest(
            self.model_dump(mode="json", exclude={"report_digest"})
        )
        if self.report_digest != expected:
            raise ValueError("knowledge tracing report digest does not match content")
        return self


def evaluate_knowledge_tracing(
    observations: Sequence[KnowledgeTracingObservation],
    *,
    model_version: str | None = None,
    data_version: str = "knowledge-tracing-eval.v1",
) -> KnowledgeTracingEvaluationReport:
    validated = tuple(
        KnowledgeTracingObservation.model_validate(item.model_dump())
        for item in observations
    )
    if not validated:
        raise ValueError("knowledge tracing evaluation requires at least one observation")
    ids = [item.observation_id for item in validated]
    if len(ids) != len(set(ids)):
        raise ValueError("knowledge tracing observation IDs must be unique")
    inferred_model = model_version or validated[0].model_version
    if any(item.model_version != inferred_model for item in validated):
        raise ValueError("knowledge tracing observations must use one model version")
    pairs = tuple((item.predicted_mastery, int(item.correct)) for item in validated)
    positives = sum(label for _, label in pairs)
    negatives = len(pairs) - positives
    metrics = KnowledgeTracingMetrics(
        sample_count=len(pairs),
        positive_count=positives,
        negative_count=negatives,
        brier_score=(
            sum((probability - label) ** 2 for probability, label in pairs)
            / len(pairs)
        ),
        log_loss=_log_loss(pairs),
        auc=_roc_auc(pairs),
    )
    payload = {
        "schema_version": "knowledge-tracing-evaluation.v1",
        "data_kind": "observed_predictions",
        "disclaimer": _DISCLAIMER,
        "data_version": data_version,
        "model_version": inferred_model,
        "observations": validated,
        "metrics": metrics,
    }
    return KnowledgeTracingEvaluationReport(
        **payload,
        report_digest=build_knowledge_tracing_report_digest(payload),
    )


def build_knowledge_tracing_report_digest(payload: object) -> str:
    serializable = _JSON_ADAPTER.dump_python(payload, mode="json")
    canonical = json.dumps(
        serializable,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"knowledge_tracing_evaluation_{sha256(canonical.encode('utf-8')).hexdigest()}"


def _log_loss(pairs: tuple[tuple[float, int], ...]) -> float:
    total = 0.0
    for probability, label in pairs:
        safe = min(1 - _LOG_EPSILON, max(_LOG_EPSILON, probability))
        total -= label * log(safe) + (1 - label) * log(1 - safe)
    return total / len(pairs)


def _roc_auc(pairs: tuple[tuple[float, int], ...]) -> float | None:
    positives = sum(label for _, label in pairs)
    negatives = len(pairs) - positives
    if positives == 0 or negatives == 0:
        return None
    ranked = sorted(pairs, key=lambda item: item[0])
    rank_sum_positive = 0.0
    index = 0
    while index < len(ranked):
        end = index + 1
        while end < len(ranked) and ranked[end][0] == ranked[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2
        rank_sum_positive += average_rank * sum(
            label for _, label in ranked[index:end]
        )
        index = end
    return (
        rank_sum_positive - positives * (positives + 1) / 2
    ) / (positives * negatives)
