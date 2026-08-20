import json
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.ontology.models import (
    CONCEPT_ID_PATTERN,
    LearnerProfileSnapshot,
)
from skillforge_kb.planning.adaptation import NodeAdaptationDecision
from skillforge_kb.planning.models import PathDecision, PathNode, PathStatus
from skillforge_kb.retrieval.models import KnowledgeRetrievalResult

from .planning_tools import PlanningToolAudit

ConceptId = Annotated[str, Field(pattern=CONCEPT_ID_PATTERN)]


class PlanningEventKind(StrEnum):
    INITIALIZE = "initialize"
    PROFILE_REFRESHED = "profile_refreshed"
    CONCEPTS_COMPLETED = "concepts_completed"
    RESET = "reset"


class PlanningAgentStatus(StrEnum):
    IDLE = "idle"
    PLANNING = "planning"
    UPDATING = "updating"
    READY = "ready"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanningNextAction(StrEnum):
    START_CURRENT_NODE = "start_current_node"
    WAIT_FOR_EVENT = "wait_for_event"
    COURSE_COMPLETE = "course_complete"
    RETRY_EVENT = "retry_event"
    RESET_REQUIRED = "reset_required"


class PlanningAgentFailureCode(StrEnum):
    INVALID_EVENT = "invalid_event"
    INVALID_TRANSITION = "invalid_transition"
    EVENT_ID_CONFLICT = "event_id_conflict"
    PLANNING_ERROR = "planning_error"
    ADAPTATION_ERROR = "adaptation_error"
    NO_AVAILABLE_NODE = "no_available_node"
    MULTIPLE_AVAILABLE_NODES = "multiple_available_nodes"


class PlanningAgentEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["planning-agent-event.v1"] = "planning-agent-event.v1"
    event_id: str = Field(pattern=r"^event_[0-9a-f]{64}$")
    kind: PlanningEventKind
    profile: LearnerProfileSnapshot | None = None
    completed_concept_ids: tuple[ConceptId, ...] = ()
    target_concept_id: ConceptId | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "PlanningAgentEvent":
        if len(self.completed_concept_ids) != len(set(self.completed_concept_ids)):
            raise ValueError("completed concept IDs must be unique")
        if self.kind in {
            PlanningEventKind.INITIALIZE,
            PlanningEventKind.PROFILE_REFRESHED,
        } and self.profile is None:
            raise ValueError(f"{self.kind.value} event requires a profile")
        if self.kind is PlanningEventKind.CONCEPTS_COMPLETED:
            if not self.completed_concept_ids:
                raise ValueError("concepts_completed event requires completed concept IDs")
        elif self.completed_concept_ids:
            if self.kind is PlanningEventKind.RESET:
                raise ValueError("reset event cannot include completed concept IDs")
            raise ValueError(f"{self.kind.value} event cannot include completed concept IDs")
        if self.kind is PlanningEventKind.RESET and self.profile is not None:
            raise ValueError("reset event cannot include a profile")
        if self.kind in {
            PlanningEventKind.CONCEPTS_COMPLETED,
            PlanningEventKind.RESET,
        } and self.target_concept_id is not None:
            raise ValueError(f"{self.kind.value} event cannot include a target concept")
        return self


class PlanningAgentFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: PlanningAgentFailureCode
    message: str = Field(min_length=1)
    event_id: str = Field(pattern=r"^event_[0-9a-f]{64}$")


class ProcessedPlanningEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(pattern=r"^event_[0-9a-f]{64}$")
    event_digest: str = Field(pattern=r"^event_digest_[0-9a-f]{64}$")


class CoursePlanningAgentState(TypedDict, total=False):
    event: PlanningAgentEvent
    route: str
    profile: LearnerProfileSnapshot | None
    path: PathDecision | None
    adaptations: tuple[NodeAdaptationDecision, ...]
    current_node_id: str | None
    status: PlanningAgentStatus
    next_action: PlanningNextAction
    processed_events: tuple[ProcessedPlanningEvent, ...]
    last_event_id: str | None
    event_duplicate: bool
    knowledge_context: KnowledgeRetrievalResult | None
    planning_audit: PlanningToolAudit | None
    failure: PlanningAgentFailure | None
    candidate_profile: LearnerProfileSnapshot | None
    candidate_path: PathDecision | None
    candidate_adaptations: tuple[NodeAdaptationDecision, ...]
    candidate_audit: PlanningToolAudit | None


class CoursePlanningAgentResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["course-planning-agent-result.v1"] = (
        "course-planning-agent-result.v1"
    )
    thread_id: str = Field(min_length=1)
    status: PlanningAgentStatus
    next_action: PlanningNextAction
    path: PathDecision | None = None
    current_node: PathNode | None = None
    current_adaptation: NodeAdaptationDecision | None = None
    adaptations: tuple[NodeAdaptationDecision, ...] = ()
    knowledge_context: KnowledgeRetrievalResult | None = None
    planning_audit: PlanningToolAudit | None = None
    failure: PlanningAgentFailure | None = None
    last_event_id: str | None = Field(
        default=None,
        pattern=r"^event_[0-9a-f]{64}$",
    )
    event_duplicate: bool = False

    @model_validator(mode="after")
    def validate_state(self) -> "CoursePlanningAgentResult":
        if self.status is PlanningAgentStatus.IDLE:
            if self.path is not None:
                raise ValueError("idle result cannot contain a path")
            if self.adaptations or self.current_node or self.current_adaptation:
                raise ValueError("idle result cannot contain planning decisions")
            if self.knowledge_context is not None:
                raise ValueError("idle result cannot contain knowledge context")
            if self.next_action is not PlanningNextAction.WAIT_FOR_EVENT:
                raise ValueError("idle result must wait for an event")

        if self.status is PlanningAgentStatus.COMPLETED:
            self._validate_completed_state()

        if self.path is None:
            if self.adaptations:
                raise ValueError("adaptations require a path")
            if self.knowledge_context is not None:
                raise ValueError("knowledge context requires a path")
        else:
            expected_ids = tuple(
                node.concept_id
                for node in self.path.nodes
                if node.status not in {PathStatus.COMPLETED, PathStatus.SKIPPED}
            )
            actual_ids = tuple(item.concept_id for item in self.adaptations)
            if actual_ids != expected_ids:
                raise ValueError("adaptations must match unfinished path nodes in order")

        if self.status is PlanningAgentStatus.READY:
            self._validate_ready_state()
        if self.status is PlanningAgentStatus.FAILED:
            if self.failure is None:
                raise ValueError("failed result requires failure details")
            expected_action = (
                PlanningNextAction.RETRY_EVENT
                if self.failure.code is PlanningAgentFailureCode.INVALID_EVENT
                else PlanningNextAction.RESET_REQUIRED
            )
            if self.next_action is not expected_action:
                raise ValueError("failed result has an invalid recovery action")
        elif self.failure is not None:
            raise ValueError("non-failed result cannot contain failure details")
        return self

    def _validate_ready_state(self) -> None:
        if self.path is None or self.current_node is None:
            raise ValueError("ready result requires a path and current node")
        if self.current_adaptation is None:
            raise ValueError("ready result requires a current adaptation")
        if self.next_action is not PlanningNextAction.START_CURRENT_NODE:
            raise ValueError("ready result must start the current node")
        available = tuple(
            node for node in self.path.nodes if node.status is PathStatus.AVAILABLE
        )
        if available != (self.current_node,):
            raise ValueError("current node must be the unique available path node")
        if self.current_adaptation.concept_id != self.current_node.concept_id:
            raise ValueError("current adaptation does not match current node")
        if self.current_adaptation not in self.adaptations:
            raise ValueError("current adaptation must be present in adaptations")

    def _validate_completed_state(self) -> None:
        if self.path is None:
            raise ValueError("completed result requires a path")
        if any(
            node.status not in {PathStatus.COMPLETED, PathStatus.SKIPPED}
            for node in self.path.nodes
        ):
            raise ValueError("completed result requires a finished path")
        if self.current_node is not None or self.current_adaptation is not None:
            raise ValueError("completed result cannot contain a current node")
        if self.knowledge_context is not None:
            raise ValueError("completed result cannot contain knowledge context")
        if self.next_action is not PlanningNextAction.COURSE_COMPLETE:
            raise ValueError("completed result must mark the course complete")


def build_event_digest(event: PlanningAgentEvent) -> str:
    canonical = json.dumps(
        event.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"event_digest_{sha256(canonical.encode('utf-8')).hexdigest()}"
