from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from skillforge_kb.assessment import (
    AssessmentErrorKind,
    AssessmentEvent,
    AssessmentLedger,
    AssessmentPolicy,
    apply_assessment_event,
    build_assessment_event_digest,
    build_assessment_policy_digest,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import (
    AssessmentStatus,
    ErrorPattern,
    KnowledgeMastery,
    LearnerProfileSnapshot,
)


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


def test_correct_answer_raises_mastery_and_duplicate_is_noop(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
) -> None:
    event = _event(correct=True, evidence_refs=("item-bank:item-7",))

    first = apply_assessment_event(catalog, ledger, event)
    second = apply_assessment_event(catalog, first.ledger, event)

    assert first.applied is True
    assert first.mastery_before == ((event.concept_ids[0], 0.50),)
    assert first.mastery_after == ((event.concept_ids[0], pytest.approx(0.56)),)
    assert first.ledger.profile.knowledge_mastery[0].confidence == pytest.approx(0.34)
    assert first.ledger.profile.knowledge_mastery[0].evidence_refs == [
        "event-1",
        "item-bank:item-7",
    ]
    assert first.policy_digest == build_assessment_policy_digest(AssessmentPolicy())
    assert first.event_digest == build_assessment_event_digest(event)
    assert ledger.processed_event_ids == ()
    assert ledger.profile.knowledge_mastery == []

    assert second.applied is False
    assert second.reason_codes == ("duplicate_event",)
    assert second.ledger is first.ledger
    assert second.affected_concept_ids == ()
    assert second.mastery_before == ()
    assert second.mastery_after == ()


def test_incorrect_answer_lowers_mastery_from_prior(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
) -> None:
    result = apply_assessment_event(catalog, ledger, _event(correct=False))

    assert result.mastery_before[0][1] == 0.50
    assert result.mastery_after[0][1] == pytest.approx(0.425)
    assert result.classified_error_kind is AssessmentErrorKind.MISSED_CONDITION


def test_hints_and_retries_reduce_score_relative_to_same_answer(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
) -> None:
    plain = apply_assessment_event(catalog, ledger, _event(event_id="plain"))
    penalized = apply_assessment_event(
        catalog,
        ledger,
        _event(event_id="penalized", hint_count=2, attempt_count=2),
    )

    assert plain.mastery_after[0][1] == pytest.approx(0.56)
    assert penalized.mastery_after[0][1] == pytest.approx(0.48)
    assert penalized.mastery_after[0][1] < plain.mastery_after[0][1]


def test_confidence_increases_with_each_new_event_and_stays_bounded(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
) -> None:
    current = ledger
    confidences: list[float] = []
    start = datetime(2026, 7, 30, 8, tzinfo=UTC)
    for sequence in range(40):
        result = apply_assessment_event(
            catalog,
            current,
            _event(
                event_id=f"event-{sequence}",
                timestamp=start + timedelta(minutes=sequence),
            ),
        )
        current = result.ledger
        confidences.append(current.profile.knowledge_mastery[0].confidence)

    assert confidences == sorted(confidences)
    assert confidences[0] == pytest.approx(0.34)
    assert 0 < confidences[-1] <= 1


@pytest.mark.parametrize(
    ("hints", "response_ms", "attempts", "expected"),
    [
        (2, 1000, 1, AssessmentErrorKind.CONCEPT_CONFUSION),
        (0, 120000, 1, AssessmentErrorKind.LOGIC_GAP),
        (0, 1000, 2, AssessmentErrorKind.CALCULATION_ERROR),
        (0, 1000, 1, AssessmentErrorKind.MISSED_CONDITION),
    ],
)
def test_incorrect_answer_classifies_deterministically(
    hints: int,
    response_ms: int,
    attempts: int,
    expected: AssessmentErrorKind,
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
) -> None:
    result = apply_assessment_event(
        catalog,
        ledger,
        _event(
            correct=False,
            hint_count=hints,
            response_time_ms=response_ms,
            attempt_count=attempts,
        ),
    )

    assert result.classified_error_kind is expected


def test_explicit_error_kind_overrides_heuristics(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
) -> None:
    result = apply_assessment_event(
        catalog,
        ledger,
        _event(
            correct=False,
            error_kind=AssessmentErrorKind.MISSED_CONDITION,
            hint_count=3,
            response_time_ms=180000,
            attempt_count=4,
        ),
    )

    assert result.classified_error_kind is AssessmentErrorKind.MISSED_CONDITION


def test_multi_concept_event_preserves_input_order_and_unrelated_mastery(
    catalog: OntologyCatalog,
    profile: LearnerProfileSnapshot,
) -> None:
    first, second, unrelated = (concept.id for concept in catalog.concepts()[:3])
    unrelated_mastery = KnowledgeMastery(
        concept_id=unrelated,
        mastery_score=0.80,
        assessment_status=AssessmentStatus.ASSESSED,
        confidence=0.90,
        observed_at=datetime(2026, 7, 29, tzinfo=UTC),
        evidence_refs=["earlier-assessment"],
    )
    source = profile.model_copy(
        update={"knowledge_mastery": [unrelated_mastery]},
        deep=True,
    )

    result = apply_assessment_event(
        catalog,
        AssessmentLedger(profile=source),
        _event(concept_ids=(second, first)),
    )

    assert result.affected_concept_ids == (second, first)
    assert tuple(item[0] for item in result.mastery_after) == (second, first)
    assert result.ledger.profile.knowledge_mastery[0] == unrelated_mastery
    assert [item.concept_id for item in result.ledger.profile.knowledge_mastery[1:]] == [
        second,
        first,
    ]


@pytest.mark.parametrize(
    ("profile_id", "profile_graph", "event_graph", "concept_ids", "message"),
    [
        (
            "wrong-profile",
            "ai-course-v1",
            "ai-course-v1",
            ("ml.optimization.gradient-descent",),
            "event profile ID does not match ledger",
        ),
        (
            "profile-assessment",
            "ai-course-v0",
            "ai-course-v1",
            ("ml.optimization.gradient-descent",),
            "ledger graph version does not match catalog",
        ),
        (
            "profile-assessment",
            "ai-course-v1",
            "ai-course-v0",
            ("ml.optimization.gradient-descent",),
            "event graph version does not match catalog",
        ),
        (
            "profile-assessment",
            "ai-course-v1",
            "ai-course-v1",
            ("unknown.concept",),
            "unknown assessment concept",
        ),
    ],
)
def test_scope_failures_leave_original_ledger_unchanged(
    profile_id: str,
    profile_graph: str,
    event_graph: str,
    concept_ids: tuple[str, ...],
    message: str,
    catalog: OntologyCatalog,
    profile: LearnerProfileSnapshot,
) -> None:
    source = profile.model_copy(update={"graph_version": profile_graph}, deep=True)
    ledger = AssessmentLedger(profile=source)
    before = ledger.model_dump()

    with pytest.raises(ValueError, match=message):
        apply_assessment_event(
            catalog,
            ledger,
            _event(
                profile_id=profile_id,
                graph_version=event_graph,
                concept_ids=concept_ids,
            ),
        )

    assert ledger.model_dump() == before


def test_apply_revalidates_tampered_event_before_updating(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
) -> None:
    tampered = _event().model_copy(
        update={"error_kind": AssessmentErrorKind.LOGIC_GAP}
    )

    with pytest.raises(ValidationError, match="correct answers cannot include error_kind"):
        apply_assessment_event(catalog, ledger, tampered)

    assert ledger.processed_event_ids == ()
    assert ledger.profile.knowledge_mastery == []


def test_incorrect_events_aggregate_counts_ratios_and_evidence_per_concept(
    catalog: OntologyCatalog,
    ledger: AssessmentLedger,
) -> None:
    first = apply_assessment_event(
        catalog,
        ledger,
        _event(event_id="confusion-1", correct=False, hint_count=2),
    )
    second = apply_assessment_event(
        catalog,
        first.ledger,
        _event(
            event_id="logic-1",
            correct=False,
            response_time_ms=120000,
            timestamp=datetime(2026, 7, 30, 9, tzinfo=UTC),
        ),
    )
    third = apply_assessment_event(
        catalog,
        second.ledger,
        _event(
            event_id="confusion-2",
            correct=False,
            hint_count=2,
            timestamp=datetime(2026, 7, 30, 10, tzinfo=UTC),
        ),
    )

    patterns = {
        item.code: item for item in third.ledger.profile.error_patterns
    }
    assert patterns["concept_confusion"].count == 2
    assert patterns["concept_confusion"].ratio == pytest.approx(2 / 3)
    assert patterns["concept_confusion"].evidence_refs == [
        "confusion-1",
        "confusion-2",
    ]
    assert patterns["logic_gap"].count == 1
    assert patterns["logic_gap"].ratio == pytest.approx(1 / 3)


def test_error_update_preserves_unrelated_patterns_and_correct_adds_none(
    catalog: OntologyCatalog,
    profile: LearnerProfileSnapshot,
) -> None:
    affected = "ml.optimization.gradient-descent"
    unrelated = catalog.concepts()[0].id
    unrelated_pattern = ErrorPattern(
        code="legacy_error",
        count=4,
        ratio=0.80,
        concept_ids=[unrelated],
        evidence_refs=["legacy-run"],
    )
    source = profile.model_copy(
        update={"error_patterns": [unrelated_pattern]},
        deep=True,
    )

    correct = apply_assessment_event(
        catalog,
        AssessmentLedger(profile=source),
        _event(concept_ids=(affected,), correct=True),
    )

    assert correct.ledger.profile.error_patterns == [unrelated_pattern]
    assert correct.classified_error_kind is None
    assert source.error_patterns == [unrelated_pattern]
