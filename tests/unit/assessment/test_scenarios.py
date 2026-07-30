from datetime import UTC, datetime

import pytest

from skillforge_kb.assessment import (
    AssessmentEvent,
    AssessmentLedger,
    apply_assessment_event,
)
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import (
    AssessmentStatus,
    ErrorPattern,
    KnowledgeMastery,
    LearnerProfileSnapshot,
)
from skillforge_kb.planning.planner import CoursePlanner

CONCEPT_ID = "ml.optimization.gradient-descent"


def _event() -> AssessmentEvent:
    return AssessmentEvent(
        event_id="scenario-event",
        profile_id="profile-assessment",
        graph_version="ai-course-v1",
        concept_ids=(CONCEPT_ID,),
        correct=True,
        response_time_ms=1500,
        hint_count=0,
        attempt_count=1,
        timestamp=datetime(2026, 7, 30, 12, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("initial_mastery", "expected_before", "expected_after"),
    [
        (None, 0.50, 0.56),
        (
            KnowledgeMastery(
                concept_id=CONCEPT_ID,
                mastery_score=None,
                assessment_status=AssessmentStatus.NOT_ASSESSED,
                confidence=0.10,
            ),
            0.50,
            0.56,
        ),
        (
            KnowledgeMastery(
                concept_id=CONCEPT_ID,
                mastery_score=0.80,
                assessment_status=AssessmentStatus.ASSESSED,
                confidence=0.70,
                observed_at=datetime(2026, 7, 29, tzinfo=UTC),
                evidence_refs=["assessment-run-1"],
            ),
            0.80,
            0.824,
        ),
    ],
    ids=("missing", "not-assessed", "assessed"),
)
def test_profile_starting_states_update_from_the_correct_baseline(
    initial_mastery: KnowledgeMastery | None,
    expected_before: float,
    expected_after: float,
    catalog: OntologyCatalog,
    profile: LearnerProfileSnapshot,
) -> None:
    knowledge_mastery = [] if initial_mastery is None else [initial_mastery]
    source = profile.model_copy(
        update={"knowledge_mastery": knowledge_mastery},
        deep=True,
    )

    result = apply_assessment_event(catalog, AssessmentLedger(profile=source), _event())

    assert result.mastery_before[0][1] == pytest.approx(expected_before)
    assert result.mastery_after[0][1] == pytest.approx(expected_after)
    assert result.ledger.profile.knowledge_mastery[0].assessment_status is (
        AssessmentStatus.ASSESSED
    )


def test_existing_error_counts_are_reaggregated_per_concept(
    catalog: OntologyCatalog,
    profile: LearnerProfileSnapshot,
) -> None:
    source = profile.model_copy(
        update={
            "error_patterns": [
                ErrorPattern(
                    code="concept_confusion",
                    count=2,
                    ratio=1,
                    concept_ids=[CONCEPT_ID],
                    evidence_refs=["earlier-1", "earlier-2"],
                )
            ]
        },
        deep=True,
    )
    incorrect = _event().model_copy(
        update={
            "event_id": "new-logic-error",
            "correct": False,
            "response_time_ms": 120000,
        }
    )

    result = apply_assessment_event(
        catalog,
        AssessmentLedger(profile=source),
        incorrect,
    )
    patterns = {item.code: item for item in result.ledger.profile.error_patterns}

    assert patterns["concept_confusion"].count == 2
    assert patterns["concept_confusion"].ratio == pytest.approx(2 / 3)
    assert patterns["logic_gap"].count == 1
    assert patterns["logic_gap"].ratio == pytest.approx(1 / 3)


def test_assessment_update_does_not_mutate_or_invoke_course_planning(
    catalog: OntologyCatalog,
    profile: LearnerProfileSnapshot,
) -> None:
    planner = CoursePlanner(catalog)
    original_payload = profile.model_dump()
    original_decision = planner.plan(profile)

    result = apply_assessment_event(catalog, AssessmentLedger(profile=profile), _event())

    assert profile.model_dump() == original_payload
    assert planner.plan(profile) == original_decision
    assert result.ledger.profile != profile
    assert result.ledger.profile.assessment_runs == profile.assessment_runs
