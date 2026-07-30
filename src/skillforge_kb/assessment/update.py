import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.ontology.models import (
    CONCEPT_ID_PATTERN,
    LearnerProfileSnapshot,
)

_POLICY_DIGEST_PATTERN = r"^assessment_policy_[0-9a-f]{64}$"
_EVENT_DIGEST_PATTERN = r"^assessment_event_[0-9a-f]{64}$"

ConceptId = Annotated[str, Field(pattern=CONCEPT_ID_PATTERN)]
BoundedScore = Annotated[float, Field(ge=0, le=1)]
MasteryFact = tuple[ConceptId, BoundedScore]


class AssessmentErrorKind(StrEnum):
    CONCEPT_CONFUSION = "concept_confusion"
    LOGIC_GAP = "logic_gap"
    CALCULATION_ERROR = "calculation_error"
    MISSED_CONDITION = "missed_condition"


class AssessmentEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    concept_ids: tuple[ConceptId, ...] = Field(min_length=1)
    correct: bool
    response_time_ms: int = Field(strict=True, ge=0)
    hint_count: int = Field(strict=True, ge=0)
    attempt_count: int = Field(strict=True, ge=1)
    timestamp: datetime
    error_kind: AssessmentErrorKind | None = None
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_event(self) -> "AssessmentEvent":
        if len(self.concept_ids) != len(set(self.concept_ids)):
            raise ValueError("concept IDs must be unique")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("assessment timestamp must be timezone-aware")
        if self.correct and self.error_kind is not None:
            raise ValueError("correct answers cannot include error_kind")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("event evidence references must be unique")
        return self


class AssessmentPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(default="rule-based-assessment.v1", min_length=1)
    prior_mastery: float = Field(default=0.50, ge=0, le=1)
    prior_confidence: float = Field(default=0.25, ge=0, le=1)
    correct_gain: float = Field(default=0.12, ge=0, le=1)
    incorrect_loss: float = Field(default=0.15, ge=0, le=1)
    hint_penalty: float = Field(default=0.03, ge=0, le=1)
    maximum_penalized_hints: int = Field(default=3, strict=True, ge=0)
    retry_penalty: float = Field(default=0.02, ge=0, le=1)
    confidence_gain: float = Field(default=0.12, ge=0, le=1)
    minimum_observed_confidence: float = Field(default=0.25, ge=0, le=1)


class AssessmentLedger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: LearnerProfileSnapshot
    processed_event_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_processed_event_ids(self) -> "AssessmentLedger":
        if len(self.processed_event_ids) != len(set(self.processed_event_ids)):
            raise ValueError("processed event IDs must be unique")
        return self


class AssessmentUpdateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ledger: AssessmentLedger
    policy_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=_POLICY_DIGEST_PATTERN)
    event_digest: str = Field(pattern=_EVENT_DIGEST_PATTERN)
    applied: bool
    affected_concept_ids: tuple[ConceptId, ...] = ()
    mastery_before: tuple[MasteryFact, ...] = ()
    mastery_after: tuple[MasteryFact, ...] = ()
    classified_error_kind: AssessmentErrorKind | None = None
    reason_codes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result_facts(self) -> "AssessmentUpdateResult":
        if len(self.affected_concept_ids) != len(set(self.affected_concept_ids)):
            raise ValueError("affected concept IDs must be unique")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("assessment reason codes must be unique")
        before_ids = tuple(item[0] for item in self.mastery_before)
        after_ids = tuple(item[0] for item in self.mastery_after)
        if before_ids != self.affected_concept_ids or after_ids != before_ids:
            raise ValueError("mastery facts must match affected concept IDs")
        if not self.applied and (
            self.affected_concept_ids or self.classified_error_kind is not None
        ):
            raise ValueError("no-op result cannot contain changed assessment facts")
        return self


def build_assessment_policy_digest(policy: AssessmentPolicy) -> str:
    return _build_digest("assessment_policy", policy.model_dump(mode="json"))


def build_assessment_event_digest(event: AssessmentEvent) -> str:
    return _build_digest("assessment_event", event.model_dump(mode="json"))


def _build_digest(prefix: str, payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"{prefix}_{sha256(canonical.encode('utf-8')).hexdigest()}"
