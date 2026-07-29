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
from skillforge_kb.ontology.models import (
    AbilityScore,
    AssessmentStatus,
    KnowledgeMastery,
    LearnerProfileSnapshot,
)
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


def completion_event(
    *concept_ids: str,
    label: str = "completion",
) -> PlanningAgentEvent:
    return PlanningAgentEvent(
        event_id=event_id(label),
        kind=PlanningEventKind.CONCEPTS_COMPLETED,
        completed_concept_ids=tuple(concept_ids),
    )


def reset_event(*, label: str = "reset") -> PlanningAgentEvent:
    return PlanningAgentEvent(
        event_id=event_id(label),
        kind=PlanningEventKind.RESET,
    )


def enriched_profile(
    profile: LearnerProfileSnapshot,
    concept_id: str,
) -> LearnerProfileSnapshot:
    assessment_id = "assessment-agent-refresh"
    return profile.model_copy(
        update={
            "generated_at": datetime(2026, 7, 30, tzinfo=UTC),
            "knowledge_mastery": [
                KnowledgeMastery(
                    concept_id=concept_id,
                    mastery_score=0.84,
                    assessment_status=AssessmentStatus.ASSESSED,
                    confidence=0.90,
                    observed_at=datetime(2026, 7, 30, tzinfo=UTC),
                    evidence_refs=[assessment_id],
                )
            ],
            "abilities": {
                dimension: AbilityScore(
                    score=0.90,
                    confidence=0.90,
                    assessment_run_id=assessment_id,
                )
                for dimension in (
                    "theoretical_understanding",
                    "coding_ability",
                    "mathematical_foundation",
                    "problem_solving",
                )
            },
        }
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


def test_completion_advances_current_node_without_changing_path_id(
    agent,
    profile,
) -> None:
    initial = agent.invoke(initialize_event(profile), thread_id="student-1")
    assert initial.path is not None and initial.current_node is not None
    completed_id = initial.current_node.concept_id

    updated = agent.invoke(
        completion_event(completed_id),
        thread_id="student-1",
    )

    assert updated.status is PlanningAgentStatus.READY
    assert updated.path is not None and updated.current_node is not None
    assert updated.path.path_id == initial.path.path_id
    assert [node.concept_id for node in updated.path.nodes] == [
        node.concept_id for node in initial.path.nodes
    ]
    assert updated.current_node.concept_id != completed_id
    completed = next(
        node for node in updated.path.nodes if node.concept_id == completed_id
    )
    assert completed.status is PathStatus.COMPLETED
    assert completed_id not in {item.concept_id for item in updated.adaptations}


def test_profile_refresh_preserves_path_and_recomputes_support(agent, profile) -> None:
    initial = agent.invoke(initialize_event(profile), thread_id="student-1")
    assert initial.path is not None
    assert initial.current_node is not None
    assert initial.current_adaptation is not None
    refreshed_profile = enriched_profile(profile, initial.current_node.concept_id)

    updated = agent.invoke(
        refresh_event(refreshed_profile),
        thread_id="student-1",
    )

    assert updated.path is not None
    assert updated.current_node is not None
    assert updated.current_adaptation is not None
    assert updated.path.path_id == initial.path.path_id
    assert [node.concept_id for node in updated.path.nodes] == [
        node.concept_id for node in initial.path.nodes
    ]
    assert updated.current_node.concept_id == initial.current_node.concept_id
    assert (
        updated.current_adaptation.support_need_score
        < initial.current_adaptation.support_need_score
    )


def test_completing_all_remaining_nodes_finishes_course(agent, profile) -> None:
    initial = agent.invoke(initialize_event(profile), thread_id="student-1")
    assert initial.path is not None
    remaining_ids = tuple(
        node.concept_id
        for node in initial.path.nodes
        if node.status is not PathStatus.SKIPPED
    )

    completed = agent.invoke(
        completion_event(*remaining_ids, label="complete-course"),
        thread_id="student-1",
    )

    assert completed.status is PlanningAgentStatus.COMPLETED
    assert completed.next_action is PlanningNextAction.COURSE_COMPLETE
    assert completed.path is not None
    assert completed.current_node is None
    assert completed.current_adaptation is None
    assert completed.adaptations == ()
    assert all(
        node.status in {PathStatus.COMPLETED, PathStatus.SKIPPED}
        for node in completed.path.nodes
    )


def test_duplicate_event_is_a_no_op(agent, profile) -> None:
    event = initialize_event(profile)
    first = agent.invoke(event, thread_id="student-1")

    duplicate = agent.invoke(event, thread_id="student-1")

    assert duplicate.event_duplicate is True
    assert duplicate.status is first.status
    assert duplicate.path == first.path
    assert duplicate.adaptations == first.adaptations
    assert duplicate.current_node == first.current_node
    assert duplicate.failure is None


def test_event_id_conflict_preserves_last_valid_path(agent, profile) -> None:
    original = initialize_event(profile, label="shared-event-id")
    initial = agent.invoke(original, thread_id="student-1")
    conflicting_profile = profile.model_copy(update={"profile_id": "profile-conflict"})
    conflicting = initialize_event(conflicting_profile, label="shared-event-id")

    result = agent.invoke(conflicting, thread_id="student-1")

    assert result.status is PlanningAgentStatus.FAILED
    assert result.path == initial.path
    assert result.adaptations == initial.adaptations
    assert result.failure is not None
    assert result.failure.code is PlanningAgentFailureCode.EVENT_ID_CONFLICT


def test_reset_clears_session_and_allows_reinitialize(agent, profile) -> None:
    agent.invoke(initialize_event(profile), thread_id="student-1")

    reset = agent.invoke(reset_event(), thread_id="student-1")

    assert reset.status is PlanningAgentStatus.IDLE
    assert reset.next_action is PlanningNextAction.WAIT_FOR_EVENT
    assert reset.path is None
    assert reset.adaptations == ()
    assert reset.current_node is None
    assert reset.failure is None
    assert agent.get_state("student-1") == reset

    reinitialized = agent.invoke(
        initialize_event(profile, label="reinitialize"),
        thread_id="student-1",
    )
    assert reinitialized.status is PlanningAgentStatus.READY
    assert reinitialized.path is not None


def test_thread_ids_isolate_course_planning_sessions(agent, profile) -> None:
    another_profile = profile.model_copy(
        update={
            "profile_id": "profile-another-student",
            "learner_ref": "d" * 64,
        }
    )

    first = agent.invoke(initialize_event(profile), thread_id="student-1")
    second = agent.invoke(initialize_event(another_profile), thread_id="student-2")

    assert first.path is not None and second.path is not None
    assert first.path.profile_id == profile.profile_id
    assert second.path.profile_id == another_profile.profile_id
    assert first.path.path_id != second.path.path_id
    assert agent.get_state("student-1") == first
    assert agent.get_state("student-2") == second


@pytest.mark.asyncio
async def test_async_invocation_matches_sync_semantics(agent, profile) -> None:
    event = initialize_event(profile)

    synchronous = agent.invoke(event, thread_id="student-sync")
    asynchronous = await agent.ainvoke(event, thread_id="student-async")

    assert asynchronous.status is synchronous.status
    assert asynchronous.next_action is synchronous.next_action
    assert asynchronous.path == synchronous.path
    assert asynchronous.adaptations == synchronous.adaptations
    assert asynchronous.current_node == synchronous.current_node


def test_unknown_thread_has_no_state(agent) -> None:
    assert agent.get_state("unknown-student") is None


def test_invalid_raw_event_preserves_checkpointed_state(agent, profile) -> None:
    initial = agent.invoke(initialize_event(profile), thread_id="student-1")
    invalid_event = {
        "event_id": event_id("invalid-event"),
        "kind": PlanningEventKind.CONCEPTS_COMPLETED,
        "completed_concept_ids": [],
    }

    result = agent.invoke(invalid_event, thread_id="student-1")

    assert result.status is PlanningAgentStatus.FAILED
    assert result.path == initial.path
    assert result.adaptations == initial.adaptations
    assert result.failure is not None
    assert result.failure.code is PlanningAgentFailureCode.INVALID_EVENT
    assert agent.get_state("student-1") == initial


def test_agent_is_available_from_public_agents_api() -> None:
    from skillforge_kb import agents

    assert agents.CoursePlanningAgent is CoursePlanningAgent
    assert agents.PlanningAgentEvent is PlanningAgentEvent
    assert agents.PlanningAgentStatus is PlanningAgentStatus
    assert agents.PlanningEventKind is PlanningEventKind
