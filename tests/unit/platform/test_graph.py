from datetime import UTC, datetime

import pytest

from skillforge_kb.agents.resource_agent import ResourceGenerationAgent
import skillforge_kb.platform.graph as graph_module
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
