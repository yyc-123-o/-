from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from skillforge_kb.assessment import (
    AssessmentErrorKind,
    AssessmentEvent,
    AssessmentLedger,
    AssessmentPolicy,
    build_assessment_event_digest,
    build_assessment_policy_digest,
)
from skillforge_kb.ontology.models import LearnerProfileSnapshot


def _event(**overrides: object) -> AssessmentEvent:
    payload: dict[str, object] = {
        "event_id": "event-1",
        "profile_id": "profile-assessment",
        "graph_version": "ai-course-v1",
        "concept_ids": ("ml.optimization.gradient-descent",),
        "correct": True,
        "response_time_ms": 1000,
        "hint_count": 0,
        "attempt_count": 1,
        "timestamp": datetime(2026, 7, 30, 8, tzinfo=UTC),
    }
    payload.update(overrides)
    return AssessmentEvent.model_validate(payload)


def test_event_requires_aware_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _event(timestamp=datetime(2026, 7, 30, 8))


def test_event_requires_unique_concepts() -> None:
    with pytest.raises(ValidationError, match="concept IDs must be unique"):
        _event(concept_ids=("ml.optimization.gradient-descent",) * 2)


def test_correct_event_rejects_explicit_error_kind() -> None:
    with pytest.raises(ValidationError, match="correct answers cannot include error_kind"):
        _event(correct=True, error_kind=AssessmentErrorKind.LOGIC_GAP)


def test_policy_has_exact_v1_defaults_and_rejects_out_of_bounds() -> None:
    policy = AssessmentPolicy()

    assert policy.version == "rule-based-assessment.v1"
    assert policy.prior_mastery == 0.50
    assert policy.prior_confidence == 0.25
    assert policy.correct_gain == 0.12
    assert policy.incorrect_loss == 0.15
    assert policy.hint_penalty == 0.03
    assert policy.maximum_penalized_hints == 3
    assert policy.retry_penalty == 0.02
    assert policy.confidence_gain == 0.12
    assert policy.minimum_observed_confidence == 0.25

    with pytest.raises(ValidationError):
        AssessmentPolicy(prior_mastery=1.01)


def test_policy_and_event_digests_are_stable_and_content_sensitive() -> None:
    event = _event()
    rebuilt = AssessmentEvent.model_validate(event.model_dump())

    assert build_assessment_event_digest(event) == build_assessment_event_digest(rebuilt)
    assert build_assessment_event_digest(event).startswith("assessment_event_")
    assert build_assessment_event_digest(event) != build_assessment_event_digest(
        event.model_copy(update={"hint_count": 1})
    )
    assert build_assessment_policy_digest(AssessmentPolicy()).startswith(
        "assessment_policy_"
    )


def test_ledger_rejects_duplicate_processed_event_ids(
    profile: LearnerProfileSnapshot,
) -> None:
    with pytest.raises(ValidationError, match="processed event IDs must be unique"):
        AssessmentLedger(
            profile=profile,
            processed_event_ids=("event-1", "event-1"),
        )
