from datetime import UTC, datetime

import pytest

import skillforge_kb.platform.graph as graph_module
from skillforge_kb.agents.resource_agent import ResourceGenerationAgent
from skillforge_kb.evaluation import evaluate_knowledge_tracing
from skillforge_kb.platform.graph import PlatformGraphDependencies, PlatformService
from skillforge_kb.platform.models import (
    AssessmentModel,
    ExecutionMode,
    PlatformRunRequest,
    PlatformRunStatus,
    PlatformStage,
)
from skillforge_kb.platform.repository import InMemoryPlatformRunRepository


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 16, tzinfo=UTC)


class RecordingPlanningAgent:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[object] = []

    def invoke(self, event, thread_id: str):
        self.calls.append((event, thread_id))
        return self.result.model_copy(update={"thread_id": thread_id})


class StaticHandoffFactory:
    def __init__(self, handoff) -> None:
        self.handoff = handoff

    def build(self, planning, profile):
        return self.handoff


class StaticRetrievalAgent:
    def __init__(self, result, *, fail: bool = False) -> None:
        self.result = result
        self.fail = fail

    def retrieve(self, request, handoff):
        if self.fail:
            raise ValueError("retrieval identity mismatch")
        return self.result.model_copy(update={"request": request})


class RecordingResourceAgent:
    def __init__(self) -> None:
        self.delegate = ResourceGenerationAgent()
        self.strict_calls: list[object] = []
        self.preview_calls: list[object] = []

    def generate_strict(self, handoff, bundle):
        self.strict_calls.append((handoff, bundle))
        return self.delegate.generate_strict(handoff, bundle)

    def generate_preview(self, profile, handoff, retrieval):
        self.preview_calls.append((profile, handoff, retrieval))
        return self.delegate.generate_preview(profile, handoff, retrieval)


def _service(platform_case, *, retrieval_fails: bool = False):
    planning = RecordingPlanningAgent(platform_case["planning"])
    retrieval = StaticRetrievalAgent(
        platform_case["retrieval"],
        fail=retrieval_fails,
    )
    resource = RecordingResourceAgent()
    dependencies = PlatformGraphDependencies(
        planning_agent=planning,
        retrieval_agent=retrieval,
        resource_agent=resource,
        handoff_factory=StaticHandoffFactory(platform_case["handoff"]),
        evidence_index=platform_case["evidence_index"],
        clock=FixedClock(),
        catalog=platform_case["catalog"],
    )
    service = PlatformService(
        dependencies,
        InMemoryPlatformRunRepository(),
    )
    return service, planning, resource


def test_bkt_assessment_dispatches_to_bkt_updater(
    monkeypatch: pytest.MonkeyPatch,
    platform_case,
    profile,
) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="dispatch-bkt-run",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
            assessment_model=AssessmentModel.BKT,
        )
    )
    assert initial.planning is not None
    assert initial.planning.current_node is not None
    calls: list[str] = []
    original = graph_module.apply_bkt_event

    def capture(catalog, ledger, event, parameters=None):
        calls.append("bkt")
        return original(catalog, ledger, event, parameters)

    monkeypatch.setattr(graph_module, "apply_bkt_event", capture)
    result = service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "dispatch-bkt-1",
            "concept_id": initial.planning.current_node.concept_id,
            "score": 1.0,
            "response_time_ms": 1000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )

    assert result.status is PlatformRunStatus.COMPLETED
    assert calls == ["bkt"]


def test_rule_assessment_records_prior_mastery(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="obs-rule",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    assert initial.planning is not None
    assert initial.planning.current_node is not None
    concept_id = initial.planning.current_node.concept_id

    service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "obs-rule-1",
            "concept_id": concept_id,
            "score": 1.0,
            "response_time_ms": 1000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )

    observation = service._repository.get_prediction_observation(
        initial.run_id,
        "obs-rule-1",
    )
    assert observation is not None
    assert observation.model_version == "rule.v1"
    assert observation.predicted_mastery == 0.50


def test_practice_review_persists_completion_progress(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="practice-progress",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    assert initial.planning is not None and initial.planning.current_node is not None
    concept_id = initial.planning.current_node.concept_id
    exercise = initial.resources.preview_package.draft.practical_guide.exercise
    source = "\n".join(f"{token} = 1" for token in exercise.required_tokens)
    source += "\nresult = 1\nprint(result)"
    review = service.review_practice(
        initial.run_id,
        {"concept_id": concept_id, "source": source},
    )
    assert review.accepted is True
    updated = service.get(initial.run_id)
    assert updated is not None and updated.learning_progress is not None
    assert updated.learning_progress.practice_completed is True
    assert updated.learning_progress.assessment_passed is False


def test_accepted_practice_updates_profile_and_knowledge_tracing_history(
    platform_case,
    profile,
) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="practice-kt-update",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    assert initial.planning is not None and initial.planning.current_node is not None
    concept_id = initial.planning.current_node.concept_id
    exercise = initial.resources.preview_package.draft.practical_guide.exercise
    source = "\n".join(f"{token} = 1" for token in exercise.required_tokens)
    source += "\nresult = 1\nprint(result)"

    review = service.review_practice(
        initial.run_id,
        {"concept_id": concept_id, "source": source},
    )

    assert review.accepted is True
    request = service._repository.get_request(initial.run_id)
    assert request is not None
    mastery = next(item for item in request.profile.knowledge_mastery if item.concept_id == concept_id)
    assert mastery.mastery_score is not None and mastery.mastery_score > 0.50
    observations = service._repository.list_prediction_observations(initial.run_id)
    assert len(observations) == 1
    assert observations[0].concept_id == concept_id
    assert observations[0].correct is True


def test_failed_assessment_records_remediation_progress(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="failed-assessment-progress",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    assert initial.planning is not None and initial.planning.current_node is not None
    concept_id = initial.planning.current_node.concept_id
    result = service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "failed-assessment-1",
            "concept_id": concept_id,
            "score": 0.0,
            "response_time_ms": 1000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )
    assert result.learning_progress is not None
    assert result.learning_progress.failed_attempts == 1
    assert result.learning_progress.remediation_required is True


def test_passing_assessment_without_practice_does_not_complete_node(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="assessment-without-practice",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    assert initial.planning is not None and initial.planning.current_node is not None
    concept_id = initial.planning.current_node.concept_id
    result = service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "assessment-without-practice-1",
            "concept_id": concept_id,
            "score": 1.0,
            "response_time_ms": 1000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )
    assert result.learning_progress is not None
    assert result.learning_progress.assessment_passed is True
    assert result.learning_progress.practice_completed is False
    assert result.planning is not None and result.planning.current_node is not None
    assert result.planning.current_node.concept_id == concept_id
    assert result.status is PlatformRunStatus.COMPLETED
    assert result.learning_progress.can_complete is False


def test_explicit_completion_requires_recorded_learning_gates(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="completion-gate",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    assert initial.planning is not None and initial.planning.current_node is not None
    concept_id = initial.planning.current_node.concept_id
    exercise = initial.resources.preview_package.draft.practical_guide.exercise
    source = "\n".join(f"{token} = 1" for token in exercise.required_tokens)
    source += "\nresult = 1\nprint(result)"
    assert service.review_practice(
        initial.run_id,
        {"concept_id": concept_id, "source": source},
    ).accepted
    with pytest.raises(ValueError, match="completion gate"):
        service.complete_current_node(initial.run_id, concept_id)


def test_bkt_assessment_records_prior_and_replay_is_idempotent(
    platform_case,
    profile,
) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="obs-bkt",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
            assessment_model=AssessmentModel.BKT,
        )
    )
    assert initial.planning is not None
    assert initial.planning.current_node is not None
    concept_id = initial.planning.current_node.concept_id
    submission = {
        "assessment_id": "obs-bkt-1",
        "concept_id": concept_id,
        "score": 1.0,
        "response_time_ms": 1000,
        "hint_count": 0,
        "attempt_count": 1,
    }

    first = service.submit_assessment(initial.run_id, submission)
    replay = service.submit_assessment(initial.run_id, submission)
    observation = service._repository.get_prediction_observation(
        initial.run_id,
        "obs-bkt-1",
    )

    assert replay == first
    assert observation is not None
    assert observation.model_version == "bkt.v1"
    assert observation.predicted_mastery == 0.20
    assert len(service._repository.list_prediction_observations(initial.run_id)) == 1


def test_saved_observations_feed_knowledge_tracing_evaluation(
    platform_case,
    profile,
) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="obs-export",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    assert initial.planning is not None
    assert initial.planning.current_node is not None

    service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "obs-export-1",
            "concept_id": initial.planning.current_node.concept_id,
            "score": 1.0,
            "response_time_ms": 1000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )
    observations = service._repository.list_prediction_observations(initial.run_id)
    report = evaluate_knowledge_tracing(observations)

    assert report.metrics.sample_count == 1


def test_service_evaluates_profile_observations(platform_case, profile) -> None:
    service, _, _ = _service(platform_case)
    initial = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="eval-entry",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )
    assert initial.planning is not None
    assert initial.planning.current_node is not None
    service.submit_assessment(
        initial.run_id,
        {
            "assessment_id": "eval-1",
            "concept_id": initial.planning.current_node.concept_id,
            "score": 1.0,
            "response_time_ms": 1000,
            "hint_count": 0,
            "attempt_count": 1,
        },
    )

    reports = service.evaluate_profile_knowledge_tracing(profile.profile_id)

    assert len(reports) == 1
    assert reports[0].metrics.sample_count == 1


def test_service_evaluation_rejects_profile_without_observations(
    platform_case,
    profile,
) -> None:
    service, _, _ = _service(platform_case)

    with pytest.raises(ValueError, match="no prediction observations"):
        service.evaluate_profile_knowledge_tracing(profile.profile_id)


def test_strict_gap_blocks_without_calling_resource_agent(platform_case, profile) -> None:
    service, _, resource = _service(platform_case)
    result = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="strict-gap",
            execution_mode=ExecutionMode.STRICT,
        )
    )

    assert result.status is PlatformRunStatus.BLOCKED
    assert resource.strict_calls == []
    assert resource.preview_calls == []
    assert result.steps[-1].stage is PlatformStage.FINALIZE


def test_candidate_preview_runs_only_without_hard_blockers(platform_case, profile) -> None:
    service, _, resource = _service(platform_case)
    result = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="candidate-preview",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )

    assert result.status is PlatformRunStatus.COMPLETED
    assert result.resources is not None
    assert result.resources.publication_status == "candidate_draft"
    assert len(resource.preview_calls) == 1


def test_candidate_preview_blocks_when_no_candidate_evidence(platform_case, profile) -> None:
    service, _, resource = _service(platform_case)
    retrieval = platform_case["retrieval"]
    partial = retrieval.model_copy(
        update={
            "candidate_evidence": (),
            "concept_evidence": {retrieval.request.concept_id: ()},
            "evidence_summary": retrieval.evidence_summary.model_copy(
                update={"candidate_count": 0, "available_content_kinds": ()}
            ),
        }
    )
    service, _, resource = _service(
        platform_case | {"retrieval": partial}
    )

    result = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="candidate-partial-evidence",
            execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
        )
    )

    assert result.status is PlatformRunStatus.BLOCKED
    assert result.resources is None
    assert resource.preview_calls == []


def test_retrieval_contract_failure_stops_generation(platform_case, profile) -> None:
    service, _, resource = _service(platform_case, retrieval_fails=True)
    result = service.run(
        PlatformRunRequest(
            profile=profile,
            idempotency_key="retrieval-failure",
        )
    )

    assert result.status is PlatformRunStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "contract_mismatch"
    assert resource.strict_calls == []
    assert resource.preview_calls == []


def test_identical_replay_does_not_invoke_agents_twice(platform_case, profile) -> None:
    service, planning, resource = _service(platform_case)
    request = PlatformRunRequest(
        profile=profile,
        idempotency_key="replay",
        execution_mode=ExecutionMode.CANDIDATE_PREVIEW,
    )

    first = service.run(request)
    second = service.run(request)

    assert second == first
    assert len(planning.calls) == 1
    assert len(resource.preview_calls) == 1
