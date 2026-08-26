from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillforge_kb.agents.planning_agent_models import (
    CoursePlanningAgentResult,
    PlanningAgentEvent,
    PlanningAgentStatus,
    PlanningEventKind,
    PlanningNextAction,
    build_event_digest,
)
from skillforge_kb.agents.planning_tools import (
    PlanningToolResult,
    create_course_plan_tool,
)
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.planning.adaptation import NodeWeightEngine
from skillforge_kb.planning.models import PathStatus


@pytest.fixture
def profile(catalog) -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="profile-planning-agent",
        learner_ref="b" * 64,
        graph_version=catalog.course_document.version,
        generated_at=datetime(2026, 7, 29, tzinfo=UTC),
    )


def test_initialize_requires_only_a_profile(profile) -> None:
    event = PlanningAgentEvent(
        event_id="event_" + "1" * 64,
        kind=PlanningEventKind.INITIALIZE,
        profile=profile,
    )

    assert event.completed_concept_ids == ()
    assert event.profile == profile


def test_profile_refresh_requires_profile_and_no_completions(profile) -> None:
    event = PlanningAgentEvent(
        event_id="event_" + "2" * 64,
        kind=PlanningEventKind.PROFILE_REFRESHED,
        profile=profile,
    )

    assert event.profile == profile
    assert event.completed_concept_ids == ()


def test_completion_requires_unique_concepts_and_allows_optional_profile(profile) -> None:
    event = PlanningAgentEvent(
        event_id="event_" + "3" * 64,
        kind=PlanningEventKind.CONCEPTS_COMPLETED,
        profile=profile,
        completed_concept_ids=("math.linear-algebra.scalar",),
    )

    assert event.completed_concept_ids == ("math.linear-algebra.scalar",)

    with pytest.raises(ValidationError, match="completed concept IDs must be unique"):
        PlanningAgentEvent(
            event_id="event_" + "4" * 64,
            kind=PlanningEventKind.CONCEPTS_COMPLETED,
            completed_concept_ids=("math.linear-algebra.scalar",) * 2,
        )


def test_reset_rejects_profile_and_completions(profile) -> None:
    with pytest.raises(ValidationError, match="reset event"):
        PlanningAgentEvent(
            event_id="event_" + "5" * 64,
            kind=PlanningEventKind.RESET,
            profile=profile,
        )
    with pytest.raises(ValidationError, match="reset event"):
        PlanningAgentEvent(
            event_id="event_" + "6" * 64,
            kind=PlanningEventKind.RESET,
            completed_concept_ids=("math.linear-algebra.scalar",),
        )


@pytest.mark.parametrize(
    "kind",
    (
        PlanningEventKind.INITIALIZE,
        PlanningEventKind.PROFILE_REFRESHED,
    ),
)
def test_profile_events_reject_missing_profile(kind) -> None:
    with pytest.raises(ValidationError, match="requires a profile"):
        PlanningAgentEvent(
            event_id="event_" + "7" * 64,
            kind=kind,
        )


def test_completion_rejects_empty_concept_ids() -> None:
    with pytest.raises(ValidationError, match="requires completed concept IDs"):
        PlanningAgentEvent(
            event_id="event_" + "8" * 64,
            kind=PlanningEventKind.CONCEPTS_COMPLETED,
        )


def test_noncompletion_events_reject_completed_ids(profile) -> None:
    with pytest.raises(ValidationError, match="cannot include completed concept IDs"):
        PlanningAgentEvent(
            event_id="event_" + "9" * 64,
            kind=PlanningEventKind.INITIALIZE,
            profile=profile,
            completed_concept_ids=("math.linear-algebra.scalar",),
        )


def test_event_digest_is_stable_and_content_sensitive(profile) -> None:
    first = PlanningAgentEvent(
        event_id="event_" + "a" * 64,
        kind=PlanningEventKind.INITIALIZE,
        profile=profile,
    )
    same = PlanningAgentEvent.model_validate(first.model_dump())
    changed = first.model_copy(
        update={"profile": profile.model_copy(update={"profile_id": "changed-profile"})}
    )

    assert build_event_digest(first) == build_event_digest(same)
    assert build_event_digest(first) != build_event_digest(changed)


def test_ready_result_requires_matching_current_adaptation(catalog, profile) -> None:
    tool_result = PlanningToolResult.model_validate(
        create_course_plan_tool(catalog).invoke(
            {"profile": profile.model_dump(mode="json")}
        )
    )
    current = next(
        node for node in tool_result.path.nodes if node.status is PathStatus.AVAILABLE
    )
    root = Path(__file__).parents[3] / "resources" / "ontology"
    attributes = load_concept_attributes(catalog, root / "concept_attributes_v1.yaml")
    engine = NodeWeightEngine(catalog, attributes)
    adaptations = tuple(
        engine.evaluate(profile, node)
        for node in tool_result.path.nodes
        if node.status not in {PathStatus.COMPLETED, PathStatus.SKIPPED}
    )
    adaptation = next(
        item for item in adaptations if item.concept_id == current.concept_id
    )

    result = CoursePlanningAgentResult(
        thread_id="student-1",
        status=PlanningAgentStatus.READY,
        next_action=PlanningNextAction.START_CURRENT_NODE,
        path=tool_result.path,
        current_node=current,
        current_adaptation=adaptation,
        adaptations=adaptations,
        planning_audit=tool_result.audit,
        last_event_id="event_" + "a" * 64,
    )

    assert result.current_adaptation.concept_id == result.current_node.concept_id

    wrong = next(
        item
        for item in adaptations
        if item.concept_id != current.concept_id
    )
    with pytest.raises(ValidationError, match="current adaptation"):
        CoursePlanningAgentResult(
            thread_id="student-1",
            status=PlanningAgentStatus.READY,
            next_action=PlanningNextAction.START_CURRENT_NODE,
            path=tool_result.path,
            current_node=current,
            current_adaptation=wrong,
            adaptations=adaptations,
            planning_audit=tool_result.audit,
            last_event_id="event_" + "a" * 64,
        )


def test_idle_and_completed_result_contracts(catalog, profile) -> None:
    idle = CoursePlanningAgentResult(
        thread_id="student-1",
        status=PlanningAgentStatus.IDLE,
        next_action=PlanningNextAction.WAIT_FOR_EVENT,
    )
    assert idle.path is None

    path = PlanningToolResult.model_validate(
        create_course_plan_tool(catalog).invoke(
            {"profile": profile.model_dump(mode="json")}
        )
    ).path
    completed_path = path.model_copy(
        update={
            "nodes": tuple(
                node
                if node.status is PathStatus.SKIPPED
                else node.model_copy(update={"status": PathStatus.COMPLETED})
                for node in path.nodes
            )
        }
    )
    completed = CoursePlanningAgentResult(
        thread_id="student-1",
        status=PlanningAgentStatus.COMPLETED,
        next_action=PlanningNextAction.COURSE_COMPLETE,
        path=completed_path,
    )
    assert completed.current_node is None

    with pytest.raises(ValidationError, match="completed result requires a finished path"):
        CoursePlanningAgentResult(
            thread_id="student-1",
            status=PlanningAgentStatus.COMPLETED,
            next_action=PlanningNextAction.COURSE_COMPLETE,
            path=path,
        )

    with pytest.raises(ValidationError, match="idle result cannot contain a path"):
        CoursePlanningAgentResult(
            thread_id="student-1",
            status=PlanningAgentStatus.IDLE,
            next_action=PlanningNextAction.WAIT_FOR_EVENT,
            path=path,
        )
