import json
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.planning.models import PathDecision


class PlanningOperation(StrEnum):
    CREATE = "create_course_plan"
    UPDATE = "update_course_plan"


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
    completed_concept_ids: tuple[str, ...] = Field(min_length=1)

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
