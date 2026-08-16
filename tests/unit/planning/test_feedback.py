from datetime import UTC, datetime
from datetime import datetime as DateTime

import pytest

from skillforge_kb.agents.feedback import PlanningFeedbackCoordinator
from skillforge_kb.assessment.update import AssessmentEvent, AssessmentLedger
from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import LearnerProfileSnapshot


@pytest.fixture
def assessment_profile(catalog: OntologyCatalog) -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="profile-planning-feedback",
        learner_ref="0" * 64,
        graph_version=catalog.course_document.version,
        generated_at=DateTime(2026, 8, 10, tzinfo=UTC),
    )


def test_feedback_produces_profile_refresh_event(catalog, assessment_profile) -> None:
    ledger = AssessmentLedger(profile=assessment_profile)
    event = AssessmentEvent(
        event_id="assessment-event-1",
        profile_id=assessment_profile.profile_id,
        graph_version=catalog.course_document.version,
        concept_ids=("math.linear-algebra.scalar",),
        correct=True,
        response_time_ms=1000,
        hint_count=0,
        attempt_count=1,
        timestamp=datetime(2026, 8, 10, tzinfo=UTC),
    )

    result = PlanningFeedbackCoordinator(catalog).apply(ledger, event)

    assert result.applied is True
    assert result.profile.profile_id == assessment_profile.profile_id
    assert result.planning_event is not None
    assert result.planning_event.kind.value == "profile_refreshed"
    assert result.planning_event.profile == result.profile


def test_duplicate_feedback_does_not_emit_refresh_event(
    catalog,
    assessment_profile,
) -> None:
    ledger = AssessmentLedger(profile=assessment_profile)
    event = AssessmentEvent(
        event_id="assessment-event-duplicate",
        profile_id=assessment_profile.profile_id,
        graph_version=catalog.course_document.version,
        concept_ids=("math.linear-algebra.scalar",),
        correct=False,
        response_time_ms=1000,
        hint_count=0,
        attempt_count=1,
        timestamp=datetime(2026, 8, 10, tzinfo=UTC),
    )
    first = PlanningFeedbackCoordinator(catalog).apply(ledger, event)

    second = PlanningFeedbackCoordinator(catalog).apply(first.ledger, event)

    assert second.applied is False
    assert second.planning_event is None


def test_feedback_rejects_profile_graph_mismatch(catalog, assessment_profile) -> None:
    ledger = AssessmentLedger(profile=assessment_profile)
    event = AssessmentEvent(
        event_id="assessment-event-mismatch",
        profile_id=assessment_profile.profile_id,
        graph_version="ai-course-v2",
        concept_ids=("math.linear-algebra.scalar",),
        correct=True,
        response_time_ms=1000,
        hint_count=0,
        attempt_count=1,
        timestamp=datetime(2026, 8, 10, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="graph version"):
        PlanningFeedbackCoordinator(catalog).apply(ledger, event)
