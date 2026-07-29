from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from skillforge_kb.agents.planning_agent import CoursePlanningAgent
from skillforge_kb.agents.planning_agent_models import (
    PlanningAgentEvent,
    PlanningAgentFailureCode,
    PlanningAgentStatus,
    PlanningEventKind,
    PlanningNextAction,
)
from skillforge_kb.ontology.concept_attributes import load_concept_attributes
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.planning.models import PathStatus


def event_id(label: str) -> str:
    return f"event_{sha256(label.encode('utf-8')).hexdigest()}"


@pytest.fixture
def profile(catalog) -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id="profile-agent-lifecycle",
        learner_ref="c" * 64,
        graph_version=catalog.course_document.version,
        generated_at=datetime(2026, 7, 29, tzinfo=UTC),
    )


@pytest.fixture
def agent(catalog) -> CoursePlanningAgent:
    root = Path(__file__).parents[3] / "resources" / "ontology"
    attributes = load_concept_attributes(catalog, root / "concept_attributes_v1.yaml")
    return CoursePlanningAgent.create(catalog, attributes)


def initialize_event(
    profile: LearnerProfileSnapshot,
    *,
    label: str = "initialize",
) -> PlanningAgentEvent:
    return PlanningAgentEvent(
        event_id=event_id(label),
        kind=PlanningEventKind.INITIALIZE,
        profile=profile,
    )


def refresh_event(
    profile: LearnerProfileSnapshot,
    *,
    label: str = "refresh",
) -> PlanningAgentEvent:
    return PlanningAgentEvent(
        event_id=event_id(label),
        kind=PlanningEventKind.PROFILE_REFRESHED,
        profile=profile,
    )


def test_initialize_builds_a_ready_path(agent, profile) -> None:
    result = agent.invoke(initialize_event(profile), thread_id="student-1")

    assert result.status is PlanningAgentStatus.READY
    assert result.next_action is PlanningNextAction.START_CURRENT_NODE
    assert result.path is not None
    assert result.current_node is not None
    assert result.current_node.status is PathStatus.AVAILABLE
    assert result.current_adaptation is not None
    assert result.current_adaptation.concept_id == result.current_node.concept_id
    assert result.planning_audit is not None
    assert result.path.path_id == result.planning_audit.path_id
    unfinished = tuple(
        node.concept_id
        for node in result.path.nodes
        if node.status not in {PathStatus.COMPLETED, PathStatus.SKIPPED}
    )
    assert tuple(item.concept_id for item in result.adaptations) == unfinished


def test_update_before_initialize_returns_failure(agent, profile) -> None:
    result = agent.invoke(refresh_event(profile), thread_id="student-1")

    assert result.status is PlanningAgentStatus.FAILED
    assert result.next_action is PlanningNextAction.RESET_REQUIRED
    assert result.path is None
    assert result.failure is not None
    assert result.failure.code is PlanningAgentFailureCode.INVALID_TRANSITION


def test_new_initialize_after_initialize_requires_reset(agent, profile) -> None:
    initial = agent.invoke(
        initialize_event(profile, label="first-initialize"),
        thread_id="student-1",
    )
    result = agent.invoke(
        initialize_event(profile, label="second-initialize"),
        thread_id="student-1",
    )

    assert initial.path is not None
    assert result.status is PlanningAgentStatus.FAILED
    assert result.path == initial.path
    assert result.adaptations == initial.adaptations
    assert result.failure is not None
    assert result.failure.code is PlanningAgentFailureCode.INVALID_TRANSITION


def test_graph_version_mismatch_returns_planning_failure(agent, profile) -> None:
    invalid = profile.model_copy(update={"graph_version": "ai-course-v2"})

    result = agent.invoke(initialize_event(invalid), thread_id="student-1")

    assert result.status is PlanningAgentStatus.FAILED
    assert result.path is None
    assert result.failure is not None
    assert result.failure.code is PlanningAgentFailureCode.PLANNING_ERROR
    assert "graph version" in result.failure.message
