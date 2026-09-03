import json
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from skillforge_kb.agents.planning_agent_models import CoursePlanningAgentResult
from skillforge_kb.agents.resource_agent import ResourceAgentResult
from skillforge_kb.agents.retrieval_agent_models import (
    DomainRetrievalResult,
    EvidenceGap,
)
from skillforge_kb.assessment import AssessmentErrorKind
from skillforge_kb.ontology.models import CONCEPT_ID_PATTERN, LearnerProfileSnapshot
from skillforge_kb.resources.handoff import ResourceHandoffContract

ASSESSMENT_PASSING_SCORE = 0.60


class ExecutionMode(StrEnum):
    STRICT = "strict"
    CANDIDATE_PREVIEW = "candidate_preview"


class AssessmentModel(StrEnum):
    RULE = "rule"
    BKT = "bkt"


class PlatformRunStatus(StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    RETRIEVING = "retrieving"
    BLOCKED = "blocked"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class PlatformStage(StrEnum):
    VALIDATE_INPUT = "validate_input"
    PLAN_COURSE = "plan_course"
    BUILD_HANDOFF = "build_handoff"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    EVALUATE_GATE = "evaluate_generation_gate"
    GENERATE_RESOURCE = "generate_resource"
    VALIDATE_RESOURCE = "validate_resource"
    FINALIZE = "finalize"


class PlatformStepStatus(StrEnum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class PlatformRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: LearnerProfileSnapshot
    idempotency_key: str = Field(min_length=1, max_length=128)
    execution_mode: ExecutionMode = ExecutionMode.STRICT
    assessment_model: AssessmentModel = AssessmentModel.RULE
    top_k: int = Field(default=5, ge=1, le=20)
    target_concept_id: str | None = Field(default=None, pattern=CONCEPT_ID_PATTERN)
    start_concept_id: str | None = Field(default=None, pattern=CONCEPT_ID_PATTERN)


class AssessmentSubmission(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    assessment_id: str = Field(min_length=1, max_length=128)
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    score: float | None = Field(default=None, ge=0, le=1)
    responses: dict[str, int] = Field(default_factory=dict)
    response_time_ms: int = Field(strict=True, ge=0)
    hint_count: int = Field(strict=True, ge=0)
    attempt_count: int = Field(strict=True, ge=1)
    error_kind: AssessmentErrorKind | None = None
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def reject_client_passing_score(cls, value: object) -> object:
        if isinstance(value, dict) and "passing_score" in value:
            raise ValueError("passing score is controlled by the server")
        return value

    @model_validator(mode="after")
    def validate_error_kind(self) -> "AssessmentSubmission":
        if self.score is None and not self.responses:
            raise ValueError("assessment requires a score or selected responses")
        if (
            self.score is not None
            and not self.responses
            and self.score >= ASSESSMENT_PASSING_SCORE
            and self.error_kind is not None
        ):
            raise ValueError("passing assessment cannot include an error kind")
        return self


class PracticeReviewSubmission(BaseModel):
    """A student source submission for the current node's practice exercise."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    source: str = Field(min_length=1, max_length=12_000)
    exercise_kind: str = Field(default="basic", pattern="^(basic|project)$")


class LectureProgressSubmission(BaseModel):
    """Learner-reported progress through the current generated lecture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    progress: float = Field(ge=0, le=1)


class LearningCoachQuestion(BaseModel):
    """A learner question scoped to the current learning node."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    question: str = Field(min_length=1, max_length=2_000)


class LearningCoachReply(BaseModel):
    """A short Socratic response safe to display in the learning UI."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str = Field(min_length=1, max_length=4_000)


class LearningProgress(BaseModel):
    """Auditable completion gates for one concept in one platform run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    lecture_progress: float = Field(default=0.0, ge=0, le=1)
    lecture_completed: bool = False
    practice_completed: bool = False
    assessment_passed: bool = False
    assessment_attempts: int = Field(default=0, ge=0)
    failed_attempts: int = Field(default=0, ge=0)
    remediation_required: bool = False

    @model_validator(mode="before")
    @classmethod
    def discard_derived_fields(cls, value: object) -> object:
        if isinstance(value, dict) and "can_complete" in value:
            value = dict(value)
            value.pop("can_complete", None)
        return value

    @model_validator(mode="after")
    def validate_assessment_state(self) -> "LearningProgress":
        if self.lecture_completed and self.lecture_progress < 0.80:
            object.__setattr__(self, "lecture_progress", 0.80)
        if self.lecture_progress >= 0.80 and not self.lecture_completed:
            object.__setattr__(self, "lecture_completed", True)
        if self.assessment_passed and self.assessment_attempts < 1:
            raise ValueError("assessment_passed requires at least one assessment attempt")
        if self.failed_attempts > self.assessment_attempts:
            raise ValueError("failed assessment attempts cannot exceed total attempts")
        if self.assessment_passed and self.failed_attempts >= self.assessment_attempts:
            raise ValueError("assessment_passed requires a passing assessment attempt")
        return self

    @computed_field
    @property
    def can_complete(self) -> bool:
        return (
            self.lecture_completed
            and self.practice_completed
            and self.assessment_passed
            and not self.remediation_required
        )

    @property
    def max_next_lecture_progress(self) -> float:
        return min(1.0, self.lecture_progress + 0.25)


class PlatformFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    stage: PlatformStage
    retryable: bool = False
    details: dict[str, str] = Field(default_factory=dict)


class PlatformStepRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: PlatformStage
    status: PlatformStepStatus
    started_at: datetime
    finished_at: datetime
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    failure: PlatformFailure | None = None

    @model_validator(mode="after")
    def validate_timing_and_failure(self) -> "PlatformStepRecord":
        if self.finished_at < self.started_at:
            raise ValueError("platform step cannot finish before it starts")
        if self.status is PlatformStepStatus.FAILED and self.failure is None:
            raise ValueError("failed platform step requires failure details")
        if self.status is not PlatformStepStatus.FAILED and self.failure is not None:
            raise ValueError("successful platform step cannot contain failure details")
        return self


class PlatformRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(pattern=r"^run_[0-9a-f]{64}$")
    request_digest: str = Field(pattern=r"^request_[0-9a-f]{64}$")
    profile_id: str = Field(min_length=1)
    profile: LearnerProfileSnapshot | None = None
    status: PlatformRunStatus
    planning: CoursePlanningAgentResult | None = None
    retrieval: DomainRetrievalResult | None = None
    handoff: ResourceHandoffContract | None = None
    resources: ResourceAgentResult | None = None
    evidence_gap: EvidenceGap | None = None
    failure: PlatformFailure | None = None
    steps: tuple[PlatformStepRecord, ...] = ()
    learning_progress: LearningProgress | None = None
    # Human-readable, auditable explanation of what changed after feedback.
    adaptation_trace: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_terminal_status(self) -> "PlatformRunResult":
        if self.status is PlatformRunStatus.COMPLETED:
            if self.resources is None:
                raise ValueError("completed run requires resources")
            if self.planning is None or self.retrieval is None or self.handoff is None:
                raise ValueError("completed run requires all upstream Agent results")
            if self.failure is not None:
                raise ValueError("completed run cannot contain failure details")
        elif self.status is PlatformRunStatus.BLOCKED:
            if self.evidence_gap is None:
                raise ValueError("blocked run requires an evidence gap")
            if self.resources is not None:
                raise ValueError("blocked run cannot contain generated resources")
            if self.failure is not None:
                raise ValueError("blocked run cannot contain failure details")
        elif self.status is PlatformRunStatus.FAILED:
            if self.failure is None:
                raise ValueError("failed run requires failure details")
            if self.resources is not None:
                raise ValueError("failed run cannot contain generated resources")
        elif self.failure is not None:
            raise ValueError("non-failed run cannot contain failure details")
        self._validate_identity()
        return self

    def _validate_identity(self) -> None:
        if self.profile is not None and self.profile.profile_id != self.profile_id:
            raise ValueError("run profile does not match profile_id")
        if (
            self.planning is not None
            and self.planning.path is not None
            and self.planning.path.profile_id != self.profile_id
        ):
            raise ValueError("planning result profile does not match platform run")
        if self.handoff is not None and self.handoff.profile_id != self.profile_id:
            raise ValueError("handoff profile does not match platform run")
        if (
            self.retrieval is not None
            and self.retrieval.request.profile_id != self.profile_id
        ):
            raise ValueError("retrieval profile does not match platform run")
        if self.resources is not None and self.resources.profile_id != self.profile_id:
            raise ValueError("resource profile does not match platform run")
        if (
            self.learning_progress is not None
            and self.handoff is not None
            and self.learning_progress.concept_id != self.handoff.concept_id
        ):
            raise ValueError("learning progress concept does not match platform handoff")
        if self.handoff is None:
            return
        identity = (
            self.handoff.path_id,
            self.handoff.graph_version,
            self.handoff.concept_id,
            self.handoff.delivery_depth,
        )
        if self.retrieval is not None and (
            self.retrieval.request.concept_id,
            self.retrieval.request.depth,
        ) != (identity[2], identity[3]):
            raise ValueError("retrieval scope does not match platform handoff")
        if self.resources is not None and (
            self.resources.path_id,
            self.resources.graph_version,
            self.resources.concept_id,
            self.resources.depth,
        ) != identity:
            raise ValueError("resource identity does not match platform handoff")


def build_request_digest(request: PlatformRunRequest) -> str:
    validated = PlatformRunRequest.model_validate(request.model_dump())
    return _digest("request", validated.model_dump(mode="json"))


def build_run_id(request: PlatformRunRequest) -> str:
    validated = PlatformRunRequest.model_validate(request.model_dump())
    return _digest(
        "run",
        {
            "profile_id": validated.profile.profile_id,
            "idempotency_key": validated.idempotency_key,
        },
    )


def build_payload_digest(payload: object) -> str:
    return _digest("", payload).removeprefix("_")


def _digest(prefix: str, payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    value = sha256(canonical.encode("utf-8")).hexdigest()
    return f"{prefix}_{value}" if prefix else value
