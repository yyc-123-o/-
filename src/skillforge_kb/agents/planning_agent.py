import re
from collections.abc import Mapping
from enum import StrEnum
from hashlib import sha256
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import TypeAdapter, ValidationError

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.concept_attributes import ConceptAttributeCatalog
from skillforge_kb.planning.adaptation import NodeWeightEngine, NodeWeightPolicy
from skillforge_kb.planning.models import PathDecision, PathNode, PathStatus, PlannerPolicy
from skillforge_kb.planning.ordering import PlanningError
from skillforge_kb.retrieval.models import KnowledgeQuery
from skillforge_kb.retrieval.tool import KnowledgeRetrievalTool

from .planning_agent_models import (
    CoursePlanningAgentResult,
    CoursePlanningAgentState,
    PlanningAgentEvent,
    PlanningAgentFailure,
    PlanningAgentFailureCode,
    PlanningAgentStatus,
    PlanningEventKind,
    PlanningNextAction,
    ProcessedPlanningEvent,
    build_event_digest,
)
from .planning_tools import (
    PlanningToolResult,
    create_course_plan_tool,
    update_course_plan_tool,
)

PlanningGraph = CompiledStateGraph[
    CoursePlanningAgentState,
    None,
    CoursePlanningAgentState,
    CoursePlanningAgentState,
]

_STATE_ADAPTER = TypeAdapter(CoursePlanningAgentState)


def build_knowledge_query(
    catalog: OntologyCatalog,
    node: PathNode,
) -> KnowledgeQuery:
    concept = catalog.get_concept(node.concept_id)
    section = catalog.section_for(node.concept_id)
    chapter = next(item for item in catalog.chapters() if item.id == section.chapter_id)
    parts = [
        concept.names.zh,
        concept.names.en,
        *concept.aliases,
        concept.summary,
        section.title.zh,
        section.title.en,
        chapter.title.zh,
        chapter.title.en,
        *concept.levels[0].learning_outcomes,
    ]
    if node.delivery_depth is not None:
        level = next(
            item for item in concept.levels if item.level is node.delivery_depth
        )
        parts.extend(level.learning_outcomes)
        parts.append(node.delivery_depth.value)
    query = " ".join(part for part in parts if part.strip())
    return KnowledgeQuery(
        query=query,
        concept_id=node.concept_id,
        anchors=(concept.names.zh, concept.names.en),
    )


class _Route(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    RESET = "reset"
    DUPLICATE = "duplicate"
    FAILURE = "failure"


class _AfterPath(StrEnum):
    ADAPT = "adapt"
    FAILURE = "failure"


class _AfterSelection(StrEnum):
    RETRIEVE = "retrieve"
    DONE = "done"


class CoursePlanningAgent:
    def __init__(self, graph: PlanningGraph) -> None:
        self._graph = graph

    @classmethod
    def create(
        cls,
        catalog: OntologyCatalog,
        attributes: ConceptAttributeCatalog,
        planner_policy: PlannerPolicy | None = None,
        node_weight_policy: NodeWeightPolicy | None = None,
        *,
        knowledge_tool: KnowledgeRetrievalTool | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> "CoursePlanningAgent":
        return cls(
            build_course_planning_graph(
                catalog,
                attributes,
                planner_policy,
                node_weight_policy,
                knowledge_tool=knowledge_tool,
                checkpointer=checkpointer,
            )
        )

    def invoke(
        self,
        event: PlanningAgentEvent | Mapping[str, object],
        thread_id: str,
    ) -> CoursePlanningAgentResult:
        config = _thread_config(thread_id)
        try:
            validated_event = PlanningAgentEvent.model_validate(event)
        except ValidationError as exc:
            return self._invalid_event_result(event, thread_id, exc)
        values = self._graph.invoke({"event": validated_event}, config=config)
        return _build_result(thread_id, values)

    async def ainvoke(
        self,
        event: PlanningAgentEvent | Mapping[str, object],
        thread_id: str,
    ) -> CoursePlanningAgentResult:
        config = _thread_config(thread_id)
        try:
            validated_event = PlanningAgentEvent.model_validate(event)
        except ValidationError as exc:
            return self._invalid_event_result(event, thread_id, exc)
        values = await self._graph.ainvoke({"event": validated_event}, config=config)
        return _build_result(thread_id, values)

    def get_state(self, thread_id: str) -> CoursePlanningAgentResult | None:
        snapshot = self._graph.get_state(_thread_config(thread_id))
        if not snapshot.values:
            return None
        return _build_result(thread_id, snapshot.values)

    def _invalid_event_result(
        self,
        event: PlanningAgentEvent | Mapping[str, object],
        thread_id: str,
        error: ValidationError,
    ) -> CoursePlanningAgentResult:
        previous = self.get_state(thread_id)
        invalid_event_id = _invalid_event_id(event)
        return CoursePlanningAgentResult(
            thread_id=thread_id,
            status=PlanningAgentStatus.FAILED,
            next_action=PlanningNextAction.RETRY_EVENT,
            path=previous.path if previous is not None else None,
            current_node=previous.current_node if previous is not None else None,
            current_adaptation=(
                previous.current_adaptation if previous is not None else None
            ),
            adaptations=previous.adaptations if previous is not None else (),
            knowledge_context=(
                previous.knowledge_context if previous is not None else None
            ),
            planning_audit=(
                previous.planning_audit if previous is not None else None
            ),
            failure=PlanningAgentFailure(
                code=PlanningAgentFailureCode.INVALID_EVENT,
                message=str(error),
                event_id=invalid_event_id,
            ),
            last_event_id=invalid_event_id,
            event_duplicate=False,
        )


def build_course_planning_graph(
    catalog: OntologyCatalog,
    attributes: ConceptAttributeCatalog,
    planner_policy: PlannerPolicy | None = None,
    node_weight_policy: NodeWeightPolicy | None = None,
    *,
    knowledge_tool: KnowledgeRetrievalTool | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> PlanningGraph:
    create_tool = create_course_plan_tool(catalog, planner_policy)
    update_tool = update_course_plan_tool(catalog, planner_policy)
    weight_engine = NodeWeightEngine(
        catalog,
        attributes,
        planner_policy,
        node_weight_policy,
    )

    def route_event(state: CoursePlanningAgentState) -> CoursePlanningAgentState:
        event = state["event"]
        event_digest = build_event_digest(event)
        existing_event = next(
            (
                item
                for item in state.get("processed_events", ())
                if item.event_id == event.event_id
            ),
            None,
        )
        if existing_event is not None:
            if existing_event.event_digest == event_digest:
                return {
                    "route": _Route.DUPLICATE.value,
                    "last_event_id": event.event_id,
                    "event_duplicate": True,
                }
            return _failure_update(
                event,
                PlanningAgentFailureCode.EVENT_ID_CONFLICT,
                "event ID was already used with different content",
            )

        status = state.get("status", PlanningAgentStatus.IDLE)
        if event.kind is PlanningEventKind.RESET:
            return {
                "route": _Route.RESET.value,
                "event_duplicate": False,
            }
        if status in {PlanningAgentStatus.FAILED, PlanningAgentStatus.COMPLETED}:
            return _failure_update(
                event,
                PlanningAgentFailureCode.INVALID_TRANSITION,
                f"{status.value} session requires reset",
            )
        if event.kind is PlanningEventKind.INITIALIZE:
            if state.get("path") is not None or state.get("profile") is not None:
                return _failure_update(
                    event,
                    PlanningAgentFailureCode.INVALID_TRANSITION,
                    "initialized session requires reset before reinitialization",
                )
            return {
                "route": _Route.CREATE.value,
                "status": PlanningAgentStatus.PLANNING,
                "event_duplicate": False,
                "failure": None,
            }
        if state.get("path") is None or state.get("profile") is None:
            return _failure_update(
                event,
                PlanningAgentFailureCode.INVALID_TRANSITION,
                "planning session must be initialized before updates",
            )
        return {
            "route": _Route.UPDATE.value,
            "status": PlanningAgentStatus.UPDATING,
            "event_duplicate": False,
            "failure": None,
        }

    def create_path(state: CoursePlanningAgentState) -> CoursePlanningAgentState:
        event = state["event"]
        assert event.profile is not None
        try:
            result = PlanningToolResult.model_validate(
                create_tool.invoke(
                    {
                        "profile": event.profile.model_dump(mode="json"),
                        "completed_concept_ids": [],
                        "allow_skips": True,
                    }
                )
            )
        except (PlanningError, ValidationError, ValueError) as exc:
            return _failure_update(
                event,
                PlanningAgentFailureCode.PLANNING_ERROR,
                str(exc),
            )
        return {
            "candidate_profile": event.profile,
            "candidate_path": result.path,
            "candidate_audit": result.audit,
        }

    def update_path(state: CoursePlanningAgentState) -> CoursePlanningAgentState:
        event = state["event"]
        existing_path = state.get("path")
        existing_profile = state.get("profile")
        assert existing_path is not None and existing_profile is not None
        candidate_profile = event.profile or existing_profile
        try:
            result = PlanningToolResult.model_validate(
                update_tool.invoke(
                    {
                        "existing": existing_path.model_dump(mode="json"),
                        "profile": candidate_profile.model_dump(mode="json"),
                        "completed_concept_ids": list(event.completed_concept_ids),
                    }
                )
            )
        except (PlanningError, ValidationError, ValueError) as exc:
            return _failure_update(
                event,
                PlanningAgentFailureCode.PLANNING_ERROR,
                str(exc),
            )
        return {
            "candidate_profile": candidate_profile,
            "candidate_path": result.path,
            "candidate_audit": result.audit,
        }

    def recompute_adaptations(
        state: CoursePlanningAgentState,
    ) -> CoursePlanningAgentState:
        event = state["event"]
        path = state.get("candidate_path")
        profile = state.get("candidate_profile")
        assert path is not None and profile is not None
        completed_ids = {
            node.concept_id
            for node in path.nodes
            if node.status is PathStatus.COMPLETED
        }
        try:
            adaptations = tuple(
                weight_engine.evaluate(profile, node, completed_ids)
                for node in path.nodes
                if node.status not in {PathStatus.COMPLETED, PathStatus.SKIPPED}
            )
        except ValueError as exc:
            return _failure_update(
                event,
                PlanningAgentFailureCode.ADAPTATION_ERROR,
                str(exc),
            )
        return {"candidate_adaptations": adaptations}

    def select_current_node(
        state: CoursePlanningAgentState,
    ) -> CoursePlanningAgentState:
        event = state["event"]
        path = state.get("candidate_path")
        profile = state.get("candidate_profile")
        audit = state.get("candidate_audit")
        adaptations = state.get("candidate_adaptations", ())
        assert path is not None and profile is not None and audit is not None
        unfinished = tuple(
            node
            for node in path.nodes
            if node.status not in {PathStatus.COMPLETED, PathStatus.SKIPPED}
        )
        if not unfinished:
            return _commit_candidate(
                state,
                status=PlanningAgentStatus.COMPLETED,
                next_action=PlanningNextAction.COURSE_COMPLETE,
                current_node_id=None,
            )
        available = tuple(
            node for node in unfinished if node.status is PathStatus.AVAILABLE
        )
        if not available:
            return _failure_update(
                event,
                PlanningAgentFailureCode.NO_AVAILABLE_NODE,
                "unfinished path has no available node",
            )
        if len(available) > 1:
            return _failure_update(
                event,
                PlanningAgentFailureCode.MULTIPLE_AVAILABLE_NODES,
                "unfinished path has multiple available nodes",
            )
        current = available[0]
        if not any(item.concept_id == current.concept_id for item in adaptations):
            return _failure_update(
                event,
                PlanningAgentFailureCode.ADAPTATION_ERROR,
                "current node is missing an adaptation decision",
            )
        return _commit_candidate(
            state,
            status=PlanningAgentStatus.READY,
            next_action=PlanningNextAction.START_CURRENT_NODE,
            current_node_id=current.concept_id,
        )

    def retrieve_current_node_knowledge(
        state: CoursePlanningAgentState,
    ) -> CoursePlanningAgentState:
        if knowledge_tool is None:
            return {"knowledge_context": None}
        path = state.get("path")
        current_node_id = state.get("current_node_id")
        if path is None or current_node_id is None:
            return {"knowledge_context": None}
        current_node = next(
            (node for node in path.nodes if node.concept_id == current_node_id),
            None,
        )
        if current_node is None:
            return {"knowledge_context": None}
        query = build_knowledge_query(catalog, current_node)
        return {"knowledge_context": knowledge_tool.invoke(query)}

    def reset_state(state: CoursePlanningAgentState) -> CoursePlanningAgentState:
        event = state["event"]
        processed = _append_processed_event(state, event)
        return {
            "route": _Route.RESET.value,
            "profile": None,
            "path": None,
            "adaptations": (),
            "current_node_id": None,
            "status": PlanningAgentStatus.IDLE,
            "next_action": PlanningNextAction.WAIT_FOR_EVENT,
            "knowledge_context": None,
            "processed_events": processed,
            "last_event_id": event.event_id,
            "event_duplicate": False,
            "planning_audit": None,
            "failure": None,
            "candidate_profile": None,
            "candidate_path": None,
            "candidate_adaptations": (),
            "candidate_audit": None,
        }

    def after_selection(state: CoursePlanningAgentState) -> str:
        return _after_selection(state, knowledge_tool)

    builder: StateGraph[
        CoursePlanningAgentState,
        None,
        CoursePlanningAgentState,
        CoursePlanningAgentState,
    ] = StateGraph(CoursePlanningAgentState)
    builder.add_node("route_event", route_event)
    builder.add_node("create_path", create_path)
    builder.add_node("update_path", update_path)
    builder.add_node("recompute_adaptations", recompute_adaptations)
    builder.add_node("select_current_node", select_current_node)
    builder.add_node("retrieve_current_node_knowledge", retrieve_current_node_knowledge)
    builder.add_node("reset_state", reset_state)
    builder.add_edge(START, "route_event")
    builder.add_conditional_edges(
        "route_event",
        _route_from_state,
        {
            _Route.CREATE.value: "create_path",
            _Route.UPDATE.value: "update_path",
            _Route.RESET.value: "reset_state",
            _Route.DUPLICATE.value: END,
            _Route.FAILURE.value: END,
        },
    )
    builder.add_conditional_edges(
        "create_path",
        _after_path,
        {
            _AfterPath.ADAPT.value: "recompute_adaptations",
            _AfterPath.FAILURE.value: END,
        },
    )
    builder.add_conditional_edges(
        "update_path",
        _after_path,
        {
            _AfterPath.ADAPT.value: "recompute_adaptations",
            _AfterPath.FAILURE.value: END,
        },
    )
    builder.add_conditional_edges(
        "recompute_adaptations",
        _after_path,
        {
            _AfterPath.ADAPT.value: "select_current_node",
            _AfterPath.FAILURE.value: END,
        },
    )
    builder.add_conditional_edges(
        "select_current_node",
        after_selection,
        {
            _AfterSelection.RETRIEVE.value: "retrieve_current_node_knowledge",
            _AfterSelection.DONE.value: END,
        },
    )
    builder.add_edge("retrieve_current_node_knowledge", END)
    builder.add_edge("reset_state", END)
    return builder.compile(
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver()
    )


def _route_from_state(state: CoursePlanningAgentState) -> str:
    return state.get("route", _Route.FAILURE.value)


def _after_path(state: CoursePlanningAgentState) -> str:
    if state.get("failure") is not None:
        return _AfterPath.FAILURE.value
    return _AfterPath.ADAPT.value


def _after_selection(
    state: CoursePlanningAgentState,
    knowledge_tool: KnowledgeRetrievalTool | None,
) -> str:
    if knowledge_tool is not None and state.get("status") is PlanningAgentStatus.READY:
        return _AfterSelection.RETRIEVE.value
    return _AfterSelection.DONE.value


def _failure_update(
    event: PlanningAgentEvent,
    code: PlanningAgentFailureCode,
    message: str,
) -> CoursePlanningAgentState:
    return {
        "route": _Route.FAILURE.value,
        "status": PlanningAgentStatus.FAILED,
        "next_action": PlanningNextAction.RESET_REQUIRED,
        "last_event_id": event.event_id,
        "event_duplicate": False,
        "failure": PlanningAgentFailure(
            code=code,
            message=message,
            event_id=event.event_id,
        ),
        "candidate_profile": None,
        "candidate_path": None,
        "candidate_adaptations": (),
        "candidate_audit": None,
    }


def _append_processed_event(
    state: CoursePlanningAgentState,
    event: PlanningAgentEvent,
) -> tuple[ProcessedPlanningEvent, ...]:
    return (
        *state.get("processed_events", ()),
        ProcessedPlanningEvent(
            event_id=event.event_id,
            event_digest=build_event_digest(event),
        ),
    )


def _commit_candidate(
    state: CoursePlanningAgentState,
    *,
    status: PlanningAgentStatus,
    next_action: PlanningNextAction,
    current_node_id: str | None,
) -> CoursePlanningAgentState:
    event = state["event"]
    profile = state.get("candidate_profile")
    path = state.get("candidate_path")
    audit = state.get("candidate_audit")
    assert profile is not None and path is not None and audit is not None
    return {
        "profile": profile,
        "path": path,
        "adaptations": state.get("candidate_adaptations", ()),
        "current_node_id": current_node_id,
        "status": status,
        "next_action": next_action,
        "knowledge_context": None,
        "processed_events": _append_processed_event(state, event),
        "last_event_id": event.event_id,
        "event_duplicate": False,
        "planning_audit": audit,
        "failure": None,
        "candidate_profile": None,
        "candidate_path": None,
        "candidate_adaptations": (),
        "candidate_audit": None,
    }


def _thread_config(thread_id: str) -> RunnableConfig:
    if not thread_id.strip():
        raise ValueError("thread ID must not be empty")
    return {"configurable": {"thread_id": thread_id}}


def _invalid_event_id(
    event: PlanningAgentEvent | Mapping[str, object],
) -> str:
    value = event.event_id if isinstance(event, PlanningAgentEvent) else event.get("event_id")
    if isinstance(value, str) and re.fullmatch(r"event_[0-9a-f]{64}", value):
        return value
    digest = sha256(repr(event).encode("utf-8")).hexdigest()
    return f"event_{digest}"


def _build_result(
    thread_id: str,
    raw_values: object,
) -> CoursePlanningAgentResult:
    values = _STATE_ADAPTER.validate_python(raw_values)
    path_value = values.get("path")
    path = PathDecision.model_validate(path_value) if path_value is not None else None
    current_node_id = values.get("current_node_id")
    current_node = None
    if path is not None and isinstance(current_node_id, str):
        current_node = next(
            (node for node in path.nodes if node.concept_id == current_node_id),
            None,
        )
    adaptations = tuple(values.get("adaptations", ()))
    current_adaptation = next(
        (
            item
            for item in adaptations
            if current_node is not None and item.concept_id == current_node.concept_id
        ),
        None,
    )
    return CoursePlanningAgentResult(
        thread_id=thread_id,
        status=values.get("status", PlanningAgentStatus.IDLE),
        next_action=values.get("next_action", PlanningNextAction.WAIT_FOR_EVENT),
        path=path,
        current_node=current_node,
        current_adaptation=current_adaptation,
        adaptations=adaptations,
        knowledge_context=values.get("knowledge_context"),
        planning_audit=values.get("planning_audit"),
        failure=values.get("failure"),
        last_event_id=values.get("last_event_id"),
        event_duplicate=bool(values.get("event_duplicate", False)),
    )
