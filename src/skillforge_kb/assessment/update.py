import json
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import (
    CONCEPT_ID_PATTERN,
    AssessmentStatus,
    ErrorPattern,
    KnowledgeMastery,
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


def apply_assessment_event(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
    event: AssessmentEvent,
    policy: AssessmentPolicy | None = None,
) -> AssessmentUpdateResult:
    AssessmentLedger.model_validate(ledger.model_dump())
    event = AssessmentEvent.model_validate(event.model_dump())
    active_policy = AssessmentPolicy.model_validate(
        (policy or AssessmentPolicy()).model_dump()
    )
    policy_digest = build_assessment_policy_digest(active_policy)
    event_digest = build_assessment_event_digest(event)
    _validate_scope(catalog, ledger, event)

    if event.event_id in ledger.processed_event_ids:
        return AssessmentUpdateResult(
            ledger=ledger,
            policy_version=active_policy.version,
            policy_digest=policy_digest,
            event_digest=event_digest,
            applied=False,
            reason_codes=("duplicate_event",),
        )

    classified_error_kind = _classify_error(event)
    mastery, before, after = _updated_mastery(ledger.profile, event, active_policy)
    error_patterns = _updated_error_patterns(
        ledger.profile.error_patterns,
        event,
        classified_error_kind,
    )
    profile_payload = ledger.profile.model_dump()
    profile_payload["knowledge_mastery"] = mastery
    profile_payload["error_patterns"] = error_patterns
    updated_profile = LearnerProfileSnapshot.model_validate(profile_payload)
    updated_ledger = AssessmentLedger(
        profile=updated_profile,
        processed_event_ids=(*ledger.processed_event_ids, event.event_id),
    )
    return AssessmentUpdateResult(
        ledger=updated_ledger,
        policy_version=active_policy.version,
        policy_digest=policy_digest,
        event_digest=event_digest,
        applied=True,
        affected_concept_ids=event.concept_ids,
        mastery_before=before,
        mastery_after=after,
        classified_error_kind=classified_error_kind,
        reason_codes=(
            "correct_answer_applied" if event.correct else "incorrect_answer_applied",
        ),
    )


def _validate_scope(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
    event: AssessmentEvent,
) -> None:
    if event.profile_id != ledger.profile.profile_id:
        raise ValueError("event profile ID does not match ledger")
    catalog_version = catalog.course_document.version
    if ledger.profile.graph_version != catalog_version:
        raise ValueError("ledger graph version does not match catalog")
    if event.graph_version != catalog_version:
        raise ValueError("event graph version does not match catalog")
    known_ids = {concept.id for concept in catalog.concepts()}
    unknown_ids = [concept_id for concept_id in event.concept_ids if concept_id not in known_ids]
    if unknown_ids:
        raise ValueError(f"unknown assessment concept: {unknown_ids[0]}")


def _classify_error(event: AssessmentEvent) -> AssessmentErrorKind | None:
    if event.correct:
        return None
    if event.error_kind is not None:
        return event.error_kind
    if event.hint_count >= 2:
        return AssessmentErrorKind.CONCEPT_CONFUSION
    if event.response_time_ms >= 120000:
        return AssessmentErrorKind.LOGIC_GAP
    if event.attempt_count >= 2:
        return AssessmentErrorKind.CALCULATION_ERROR
    return AssessmentErrorKind.MISSED_CONDITION


def _updated_mastery(
    profile: LearnerProfileSnapshot,
    event: AssessmentEvent,
    policy: AssessmentPolicy,
) -> tuple[list[KnowledgeMastery], tuple[MasteryFact, ...], tuple[MasteryFact, ...]]:
    existing_by_id: dict[str, KnowledgeMastery] = {}
    for item in profile.knowledge_mastery:
        if item.concept_id in existing_by_id:
            raise ValueError(f"duplicate mastery concept: {item.concept_id}")
        existing_by_id[item.concept_id] = item

    replacements: dict[str, KnowledgeMastery] = {}
    before: list[MasteryFact] = []
    after: list[MasteryFact] = []
    for concept_id in event.concept_ids:
        existing = existing_by_id.get(concept_id)
        current_mastery = (
            existing.mastery_score
            if existing is not None and existing.mastery_score is not None
            else policy.prior_mastery
        )
        updated_score = _updated_mastery_score(current_mastery, event, policy)
        current_confidence = (
            existing.confidence if existing is not None else policy.prior_confidence
        )
        confidence_base = max(
            current_confidence,
            policy.prior_confidence,
            policy.minimum_observed_confidence,
        )
        updated_confidence = _clamp(
            confidence_base + policy.confidence_gain * (1 - confidence_base)
        )
        evidence_refs = _unique_refs(
            existing.evidence_refs if existing is not None else (),
            (event.event_id,),
            event.evidence_refs,
        )
        replacements[concept_id] = KnowledgeMastery(
            concept_id=concept_id,
            mastery_score=updated_score,
            assessment_status=AssessmentStatus.ASSESSED,
            confidence=updated_confidence,
            observed_at=event.timestamp,
            evidence_refs=evidence_refs,
        )
        before.append((concept_id, current_mastery))
        after.append((concept_id, updated_score))

    updated = [
        replacements.get(item.concept_id, item.model_copy(deep=True))
        for item in profile.knowledge_mastery
    ]
    updated.extend(
        replacements[concept_id]
        for concept_id in event.concept_ids
        if concept_id not in existing_by_id
    )
    return updated, tuple(before), tuple(after)


def _updated_mastery_score(
    current: float,
    event: AssessmentEvent,
    policy: AssessmentPolicy,
) -> float:
    if event.correct:
        raw = current + policy.correct_gain * (1 - current)
    else:
        raw = current - policy.incorrect_loss * current
    adjusted = (
        raw
        - policy.hint_penalty
        * min(event.hint_count, policy.maximum_penalized_hints)
        - policy.retry_penalty * max(event.attempt_count - 1, 0)
    )
    return _clamp(adjusted)


def _updated_error_patterns(
    patterns: list[ErrorPattern],
    event: AssessmentEvent,
    classified_error_kind: AssessmentErrorKind | None,
) -> list[ErrorPattern]:
    if classified_error_kind is None:
        return [pattern.model_copy(deep=True) for pattern in patterns]

    affected = set(event.concept_ids)
    counts: dict[str, dict[str, int]] = {
        concept_id: {} for concept_id in event.concept_ids
    }
    code_order: dict[str, list[str]] = {
        concept_id: [] for concept_id in event.concept_ids
    }
    references: dict[tuple[str, str], list[str]] = {}
    preserved: list[ErrorPattern] = []
    for pattern in patterns:
        matched = [concept_id for concept_id in pattern.concept_ids if concept_id in affected]
        if not matched:
            preserved.append(pattern.model_copy(deep=True))
            continue
        for concept_id in matched:
            concept_counts = counts[concept_id]
            if pattern.code not in code_order[concept_id]:
                code_order[concept_id].append(pattern.code)
            concept_counts[pattern.code] = (
                concept_counts.get(pattern.code, 0) + pattern.count
            )
            key = (concept_id, pattern.code)
            references[key] = _unique_refs(references.get(key, ()), pattern.evidence_refs)
        remaining = [
            concept_id for concept_id in pattern.concept_ids if concept_id not in affected
        ]
        if remaining:
            preserved.append(pattern.model_copy(update={"concept_ids": remaining}, deep=True))

    for concept_id in event.concept_ids:
        concept_counts = counts[concept_id]
        new_code = classified_error_kind.value
        if new_code not in code_order[concept_id]:
            code_order[concept_id].append(new_code)
        concept_counts[new_code] = (
            concept_counts.get(new_code, 0) + 1
        )
        key = (concept_id, new_code)
        references[key] = _unique_refs(
            references.get(key, ()),
            (event.event_id,),
            event.evidence_refs,
        )

    aggregated: list[ErrorPattern] = []
    for concept_id in event.concept_ids:
        concept_counts = counts[concept_id]
        total = sum(concept_counts.values())
        for code in code_order[concept_id]:
            count = concept_counts[code]
            aggregated.append(
                ErrorPattern(
                    code=code,
                    count=count,
                    ratio=count / total,
                    concept_ids=[concept_id],
                    evidence_refs=references.get((concept_id, code), []),
                )
            )
    return [*preserved, *aggregated]


def _unique_refs(*groups: Sequence[str]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for reference in group:
            if reference not in result:
                result.append(reference)
    return result


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _build_digest(prefix: str, payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"{prefix}_{sha256(canonical.encode('utf-8')).hexdigest()}"
