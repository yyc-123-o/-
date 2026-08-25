import pytest
from datetime import UTC, datetime
from pydantic import ValidationError

from skillforge_kb.assessment import AssessmentEvent
from skillforge_kb.assessment.bkt import (
    BktParameters,
    apply_bkt_event,
    update_bkt_probability,
)


def event_factory(**overrides: object) -> AssessmentEvent:
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


def test_default_parameters_and_first_observations() -> None:
    params = BktParameters()

    assert params.p_l0 == pytest.approx(0.2)
    assert update_bkt_probability(params.p_l0, True, params) == pytest.approx(
        0.5764705882
    )
    assert update_bkt_probability(params.p_l0, False, params) == pytest.approx(
        0.1272727273
    )


def test_parameters_reject_invalid_probability_combinations() -> None:
    with pytest.raises(ValidationError):
        BktParameters(p_l0=1.1)
    with pytest.raises(ValidationError, match="guess and slip"):
        BktParameters(p_guess=0.9, p_slip=0.1)


def test_repeated_correct_answers_increase_and_wrong_answers_decrease() -> None:
    params = BktParameters()
    correct = params.p_l0
    wrong = params.p_l0
    correct_values: list[float] = []
    wrong_values: list[float] = []

    for _ in range(4):
        correct = update_bkt_probability(correct, True, params)
        wrong = update_bkt_probability(wrong, False, params)
        correct_values.append(correct)
        wrong_values.append(wrong)

    assert correct_values == sorted(correct_values)
    assert wrong_values == sorted(wrong_values, reverse=True)
    assert all(0 <= value <= 1 for value in (*correct_values, *wrong_values))


def test_bkt_event_updates_mastery_and_is_idempotent(catalog, ledger) -> None:
    event = event_factory(event_id="bkt-1", evidence_refs=("item-1",))

    first = apply_bkt_event(catalog, ledger, event)
    second = apply_bkt_event(catalog, first.ledger, event)

    assert first.applied is True
    assert first.mastery_before == ((event.concept_ids[0], 0.2),)
    assert first.mastery_after[0][1] == pytest.approx(0.5764705882)
    assert first.model_version == "bkt.v1"
    assert first.reason_codes == ("bkt_update_applied",)
    assert second.applied is False
    assert second.reason_codes == ("duplicate_event",)


def test_bkt_event_preserves_unrelated_mastery_and_updates_errors(catalog, ledger) -> None:
    wrong = event_factory(event_id="bkt-wrong", correct=False, hint_count=2)

    result = apply_bkt_event(catalog, ledger, wrong)

    assert result.classified_error_kind.value == "concept_confusion"
    assert result.ledger.profile.error_patterns[0].count == 1


@pytest.mark.parametrize("field", ["profile_id", "graph_version", "concept_ids"])
def test_bkt_event_scope_failures_do_not_mutate_ledger(catalog, ledger, field) -> None:
    values = {
        "profile_id": "wrong-profile",
        "graph_version": "wrong-graph",
        "concept_ids": ("unknown.concept",),
    }

    with pytest.raises(ValueError):
        apply_bkt_event(catalog, ledger, event_factory(**{field: values[field]}))

    assert ledger.processed_event_ids == ()
