from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import AssessmentStatus, KnowledgeMastery

from .update import (
    AssessmentErrorKind,
    AssessmentEvent,
    AssessmentLedger,
    MasteryFact,
    _classify_error,
    _unique_refs,
    _updated_error_patterns,
    _validate_scope,
    build_assessment_event_digest,
)


class BktParameters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    p_l0: float = Field(default=0.2, ge=0, le=1)
    p_transition: float = Field(default=0.1, ge=0, le=1)
    p_guess: float = Field(default=0.2, ge=0, le=1)
    p_slip: float = Field(default=0.1, ge=0, le=1)
    model_version: str = Field(default="bkt.v1", min_length=1)
    parameter_version: str = Field(default="bkt-default.v1", min_length=1)

    @model_validator(mode="after")
    def validate_observation_parameters(self) -> "BktParameters":
        if self.p_guess + self.p_slip >= 1:
            raise ValueError("guess and slip probabilities must sum to less than 1")
        return self


class BktState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mastery_probability: float = Field(ge=0, le=1)
    evidence_count: int = Field(default=0, strict=True, ge=0)
    last_observed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_timestamp(self) -> "BktState":
        if self.last_observed_at is not None and (
            self.last_observed_at.tzinfo is None
            or self.last_observed_at.utcoffset() is None
        ):
            raise ValueError("BKT observation timestamp must be timezone-aware")
        return self


class BktAssessmentUpdateResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ledger: AssessmentLedger
    model_version: str = Field(min_length=1)
    parameter_version: str = Field(min_length=1)
    event_digest: str = Field(pattern=r"^assessment_event_[0-9a-f]{64}$")
    applied: bool
    affected_concept_ids: tuple[str, ...] = ()
    mastery_before: tuple[MasteryFact, ...] = ()
    mastery_after: tuple[MasteryFact, ...] = ()
    classified_error_kind: AssessmentErrorKind | None = None
    reason_codes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_facts(self) -> "BktAssessmentUpdateResult":
        if len(self.affected_concept_ids) != len(set(self.affected_concept_ids)):
            raise ValueError("affected concept IDs must be unique")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("BKT reason codes must be unique")
        before_ids = tuple(item[0] for item in self.mastery_before)
        after_ids = tuple(item[0] for item in self.mastery_after)
        if before_ids != self.affected_concept_ids or after_ids != before_ids:
            raise ValueError("BKT mastery facts must match affected concept IDs")
        if not self.applied and (
            self.affected_concept_ids or self.classified_error_kind is not None
        ):
            raise ValueError("BKT no-op result cannot contain changed facts")
        return self


def update_bkt_probability(
    prior_mastery: float,
    correct: bool,
    parameters: BktParameters,
) -> float:
    if not 0 <= prior_mastery <= 1:
        raise ValueError("prior mastery must be between 0 and 1")
    params = BktParameters.model_validate(parameters.model_dump())
    p = _clamp(prior_mastery)
    if correct:
        numerator = p * (1 - params.p_slip)
        denominator = numerator + (1 - p) * params.p_guess
    else:
        numerator = p * params.p_slip
        denominator = numerator + (1 - p) * (1 - params.p_guess)
    if denominator == 0:
        raise ValueError("BKT observation denominator must be positive")
    posterior = _clamp(numerator / denominator)
    return _clamp(posterior + (1 - posterior) * params.p_transition)


def apply_bkt_event(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
    event: AssessmentEvent,
    parameters: BktParameters | None = None,
) -> BktAssessmentUpdateResult:
    validated_ledger = AssessmentLedger.model_validate(ledger.model_dump())
    validated_event = AssessmentEvent.model_validate(event.model_dump())
    params = BktParameters.model_validate((parameters or BktParameters()).model_dump())
    event_digest = build_assessment_event_digest(validated_event)
    _validate_scope(catalog, validated_ledger, validated_event)

    if validated_event.event_id in validated_ledger.processed_event_ids:
        return BktAssessmentUpdateResult(
            ledger=validated_ledger,
            model_version=params.model_version,
            parameter_version=params.parameter_version,
            event_digest=event_digest,
            applied=False,
            reason_codes=("duplicate_event",),
        )

    classified_error_kind = _classify_error(validated_event)
    mastery, before, after = _updated_bkt_mastery(
        validated_ledger, validated_event, params
    )
    error_patterns = _updated_error_patterns(
        validated_ledger.profile.error_patterns,
        validated_event,
        classified_error_kind,
    )
    profile_payload = validated_ledger.profile.model_dump()
    profile_payload["knowledge_mastery"] = mastery
    profile_payload["error_patterns"] = error_patterns
    updated_profile = validated_ledger.profile.__class__.model_validate(profile_payload)
    updated_ledger = AssessmentLedger(
        profile=updated_profile,
        processed_event_ids=(
            *validated_ledger.processed_event_ids,
            validated_event.event_id,
        ),
    )
    return BktAssessmentUpdateResult(
        ledger=updated_ledger,
        model_version=params.model_version,
        parameter_version=params.parameter_version,
        event_digest=event_digest,
        applied=True,
        affected_concept_ids=validated_event.concept_ids,
        mastery_before=before,
        mastery_after=after,
        classified_error_kind=classified_error_kind,
        reason_codes=("bkt_update_applied",),
    )


def _updated_bkt_mastery(
    ledger: AssessmentLedger,
    event: AssessmentEvent,
    parameters: BktParameters,
) -> tuple[list[KnowledgeMastery], tuple[MasteryFact, ...], tuple[MasteryFact, ...]]:
    existing_by_id: dict[str, KnowledgeMastery] = {}
    for item in ledger.profile.knowledge_mastery:
        if item.concept_id in existing_by_id:
            raise ValueError(f"duplicate mastery concept: {item.concept_id}")
        existing_by_id[item.concept_id] = item

    replacements: dict[str, KnowledgeMastery] = {}
    before: list[MasteryFact] = []
    after: list[MasteryFact] = []
    for concept_id in event.concept_ids:
        existing = existing_by_id.get(concept_id)
        current = (
            existing.mastery_score
            if existing is not None and existing.mastery_score is not None
            else parameters.p_l0
        )
        updated = update_bkt_probability(current, event.correct, parameters)
        confidence = existing.confidence if existing is not None else 0.25
        evidence_refs = _unique_refs(
            existing.evidence_refs if existing is not None else (),
            (event.event_id,),
            event.evidence_refs,
        )
        replacements[concept_id] = KnowledgeMastery(
            concept_id=concept_id,
            mastery_score=updated,
            assessment_status=AssessmentStatus.ASSESSED,
            confidence=confidence,
            observed_at=event.timestamp,
            evidence_refs=evidence_refs,
        )
        before.append((concept_id, current))
        after.append((concept_id, updated))

    updated = [
        replacements.get(item.concept_id, item.model_copy(deep=True))
        for item in ledger.profile.knowledge_mastery
    ]
    updated.extend(
        replacements[concept_id]
        for concept_id in event.concept_ids
        if concept_id not in existing_by_id
    )
    return updated, tuple(before), tuple(after)


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))
