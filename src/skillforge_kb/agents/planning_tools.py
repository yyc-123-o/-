import json
from collections.abc import Callable
from enum import StrEnum
from hashlib import sha256
from typing import Literal, TypedDict

from langchain_core.tools import StructuredTool
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from skillforge_kb.ontology.catalog import OntologyCatalog
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.planning.models import PathDecision, PlannerPolicy
from skillforge_kb.planning.ordering import PlanningError
from skillforge_kb.planning.planner import CoursePlanner
from skillforge_kb.planning.updater import DepthUpdater


class PlanningOperation(StrEnum):
    CREATE = "create_course_plan"
    UPDATE = "update_course_plan"


class PlanningNodeStatus(StrEnum):
    PLANNED = "planned"
    UPDATED = "updated"
    FAILED = "failed"


class PlanningFailureCode(StrEnum):
    INVALID_STATE = "invalid_state"
    PLANNING_ERROR = "planning_error"


class CreateCoursePlanInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: LearnerProfileSnapshot
    completed_concept_ids: tuple[str, ...] = ()
    allow_skips: bool = True

    @field_validator("completed_concept_ids")
    @classmethod
    def validate_completed_concept_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_unique_completed_ids(value)


class UpdateCoursePlanInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    existing: PathDecision
    profile: LearnerProfileSnapshot
    completed_concept_ids: tuple[str, ...]

    @field_validator("completed_concept_ids")
    @classmethod
    def validate_completed_concept_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_unique_completed_ids(value)


class PlanningToolAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["planning-tool-audit.v1"] = "planning-tool-audit.v1"
    operation: PlanningOperation
    request_digest: str = Field(pattern=r"^request_[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^result_[0-9a-f]{64}$")
    path_id: str = Field(pattern=r"^path_[0-9a-f]{64}$")
    profile_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    policy_digest: str = Field(pattern=r"^policy_[0-9a-f]{64}$")


class PlanningToolResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["planning-tool-result.v1"] = "planning-tool-result.v1"
    path: PathDecision
    audit: PlanningToolAudit

    @model_validator(mode="after")
    def validate_audit(self) -> "PlanningToolResult":
        if self.audit.path_id != self.path.path_id:
            raise ValueError("audit path ID does not match result path")
        if self.audit.profile_id != self.path.profile_id:
            raise ValueError("audit profile ID does not match result path")
        if self.audit.graph_version != self.path.graph_version:
            raise ValueError("audit graph version does not match result path")
        if self.audit.policy_digest != self.path.policy_digest:
            raise ValueError("audit policy digest does not match result path")
        expected = build_result_digest(
            self.audit.operation,
            self.audit.request_digest,
            self.path,
        )
        if self.audit.result_digest != expected:
            raise ValueError("result digest does not match result content")
        return self


class PlanningNodeFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: PlanningFailureCode
    operation: PlanningOperation
    message: str = Field(min_length=1)


class CoursePlanningState(TypedDict, total=False):
    profile: LearnerProfileSnapshot
    path: PathDecision
    completed_concept_ids: tuple[str, ...]
    allow_skips: bool
    planning_status: PlanningNodeStatus
    planning_audit: PlanningToolAudit | None
    planning_failure: PlanningNodeFailure | None


def build_request_digest(
    operation: PlanningOperation,
    request: CreateCoursePlanInput | UpdateCoursePlanInput,
    policy_digest: str,
) -> str:
    if operation is PlanningOperation.CREATE and not isinstance(
        request, CreateCoursePlanInput
    ):
        raise ValueError("create operation requires create request")
    if operation is PlanningOperation.UPDATE and not isinstance(
        request, UpdateCoursePlanInput
    ):
        raise ValueError("update operation requires update request")
    payload = request.model_dump(mode="json")
    payload["completed_concept_ids"] = sorted(request.completed_concept_ids)
    digest_payload = {
        "operation": operation.value,
        "policy_digest": policy_digest,
        "input": payload,
    }
    return f"request_{_hash(digest_payload)}"


def build_result_digest(
    operation: PlanningOperation,
    request_digest: str,
    path: PathDecision,
) -> str:
    digest_payload = {
        "operation": operation.value,
        "request_digest": request_digest,
        "path": path.model_dump(mode="json"),
    }
    return f"result_{_hash(digest_payload)}"


def create_course_plan_tool(
    catalog: OntologyCatalog,
    policy: PlannerPolicy | None = None,
) -> StructuredTool:
    planner = CoursePlanner(catalog, policy)

    def create_course_plan(
        profile: LearnerProfileSnapshot,
        completed_concept_ids: tuple[str, ...] = (),
        allow_skips: bool = True,
    ) -> dict[str, object]:
        request = CreateCoursePlanInput(
            profile=profile,
            completed_concept_ids=completed_concept_ids,
            allow_skips=allow_skips,
        )
        path = planner.plan(
            request.profile,
            set(request.completed_concept_ids),
            allow_skips=request.allow_skips,
        )
        return _build_result(
            PlanningOperation.CREATE,
            request,
            path,
            planner.policy_digest,
        ).model_dump(mode="json")

    return StructuredTool.from_function(
        func=create_course_plan,
        name=PlanningOperation.CREATE.value,
        description=(
            "Create a deterministic, prerequisite-safe course path from a validated "
            "learner profile."
        ),
        args_schema=CreateCoursePlanInput,
        infer_schema=False,
    )


def update_course_plan_tool(
    catalog: OntologyCatalog,
    policy: PlannerPolicy | None = None,
) -> StructuredTool:
    planner = CoursePlanner(catalog, policy)
    updater = DepthUpdater(catalog, policy)

    def update_course_plan(
        existing: PathDecision,
        profile: LearnerProfileSnapshot,
        completed_concept_ids: tuple[str, ...],
    ) -> dict[str, object]:
        request = UpdateCoursePlanInput(
            existing=existing,
            profile=profile,
            completed_concept_ids=completed_concept_ids,
        )
        path = updater.update(
            request.existing,
            request.profile,
            set(request.completed_concept_ids),
        )
        return _build_result(
            PlanningOperation.UPDATE,
            request,
            path,
            planner.policy_digest,
        ).model_dump(mode="json")

    return StructuredTool.from_function(
        func=update_course_plan,
        name=PlanningOperation.UPDATE.value,
        description=(
            "Update only unfinished course path nodes after validated concept "
            "completion evidence."
        ),
        args_schema=UpdateCoursePlanInput,
        infer_schema=False,
    )


def build_create_course_plan_node(
    catalog: OntologyCatalog,
    policy: PlannerPolicy | None = None,
) -> Callable[[CoursePlanningState], CoursePlanningState]:
    tool = create_course_plan_tool(catalog, policy)

    def create_course_plan_node(state: CoursePlanningState) -> CoursePlanningState:
        raw_profile = state.get("profile")
        if raw_profile is None:
            return _node_failure(
                PlanningOperation.CREATE,
                PlanningFailureCode.INVALID_STATE,
                "profile is required",
            )
        try:
            request = CreateCoursePlanInput(
                profile=LearnerProfileSnapshot.model_validate(raw_profile),
                completed_concept_ids=state.get("completed_concept_ids", ()),
                allow_skips=state.get("allow_skips", True),
            )
        except ValidationError as exc:
            return _node_failure(
                PlanningOperation.CREATE,
                PlanningFailureCode.INVALID_STATE,
                str(exc),
            )
        try:
            result = PlanningToolResult.model_validate(
                tool.invoke(request.model_dump(mode="python"))
            )
        except PlanningError as exc:
            return _node_failure(
                PlanningOperation.CREATE,
                PlanningFailureCode.PLANNING_ERROR,
                str(exc),
            )
        except (ValidationError, ValueError) as exc:
            return _node_failure(
                PlanningOperation.CREATE,
                PlanningFailureCode.PLANNING_ERROR,
                str(exc),
            )
        return {
            "path": result.path,
            "planning_status": PlanningNodeStatus.PLANNED,
            "planning_audit": result.audit,
            "planning_failure": None,
        }

    return create_course_plan_node


def build_update_course_plan_node(
    catalog: OntologyCatalog,
    policy: PlannerPolicy | None = None,
) -> Callable[[CoursePlanningState], CoursePlanningState]:
    tool = update_course_plan_tool(catalog, policy)

    def update_course_plan_node(state: CoursePlanningState) -> CoursePlanningState:
        raw_profile = state.get("profile")
        existing = state.get("path")
        if raw_profile is None or existing is None:
            missing = "profile" if raw_profile is None else "path"
            return _node_failure(
                PlanningOperation.UPDATE,
                PlanningFailureCode.INVALID_STATE,
                f"{missing} is required",
            )
        try:
            request = UpdateCoursePlanInput(
                existing=PathDecision.model_validate(existing),
                profile=LearnerProfileSnapshot.model_validate(raw_profile),
                completed_concept_ids=state.get("completed_concept_ids", ()),
            )
        except ValidationError as exc:
            return _node_failure(
                PlanningOperation.UPDATE,
                PlanningFailureCode.INVALID_STATE,
                str(exc),
            )
        try:
            result = PlanningToolResult.model_validate(
                tool.invoke(request.model_dump(mode="python"))
            )
        except PlanningError as exc:
            return _node_failure(
                PlanningOperation.UPDATE,
                PlanningFailureCode.PLANNING_ERROR,
                str(exc),
            )
        except (ValidationError, ValueError) as exc:
            return _node_failure(
                PlanningOperation.UPDATE,
                PlanningFailureCode.PLANNING_ERROR,
                str(exc),
            )
        return {
            "path": result.path,
            "planning_status": PlanningNodeStatus.UPDATED,
            "planning_audit": result.audit,
            "planning_failure": None,
        }

    return update_course_plan_node


def _build_result(
    operation: PlanningOperation,
    request: CreateCoursePlanInput | UpdateCoursePlanInput,
    path: PathDecision,
    policy_digest: str,
) -> PlanningToolResult:
    request_digest = build_request_digest(operation, request, policy_digest)
    result_digest = build_result_digest(operation, request_digest, path)
    return PlanningToolResult(
        path=path,
        audit=PlanningToolAudit(
            operation=operation,
            request_digest=request_digest,
            result_digest=result_digest,
            path_id=path.path_id,
            profile_id=path.profile_id,
            graph_version=path.graph_version,
            policy_digest=path.policy_digest,
        ),
    )


def _node_failure(
    operation: PlanningOperation,
    code: PlanningFailureCode,
    message: str,
) -> CoursePlanningState:
    return {
        "planning_status": PlanningNodeStatus.FAILED,
        "planning_audit": None,
        "planning_failure": PlanningNodeFailure(
            code=code,
            operation=operation,
            message=message,
        ),
    }


def _validate_unique_completed_ids(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(value) != len(set(value)):
        raise ValueError("completed concept IDs must be unique")
    return value


def _hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
