from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from skillforge_kb.agents.planning_agent_models import (
    CoursePlanningAgentResult,
    PlanningAgentEvent,
    PlanningAgentStatus,
    PlanningEventKind,
)
from skillforge_kb.agents.resource_agent import ResourceAgentResult
from skillforge_kb.agents.retrieval_agent_models import (
    DomainRetrievalRequest,
    DomainRetrievalResult,
    EvidenceGap,
)
from skillforge_kb.evidence.manifest import EvidenceIndex
from skillforge_kb.resources.evidence_bundle import build_evidence_bundle
from skillforge_kb.resources.handoff import ResourceHandoffContract
from skillforge_kb.resources.models import ResourceBrief

from .models import (
    ExecutionMode,
    PlatformFailure,
    PlatformRunRequest,
    PlatformRunResult,
    PlatformRunStatus,
    PlatformStage,
    PlatformStepRecord,
    PlatformStepStatus,
    build_payload_digest,
    build_request_digest,
    build_run_id,
)
from .ports import (
    Clock,
    HandoffFactoryPort,
    PlanningAgentPort,
    PlatformRunRepository,
    ResourceAgentPort,
    RetrievalAgentPort,
)


class PlatformGraphState(TypedDict, total=False):
    request: PlatformRunRequest
    run_id: str
    route: str
    status: PlatformRunStatus
    planning: CoursePlanningAgentResult
    handoff: ResourceHandoffContract
    retrieval: DomainRetrievalResult
    resources: ResourceAgentResult
    evidence_gap: EvidenceGap
    failure: PlatformFailure
    steps: tuple[PlatformStepRecord, ...]


PlatformGraph = CompiledStateGraph[
    PlatformGraphState,
    None,
    PlatformGraphState,
    PlatformGraphState,
]


@dataclass(frozen=True)
class PlatformGraphDependencies:
    planning_agent: PlanningAgentPort
    retrieval_agent: RetrievalAgentPort
    resource_agent: ResourceAgentPort
    handoff_factory: HandoffFactoryPort
    evidence_index: EvidenceIndex
    clock: Clock


class PlatformService:
    def __init__(
        self,
        dependencies: PlatformGraphDependencies,
        repository: PlatformRunRepository,
    ) -> None:
        self._graph = build_platform_graph(dependencies)
        self._repository = repository
        self._lock = RLock()

    def run(self, request: PlatformRunRequest) -> PlatformRunResult:
        request = PlatformRunRequest.model_validate(request.model_dump())
        with self._lock:
            existing = self._repository.reserve(request)
            if existing is not None:
                return existing
            state = cast(
                PlatformGraphState,
                self._graph.invoke(
                    {
                        "request": request,
                        "run_id": build_run_id(request),
                        "status": PlatformRunStatus.PENDING,
                        "steps": (),
                    }
                ),
            )
            result = _result_from_state(state)
            self._repository.save(result)
            return result

    def peek(self, request: PlatformRunRequest) -> PlatformRunResult | None:
        return self._repository.peek(request)

    def get(self, run_id: str) -> PlatformRunResult | None:
        return self._repository.get(run_id)


def build_platform_graph(dependencies: PlatformGraphDependencies) -> PlatformGraph:
    def validate_input(state: PlatformGraphState) -> PlatformGraphState:
        request = PlatformRunRequest.model_validate(state["request"].model_dump())
        return _success_update(
            state,
            dependencies,
            PlatformStage.VALIDATE_INPUT,
            {"request": request, "status": PlatformRunStatus.PENDING},
            request,
        )

    def plan_course(state: PlatformGraphState) -> PlatformGraphState:
        request = state["request"]
        try:
            digest = build_request_digest(request)
            event = PlanningAgentEvent(
                event_id=f"event_{sha256(digest.encode('utf-8')).hexdigest()}",
                kind=PlanningEventKind.INITIALIZE,
                profile=request.profile,
                target_concept_id=request.target_concept_id,
            )
            planning = dependencies.planning_agent.invoke(event, state["run_id"])
            if (
                planning.status is not PlanningAgentStatus.READY
                or planning.path is None
                or planning.current_node is None
            ):
                message = (
                    planning.failure.message
                    if planning.failure is not None
                    else "planning Agent did not select a current node"
                )
                raise RuntimeError(message)
            return _success_update(
                state,
                dependencies,
                PlatformStage.PLAN_COURSE,
                {
                    "planning": planning,
                    "status": PlatformRunStatus.PLANNING,
                    "route": "continue",
                },
                planning,
            )
        except Exception as exc:
            return _failure_update(state, dependencies, PlatformStage.PLAN_COURSE, exc)

    def build_handoff_node(state: PlatformGraphState) -> PlatformGraphState:
        try:
            handoff = dependencies.handoff_factory.build(
                state["planning"],
                state["request"].profile,
            )
            return _success_update(
                state,
                dependencies,
                PlatformStage.BUILD_HANDOFF,
                {"handoff": handoff, "route": "continue"},
                handoff,
            )
        except Exception as exc:
            return _failure_update(state, dependencies, PlatformStage.BUILD_HANDOFF, exc)

    def retrieve_evidence(state: PlatformGraphState) -> PlatformGraphState:
        handoff = state["handoff"]
        request = state["request"]
        try:
            retrieval_request = DomainRetrievalRequest(
                original_query=(
                    f"{handoff.concept_id} {handoff.delivery_depth.value}"
                ),
                rewritten_queries=(
                    "卷积运算 CNN padding stride 输出尺寸",
                    "PyTorch nn.Conv2d 输入输出 shape 参数",
                    "卷积输出尺寸 参数量 padding stride 练习 答案",
                ),
                profile_id=handoff.profile_id,
                concept_id=handoff.concept_id,
                depth=handoff.delivery_depth,
                top_k=request.top_k,
            )
            retrieval = dependencies.retrieval_agent.retrieve(
                retrieval_request,
                handoff,
            )
            return _success_update(
                state,
                dependencies,
                PlatformStage.RETRIEVE_EVIDENCE,
                {
                    "retrieval": retrieval,
                    "status": PlatformRunStatus.RETRIEVING,
                    "route": "continue",
                },
                retrieval,
            )
        except Exception as exc:
            return _failure_update(
                state,
                dependencies,
                PlatformStage.RETRIEVE_EVIDENCE,
                exc,
            )

    def evaluate_gate(state: PlatformGraphState) -> PlatformGraphState:
        handoff = state["handoff"]
        retrieval = state["retrieval"]
        request = state["request"]
        if handoff.generation_gate.allowed and retrieval.evidence_gap is None:
            route = "strict"
            status = PlatformRunStatus.GENERATING
        elif (
            request.execution_mode is ExecutionMode.CANDIDATE_PREVIEW
            and set(handoff.generation_gate.blocking_codes)
            == {"blocked_missing_published_evidence"}
        ):
            route = "preview"
            status = PlatformRunStatus.GENERATING
        else:
            route = "blocked"
            status = PlatformRunStatus.BLOCKED
        gap = retrieval.evidence_gap
        if route == "blocked" and gap is None:
            gap = EvidenceGap(
                missing_content_kinds=handoff.evidence_filters.content_kinds,
                message=handoff.generation_gate.next_action,
            )
        values: PlatformGraphState = {
            "route": route,
            "status": status,
        }
        if gap is not None:
            values["evidence_gap"] = gap
        return _success_update(
            state,
            dependencies,
            PlatformStage.EVALUATE_GATE,
            values,
            {"route": route, "status": status.value},
            step_status=(
                PlatformStepStatus.BLOCKED
                if route == "blocked"
                else PlatformStepStatus.COMPLETED
            ),
        )

    def generate_strict(state: PlatformGraphState) -> PlatformGraphState:
        try:
            handoff = state["handoff"]
            brief = ResourceBrief.model_validate(handoff.model_dump())
            bundle = build_evidence_bundle(brief, dependencies.evidence_index)
            resources = dependencies.resource_agent.generate_strict(handoff, bundle)
            return _success_update(
                state,
                dependencies,
                PlatformStage.GENERATE_RESOURCE,
                {"resources": resources, "route": "continue"},
                resources,
            )
        except Exception as exc:
            return _failure_update(
                state,
                dependencies,
                PlatformStage.GENERATE_RESOURCE,
                exc,
            )

    def generate_preview(state: PlatformGraphState) -> PlatformGraphState:
        try:
            resources = dependencies.resource_agent.generate_preview(
                state["request"].profile,
                state["handoff"],
                state["retrieval"],
            )
            return _success_update(
                state,
                dependencies,
                PlatformStage.GENERATE_RESOURCE,
                {"resources": resources, "route": "continue"},
                resources,
            )
        except Exception as exc:
            return _failure_update(
                state,
                dependencies,
                PlatformStage.GENERATE_RESOURCE,
                exc,
            )

    def validate_resource(state: PlatformGraphState) -> PlatformGraphState:
        try:
            resources = ResourceAgentResult.model_validate(
                state["resources"].model_dump()
            )
            return _success_update(
                state,
                dependencies,
                PlatformStage.VALIDATE_RESOURCE,
                {"resources": resources, "route": "completed"},
                resources,
            )
        except Exception as exc:
            return _failure_update(
                state,
                dependencies,
                PlatformStage.VALIDATE_RESOURCE,
                exc,
            )

    def finalize_completed(state: PlatformGraphState) -> PlatformGraphState:
        return _success_update(
            state,
            dependencies,
            PlatformStage.FINALIZE,
            {"status": PlatformRunStatus.COMPLETED},
            {"status": PlatformRunStatus.COMPLETED.value},
        )

    def finalize_blocked(state: PlatformGraphState) -> PlatformGraphState:
        return _success_update(
            state,
            dependencies,
            PlatformStage.FINALIZE,
            {"status": PlatformRunStatus.BLOCKED},
            {"status": PlatformRunStatus.BLOCKED.value},
            step_status=PlatformStepStatus.BLOCKED,
        )

    def finalize_failed(state: PlatformGraphState) -> PlatformGraphState:
        return _success_update(
            state,
            dependencies,
            PlatformStage.FINALIZE,
            {"status": PlatformRunStatus.FAILED},
            {"status": PlatformRunStatus.FAILED.value},
            step_status=PlatformStepStatus.COMPLETED,
        )

    builder = StateGraph(PlatformGraphState)
    builder.add_node("validate_input", validate_input)
    builder.add_node("plan_course", plan_course)
    builder.add_node("build_handoff", build_handoff_node)
    builder.add_node("retrieve_evidence", retrieve_evidence)
    builder.add_node("evaluate_generation_gate", evaluate_gate)
    builder.add_node("strict_generate", generate_strict)
    builder.add_node("preview_generate", generate_preview)
    builder.add_node("validate_resource", validate_resource)
    builder.add_node("completed_finalize", finalize_completed)
    builder.add_node("blocked_finalize", finalize_blocked)
    builder.add_node("failed_finalize", finalize_failed)
    builder.add_edge(START, "validate_input")
    builder.add_edge("validate_input", "plan_course")
    builder.add_conditional_edges(
        "plan_course",
        _continue_or_failure,
        {"continue": "build_handoff", "failure": "failed_finalize"},
    )
    builder.add_conditional_edges(
        "build_handoff",
        _continue_or_failure,
        {"continue": "retrieve_evidence", "failure": "failed_finalize"},
    )
    builder.add_conditional_edges(
        "retrieve_evidence",
        _continue_or_failure,
        {"continue": "evaluate_generation_gate", "failure": "failed_finalize"},
    )
    builder.add_conditional_edges(
        "evaluate_generation_gate",
        lambda state: state["route"],
        {
            "strict": "strict_generate",
            "preview": "preview_generate",
            "blocked": "blocked_finalize",
        },
    )
    builder.add_conditional_edges(
        "strict_generate",
        _continue_or_failure,
        {"continue": "validate_resource", "failure": "failed_finalize"},
    )
    builder.add_conditional_edges(
        "preview_generate",
        _continue_or_failure,
        {"continue": "validate_resource", "failure": "failed_finalize"},
    )
    builder.add_conditional_edges(
        "validate_resource",
        _completed_or_failure,
        {"completed": "completed_finalize", "failure": "failed_finalize"},
    )
    builder.add_edge("completed_finalize", END)
    builder.add_edge("blocked_finalize", END)
    builder.add_edge("failed_finalize", END)
    return builder.compile()


def _continue_or_failure(state: PlatformGraphState) -> str:
    return "failure" if "failure" in state else "continue"


def _completed_or_failure(state: PlatformGraphState) -> str:
    return "failure" if "failure" in state else "completed"


def _success_update(
    state: PlatformGraphState,
    dependencies: PlatformGraphDependencies,
    stage: PlatformStage,
    values: PlatformGraphState,
    output: object,
    *,
    step_status: PlatformStepStatus = PlatformStepStatus.COMPLETED,
) -> PlatformGraphState:
    started = dependencies.clock.now()
    finished = dependencies.clock.now()
    input_payload = _last_stage_payload(state)
    step = PlatformStepRecord(
        stage=stage,
        status=step_status,
        started_at=started,
        finished_at=finished,
        input_digest=build_payload_digest(input_payload),
        output_digest=build_payload_digest(_serializable(output)),
    )
    return {**values, "steps": (*state.get("steps", ()), step)}


def _failure_update(
    state: PlatformGraphState,
    dependencies: PlatformGraphDependencies,
    stage: PlatformStage,
    error: Exception,
) -> PlatformGraphState:
    code = "contract_mismatch" if isinstance(error, ValueError) else f"{stage.value}_failed"
    failure = PlatformFailure(
        code=code,
        message=str(error) or type(error).__name__,
        stage=stage,
        retryable=not isinstance(error, ValueError),
    )
    now = dependencies.clock.now()
    step = PlatformStepRecord(
        stage=stage,
        status=PlatformStepStatus.FAILED,
        started_at=now,
        finished_at=now,
        input_digest=build_payload_digest(_last_stage_payload(state)),
        failure=failure,
    )
    return {
        "route": "failure",
        "status": PlatformRunStatus.FAILED,
        "failure": failure,
        "steps": (*state.get("steps", ()), step),
    }


def _last_stage_payload(state: PlatformGraphState) -> object:
    for key in ("resources", "retrieval", "handoff", "planning", "request"):
        if key in state:
            return _serializable(state[key])
    return {}


def _serializable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _result_from_state(state: PlatformGraphState) -> PlatformRunResult:
    return PlatformRunResult(
        run_id=state["run_id"],
        request_digest=build_request_digest(state["request"]),
        profile_id=state["request"].profile.profile_id,
        status=state["status"],
        planning=state.get("planning"),
        retrieval=state.get("retrieval"),
        handoff=state.get("handoff"),
        resources=state.get("resources"),
        evidence_gap=state.get("evidence_gap"),
        failure=state.get("failure"),
        steps=state.get("steps", ()),
    )
