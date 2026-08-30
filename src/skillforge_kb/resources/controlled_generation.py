# ruff: noqa: E501
"""Controlled, evidence-grounded resource generation.

This module deliberately keeps content writing separate from curriculum, evidence,
execution and release decisions.  It can be exercised with ``FakeLLMAdapter`` in
tests and switched to any OpenAI-compatible endpoint through configuration.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal, Protocol, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


def _digest(prefix: str, payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{sha256(canonical.encode('utf-8')).hexdigest()}"


class EvidenceApprovalStatus(StrEnum):
    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    APPROVED = "approved"


class GenerationStatus(StrEnum):
    NOT_STARTED = "not_started"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class PublicationStatus(StrEnum):
    CANDIDATE_DRAFT = "candidate_draft"
    RELEASE_CANDIDATE = "release_candidate"
    # ``published`` is intentionally not derivable in this phase.


class ClaimSupportStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNCERTAIN = "uncertain"


class QuizKind(StrEnum):
    CONCEPT = "concept"
    SHAPE_REASONING = "shape_reasoning"
    CODE = "code"
    DEBUGGING = "debugging"
    SYNTHESIS = "synthesis"


class AllowedEvidence(BaseModel):
    """A selected evidence span, not an invitation for the model to retrieve more."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    span_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    approval_status: EvidenceApprovalStatus


class PersonalizationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scaffolding_level: int = Field(ge=1, le=3)
    explanation_order_hint: tuple[str, ...] = Field(min_length=1)
    exercise_difficulty_distribution: tuple[int, int, int] = Field(min_length=3, max_length=3)
    review_intensity: int = Field(ge=1, le=3)
    debugging_emphasis: int = Field(ge=1, le=3)
    presentation_preferences: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_distribution(self) -> PersonalizationPolicy:
        if sum(self.exercise_difficulty_distribution) != 8:
            raise ValueError("exercise difficulty distribution must total eight questions")
        return self


class GenerationPolicyPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str = "generation-policy.v1"
    concept_id: str = Field(min_length=1)
    knowledge_scope: tuple[str, ...] = Field(min_length=1)
    forbidden_scope: tuple[str, ...] = ()
    learning_objectives: tuple[str, ...] = Field(min_length=1)
    delivery_depth: str = Field(min_length=1)
    prerequisite_gate_passed: bool
    unresolved_prerequisites: tuple[str, ...] = ()
    allowed_evidence: tuple[AllowedEvidence, ...] = Field(min_length=1)
    quiz_structure: tuple[tuple[QuizKind, int], ...] = (
        (QuizKind.CONCEPT, 2),
        (QuizKind.SHAPE_REASONING, 2),
        (QuizKind.CODE, 2),
        (QuizKind.DEBUGGING, 1),
        (QuizKind.SYNTHESIS, 1),
    )
    notebook_core_system_owned: bool = True
    notebook_execution_required: bool = True
    personalization: PersonalizationPolicy

    @model_validator(mode="after")
    def validate_policy(self) -> GenerationPolicyPayload:
        if self.prerequisite_gate_passed and self.unresolved_prerequisites:
            raise ValueError("a passed prerequisite gate cannot have unresolved prerequisites")
        if sum(count for _, count in self.quiz_structure) != 8:
            raise ValueError("quiz structure must contain eight questions")
        if Counter(kind for kind, _ in self.quiz_structure) != Counter(QuizKind):
            raise ValueError("quiz structure must contain every required question kind")
        return self


class GenerationPolicy(GenerationPolicyPayload):
    """Immutable curriculum/evidence/personality execution boundary."""

    policy_id: str = Field(pattern=r"^policy_[0-9a-f]{64}$")
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> GenerationPolicy:
        payload = self.model_dump(mode="json", exclude={"policy_id", "policy_hash"})
        expected_id = _digest("policy", payload)
        expected_hash = expected_id.removeprefix("policy_")
        if self.policy_id != expected_id or self.policy_hash != expected_hash:
            raise ValueError("policy identity does not match immutable content")
        return self

    @classmethod
    def create(cls, **payload: Any) -> GenerationPolicy:
        validated = GenerationPolicyPayload.model_validate(payload)
        value = validated.model_dump(mode="json")
        policy_id = _digest("policy", value)
        return cls(**value, policy_id=policy_id, policy_hash=policy_id.removeprefix("policy_"))


class ResourceGenerationBrief(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    brief_id: str = Field(pattern=r"^generation_brief_[0-9a-f]{64}$")
    profile_id: str = Field(min_length=1)
    policy: GenerationPolicy
    learner_context: dict[str, str | int | float | tuple[str, ...]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_identity(self) -> ResourceGenerationBrief:
        payload = self.model_dump(mode="json", exclude={"brief_id"})
        if self.brief_id != _digest("generation_brief", payload):
            raise ValueError("generation brief identity does not match content")
        return self

    @classmethod
    def create(
        cls, *, profile_id: str, policy: GenerationPolicy, learner_context: dict[str, Any]
    ) -> ResourceGenerationBrief:
        typed_context: dict[str, str | int | float | tuple[str, ...]] = {
            key: value
            for key, value in learner_context.items()
            if isinstance(value, (str, int, float, tuple))
        }
        payload = {
            "profile_id": profile_id,
            "policy": policy.model_dump(mode="json"),
            "learner_context": typed_context,
        }
        return cls(
            profile_id=profile_id,
            policy=policy,
            learner_context=typed_context,
            brief_id=_digest("generation_brief", payload),
        )


class TechnicalClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class LessonBlock(BaseModel):
    """A readable unit in a student-facing lesson rather than a list heading."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal[
        "objective", "intuition", "definition", "derivation", "example", "pitfall", "summary"
    ]
    title: str = Field(min_length=1)
    body: str = Field(min_length=40)
    code: str | None = None


class PracticeExercise(BaseModel):
    """Student-facing code exercise. Reference solutions remain outside this model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    language: Literal["python"] = "python"
    task: str = Field(min_length=40)
    starter_code: str = Field(min_length=1, max_length=12_000)
    expected_output: str = Field(min_length=1)
    checks: tuple[str, ...] = Field(min_length=1)
    required_tokens: tuple[str, ...] = Field(min_length=1)


class LectureDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1)
    sections: tuple[str, ...] = Field(min_length=1)
    claims: tuple[TechnicalClaim, ...] = Field(min_length=1)
    review_section_count: int = Field(default=0, ge=0)
    explanation_order: tuple[str, ...] = ()
    blocks: tuple[LessonBlock, ...] = ()


class PracticalGuideDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str = Field(min_length=1)
    learning_steps: tuple[str, ...] = Field(min_length=1)
    claims: tuple[TechnicalClaim, ...] = Field(min_length=1)
    notebook_tasks: tuple[str, ...] = Field(min_length=1)
    starter_code_lines: int = Field(default=0, ge=0)
    required_core_code_lines: int = Field(default=1, ge=1)
    debug_hint_depth: int = Field(default=0, ge=0, le=3)
    experiment_protocol: tuple[str, ...] = ()
    exercise: PracticeExercise | None = None
    project_exercise: PracticeExercise | None = None


class StudentQuizItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str = Field(min_length=1)
    kind: QuizKind
    difficulty: int = Field(ge=1, le=3)
    prompt: str = Field(min_length=1)
    hints: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()
    correct_choice: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_choice(self) -> StudentQuizItem:
        if self.correct_choice is not None and self.choices and self.correct_choice >= len(self.choices):
            raise ValueError("correct_choice must reference a quiz choice")
        return self


class StudentQuizDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    instructions: str = Field(min_length=1)
    items: tuple[StudentQuizItem, ...] = Field(min_length=1)


class TeacherAnswerItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    scoring_points: tuple[str, ...] = Field(min_length=1)
    error_diagnosis: str = Field(min_length=1)
    teaching_action: str = Field(min_length=1)


class TeacherGuideDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: tuple[TeacherAnswerItem, ...] = Field(min_length=1)
    review_task_count: int = Field(default=0, ge=0)
    feedback_strategy: tuple[str, ...] = ()


class StructuredResourceDraft(BaseModel):
    """The model can write these fields, but cannot carry a release state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lecture: LectureDraft
    practical_guide: PracticalGuideDraft
    student_quiz: StudentQuizDraft
    teacher_guide: TeacherGuideDraft


class AuditFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    hard: bool


class ClaimEvidenceLedgerItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    claim: str
    evidence_ids: tuple[str, ...]
    evidence_span_ids: tuple[str, ...]
    support: ClaimSupportStatus


class ResourceAuditReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    audit_status: AuditStatus
    findings: tuple[AuditFinding, ...]
    claim_evidence_ledger: tuple[ClaimEvidenceLedgerItem, ...]
    notebook_passed: bool


class GenerationTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str
    brief_id: str
    prompt_version: str
    model_name: str
    generator_model: str | None = None
    generator_prompt_hash: str | None = None
    material_prompt_hashes: dict[str, str] = Field(default_factory=dict)
    verifier_model: str | None = None
    verifier_prompt_version: str | None = None
    verifier_prompt_hash: str | None = None
    policy_hash: str | None = None
    evidence_bundle_hash: str | None = None
    quiz_blueprint_hash: str | None = None
    learner_profile_hash: str | None = None
    structured_output_mode: str = "json_object"
    attempt_count: int = Field(ge=1)
    generated_at: datetime


class CandidateLearningPackage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    generation_status: GenerationStatus
    audit_status: AuditStatus
    publication_status: PublicationStatus
    draft: StructuredResourceDraft | None
    audit_report: ResourceAuditReport | None
    trace: GenerationTrace


class ClaimSupportVerifier(Protocol):
    """Judge-only verifier: no retrieval, editing or new factual knowledge."""

    def verify(self, *, claim: str, evidence_span: str) -> ClaimSupportStatus: ...


class ConservativeSpanVerifier:
    """A deliberately conservative local verifier for offline tests and demos."""

    def verify(self, *, claim: str, evidence_span: str) -> ClaimSupportStatus:
        if claim.casefold() in evidence_span.casefold():
            return ClaimSupportStatus.SUPPORTED
        claim_tokens = set(re.findall(r"[A-Za-z0-9_]+", claim.casefold()))
        span_tokens = set(re.findall(r"[A-Za-z0-9_]+", evidence_span.casefold()))
        if claim_tokens and not claim_tokens.intersection(span_tokens):
            return ClaimSupportStatus.UNSUPPORTED
        return ClaimSupportStatus.UNCERTAIN


class LLMClaimSupportVerifier:
    """Model-based, read-only evidence entailment check; never retrieves or edits evidence."""

    prompt_version = "claim-entailment.v1"
    prompt_template = (
        "Judge only whether the evidence span supports the claim. Return JSON with one field "
        "status whose value is supported, unsupported, or uncertain. Do not use outside knowledge."
    )

    def __init__(self, adapter: LLMAdapter) -> None:
        self._adapter = adapter
        self.model_name = adapter.model_name

    def verify(self, *, claim: str, evidence_span: str) -> ClaimSupportStatus:
        prompt = f"{self.prompt_template}\nClaim: {claim}\nEvidence span: {evidence_span}"
        try:
            result = json.loads(self._adapter.complete(prompt))
            return ClaimSupportStatus(result["status"])
        except (KeyError, ValueError, TypeError, httpx.HTTPError, json.JSONDecodeError):
            return ClaimSupportStatus.UNCERTAIN


class LLMAdapter(Protocol):
    model_name: str

    def complete(self, prompt: str, *, repair: str | None = None) -> str: ...


class FakeLLMAdapter:
    """Test adapter that returns an explicit structured draft."""

    model_name = "fake-resource-writer"

    def __init__(self, draft: StructuredResourceDraft | dict[str, Any]) -> None:
        self._draft = draft

    def complete(self, prompt: str, *, repair: str | None = None) -> str:
        payload = (
            self._draft.model_dump(mode="json")
            if isinstance(self._draft, StructuredResourceDraft)
            else self._draft
        )
        material_match = re.search(r"MATERIAL: ([a-z_]+)", prompt)
        if material_match and isinstance(payload, dict):
            material = material_match.group(1)
            if material in payload:
                payload = payload[material]
        return json.dumps(payload, ensure_ascii=False)


class OpenAICompatibleLLMAdapter:
    """Small synchronous adapter for OpenAI-compatible chat completion APIs."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model_name: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model_name = model_name
        self._timeout_seconds = timeout_seconds
        self.structured_output_mode = "json_object"

    def complete(self, prompt: str, *, repair: str | None = None) -> str:
        message = prompt if repair is None else f"{prompt}\n\nRepair requirements:\n{repair}"
        response = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
            json={
                "model": self.model_name,
                "messages": [{"role": "user", "content": message}],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"])


class ModelCapabilityReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoint_reachable: bool
    authentication: bool
    model_available: bool
    basic_completion: bool
    json_object_response: bool
    json_schema_supported: bool
    structured_output_mode: str
    elapsed_ms: int | None
    api_key_logging_safe: bool = True
    message: str


def check_model_capabilities(adapter: OpenAICompatibleLLMAdapter) -> ModelCapabilityReport:
    started = datetime.now(UTC)
    try:
        raw = adapter.complete('Return only JSON: {"ok": true}.')
        valid_json = json.loads(raw).get("ok") is True
        elapsed = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return ModelCapabilityReport(
            endpoint_reachable=True,
            authentication=True,
            model_available=True,
            basic_completion=True,
            json_object_response=valid_json,
            json_schema_supported=False,
            structured_output_mode="json_object" if valid_json else "prompt_json",
            elapsed_ms=elapsed,
            message="model returned a JSON object; final output remains Pydantic-validated",
        )
    except httpx.HTTPStatusError as exc:
        return ModelCapabilityReport(endpoint_reachable=True, authentication=False, model_available=False, basic_completion=False, json_object_response=False, json_schema_supported=False, structured_output_mode="prompt_json", elapsed_ms=None, message=f"HTTP {exc.response.status_code}")
    except httpx.HTTPError as exc:
        return ModelCapabilityReport(endpoint_reachable=False, authentication=False, model_available=False, basic_completion=False, json_object_response=False, json_schema_supported=False, structured_output_mode="prompt_json", elapsed_ms=None, message=type(exc).__name__)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        return ModelCapabilityReport(endpoint_reachable=True, authentication=True, model_available=True, basic_completion=True, json_object_response=False, json_schema_supported=False, structured_output_mode="prompt_json", elapsed_ms=None, message=type(exc).__name__)


MATERIAL_SCHEMAS: dict[str, type[BaseModel]] = {
    "lecture": LectureDraft,
    "practical_guide": PracticalGuideDraft,
    "student_quiz": StudentQuizDraft,
    "teacher_guide": TeacherGuideDraft,
}


def build_generation_prompt(
    brief: ResourceGenerationBrief,
    *,
    material: str = "package",
    student_quiz: StudentQuizDraft | None = None,
) -> str:
    """Serialize only inputs the writer is allowed to use for one material."""

    if material not in {*MATERIAL_SCHEMAS, "package"}:
        raise ValueError(f"unknown material: {material}")
    teacher_constraint = ""
    if material == "teacher_guide":
        if student_quiz is None:
            raise ValueError("teacher guide requires a frozen student quiz")
        teacher_constraint = (
            " The following student quiz is immutable: preserve every question_id and do not "
            "add, remove, or rewrite student questions. Return teacher-only answers keyed by it.\n"
            + json.dumps(student_quiz.model_dump(mode="json"), ensure_ascii=False)
        )
    schema = "four material schemas" if material == "package" else f"the {material} schema"
    schema_model = (
        StructuredResourceDraft if material == "package" else MATERIAL_SCHEMAS[material]
    )
    schema_json = json.dumps(
        schema_model.model_json_schema(), ensure_ascii=False, separators=(",", ":")
    )
    return (
        f"MATERIAL: {material}\n"
        f"You are a teaching-content writer. Return exactly one JSON object matching {schema}. "
        "Do not wrap it in Markdown or add commentary. Do not include keys outside the schema. "
        "Do not create release status, new evidence, new scope IDs, executable notebook core "
        "code, or a different quiz blueprint. Every technical claim must use an allowed evidence "
        "ID and a knowledge scope ID.\nJSON SCHEMA:\n"
        f"{schema_json}"
        + (
            "\nPEDAGOGICAL REQUIREMENTS: For lecture, write at least seven ordered blocks with kinds "
            "objective, intuition, definition, derivation, example, pitfall, summary. "
            "Each body must explain the concept in complete sentences, include a concrete example, "
            "and connect the explanation to the learner objective."
            if material == "lecture"
            else "\nPEDAGOGICAL REQUIREMENTS: For practical_guide, provide two distinct Python exercises: "
            "exercise is a short teaching example with TODOs, while project_exercise is a more complex "
            "project-style task with data flow, reusable functions, and measurable acceptance criteria. "
            "Each exercise must provide starter_code, expected_output, checks, and required_tokens. "
            "Also provide an experiment_protocol with at least four ordered steps covering a baseline, "
            "one-variable change, boundary case, and evidence-based conclusion. The student must be able "
            "to edit either code sample and submit it for static feedback; never place a reference solution "
            "in starter_code."
            if material == "practical_guide"
            else "\nPEDAGOGICAL REQUIREMENTS: For student_quiz, write eight answerable questions with at least "
            "two choices each. Keep correct_choice as a server-only answer key and do not put answers in prompt or hints."
            if material == "student_quiz"
            else ""
        )
        + teacher_constraint
        + "\nIMMUTABLE BRIEF:\n"
        + json.dumps(brief.model_dump(mode="json"), ensure_ascii=False)
    )


def build_trace(
    *,
    brief: ResourceGenerationBrief,
    adapter: LLMAdapter,
    attempt: int,
    verifier: ClaimSupportVerifier | None = None,
    material_prompts: dict[str, str] | None = None,
) -> GenerationTrace:
    material_prompts = material_prompts or {"package": build_generation_prompt(brief)}
    generator_prompt = "\n".join(material_prompts.values())
    evidence_hash = _digest("evidence", [item.model_dump(mode="json") for item in brief.policy.allowed_evidence])
    blueprint_hash = _digest("quiz", brief.policy.quiz_structure)
    profile_hash = _digest("profile", brief.learner_context)
    verifier_prompt = getattr(verifier, "prompt_template", None)
    return GenerationTrace(
        policy_id=brief.policy.policy_id,
        brief_id=brief.brief_id,
        prompt_version="controlled-generation.v3-dual-exercise",
        model_name=adapter.model_name,
        generator_model=adapter.model_name,
        generator_prompt_hash=_digest("prompt", generator_prompt),
        material_prompt_hashes={key: _digest("prompt", value) for key, value in material_prompts.items()},
        verifier_model=getattr(verifier, "model_name", None),
        verifier_prompt_version=getattr(verifier, "prompt_version", None),
        verifier_prompt_hash=_digest("prompt", verifier_prompt) if verifier_prompt else None,
        policy_hash=brief.policy.policy_hash, evidence_bundle_hash=evidence_hash,
        quiz_blueprint_hash=blueprint_hash, learner_profile_hash=profile_hash,
        structured_output_mode=getattr(adapter, "structured_output_mode", "json_object"),
        attempt_count=attempt, generated_at=datetime.now(UTC),
    )


def derive_publication_status(
    *, policy: GenerationPolicy, audit_status: AuditStatus, referenced_evidence_ids: set[str]
) -> PublicationStatus:
    """Release state is derived; phase two never returns ``published``."""

    by_id = {item.evidence_id: item for item in policy.allowed_evidence}
    all_referenced_approved = bool(referenced_evidence_ids) and all(
        by_id[evidence_id].approval_status is EvidenceApprovalStatus.APPROVED
        for evidence_id in referenced_evidence_ids
        if evidence_id in by_id
    )
    if (
        not policy.prerequisite_gate_passed
        or audit_status is not AuditStatus.PASSED
        or not all_referenced_approved
    ):
        return PublicationStatus.CANDIDATE_DRAFT
    return PublicationStatus.RELEASE_CANDIDATE


class ResourceAuditor:
    def __init__(self, verifier: ClaimSupportVerifier | None = None) -> None:
        self._verifier = verifier or ConservativeSpanVerifier()

    @property
    def verifier(self) -> ClaimSupportVerifier:
        """Expose verifier metadata for tracing without granting mutation access."""
        return self._verifier

    def audit(
        self, draft: StructuredResourceDraft, policy: GenerationPolicy, *, notebook_passed: bool
    ) -> ResourceAuditReport:
        findings: list[AuditFinding] = []
        ledger: list[ClaimEvidenceLedgerItem] = []
        allowed = {item.evidence_id: item for item in policy.allowed_evidence}
        claims = (*draft.lecture.claims, *draft.practical_guide.claims)
        forbidden = tuple(item.casefold() for item in policy.forbidden_scope)
        student_text = "\n".join(
            (
                draft.student_quiz.instructions,
                *(item.prompt for item in draft.student_quiz.items),
                *(hint for item in draft.student_quiz.items for hint in item.hints),
            )
        ).casefold()
        all_text = "\n".join(
            (
                draft.lecture.title,
                *draft.lecture.sections,
                *(block.title for block in draft.lecture.blocks),
                *(block.body for block in draft.lecture.blocks),
                *(block.code or "" for block in draft.lecture.blocks),
                *draft.lecture.explanation_order,
                draft.practical_guide.title,
                *draft.practical_guide.learning_steps,
                *draft.practical_guide.notebook_tasks,
                *draft.practical_guide.experiment_protocol,
                draft.practical_guide.exercise.task if draft.practical_guide.exercise else "",
                draft.practical_guide.exercise.starter_code if draft.practical_guide.exercise else "",
                draft.practical_guide.project_exercise.task if draft.practical_guide.project_exercise else "",
                draft.practical_guide.project_exercise.starter_code if draft.practical_guide.project_exercise else "",
                student_text,
                *(item.answer for item in draft.teacher_guide.items),
                *(item.error_diagnosis for item in draft.teacher_guide.items),
                *(item.teaching_action for item in draft.teacher_guide.items),
                *draft.teacher_guide.feedback_strategy,
            )
        ).casefold()

        for topic in forbidden:
            if topic and topic in all_text:
                findings.append(
                    AuditFinding(
                        code="forbidden_scope", message=f"forbidden topic: {topic}", hard=True
                    )
                )
        for claim in claims:
            if claim.scope_id not in policy.knowledge_scope:
                findings.append(
                    AuditFinding(
                        code="scope_violation",
                        message=f"claim {claim.claim_id} is outside policy scope",
                        hard=True,
                    )
                )
            unknown = set(claim.evidence_ids) - set(allowed)
            if unknown:
                findings.append(
                    AuditFinding(
                        code="unknown_evidence",
                        message=f"claim {claim.claim_id} cites unknown evidence",
                        hard=True,
                    )
                )
                ledger.append(
                    ClaimEvidenceLedgerItem(
                        claim_id=claim.claim_id,
                        claim=claim.text,
                        evidence_ids=claim.evidence_ids,
                        evidence_span_ids=(),
                        support=ClaimSupportStatus.UNSUPPORTED,
                    )
                )
                continue
            outcomes = [
                self._verifier.verify(claim=claim.text, evidence_span=allowed[evidence_id].text)
                for evidence_id in claim.evidence_ids
            ]
            support = (
                ClaimSupportStatus.SUPPORTED
                if ClaimSupportStatus.SUPPORTED in outcomes
                else (
                    ClaimSupportStatus.UNCERTAIN
                    if ClaimSupportStatus.UNCERTAIN in outcomes
                    else ClaimSupportStatus.UNSUPPORTED
                )
            )
            ledger.append(
                ClaimEvidenceLedgerItem(
                    claim_id=claim.claim_id,
                    claim=claim.text,
                    evidence_ids=claim.evidence_ids,
                    evidence_span_ids=tuple(allowed[item].span_id for item in claim.evidence_ids),
                    support=support,
                )
            )
            if support is ClaimSupportStatus.UNSUPPORTED:
                findings.append(
                    AuditFinding(
                        code="unsupported_claim",
                        message=f"claim {claim.claim_id} is not supported by selected evidence",
                        hard=True,
                    )
                )

        expected = Counter(dict(policy.quiz_structure))
        actual = Counter(item.kind for item in draft.student_quiz.items)
        if actual != expected:
            findings.append(
                AuditFinding(
                    code="quiz_structure",
                    message="student quiz does not match fixed eight-question policy",
                    hard=True,
                )
            )
        student_ids = [item.question_id for item in draft.student_quiz.items]
        teacher_ids = [item.question_id for item in draft.teacher_guide.items]
        if (
            len(student_ids) != len(set(student_ids))
            or set(student_ids) != set(teacher_ids)
            or len(teacher_ids) != len(set(teacher_ids))
        ):
            findings.append(
                AuditFinding(
                    code="quiz_answer_alignment",
                    message="student and teacher question IDs do not align",
                    hard=True,
                )
            )
        leakage_markers = ("答案：", "答案:", "正确答案", "answer:", "solution:")
        if any(marker in student_text for marker in leakage_markers):
            findings.append(
                AuditFinding(
                    code="answer_leakage",
                    message="student material contains an answer marker",
                    hard=True,
                )
            )
        if policy.notebook_execution_required and not notebook_passed:
            findings.append(
                AuditFinding(
                    code="notebook_failed",
                    message="system-owned notebook did not execute",
                    hard=True,
                )
            )

        if any(item.hard for item in findings):
            status = AuditStatus.FAILED
        elif any(item.support is ClaimSupportStatus.UNCERTAIN for item in ledger):
            status = AuditStatus.NEEDS_REVIEW
        else:
            status = AuditStatus.PASSED
        return ResourceAuditReport(
            audit_status=status,
            findings=tuple(findings),
            claim_evidence_ledger=tuple(ledger),
            notebook_passed=notebook_passed,
        )


class ControlledResourceGenerationService:
    """Four material calls with one repair pass for schema/structural failures."""

    def __init__(self, adapter: LLMAdapter, auditor: ResourceAuditor | None = None) -> None:
        self._adapter = adapter
        self._auditor = auditor or ResourceAuditor()

    def generate(
        self, brief: ResourceGenerationBrief, *, notebook_passed: bool
    ) -> CandidateLearningPackage:
        errors: list[str] = []
        for attempt in (1, 2):
            try:
                draft, prompts = self._generate_materials(
                    brief, repair="; ".join(errors) if errors else None
                )
                audit = self._auditor.audit(draft, brief.policy, notebook_passed=notebook_passed)
                evidence_ids = {
                    evidence_id
                    for item in audit.claim_evidence_ledger
                    for evidence_id in item.evidence_ids
                }
                if audit.audit_status is AuditStatus.FAILED and attempt == 1:
                    errors = [finding.message for finding in audit.findings]
                    continue
                return CandidateLearningPackage(
                    generation_status=GenerationStatus.COMPLETED,
                    audit_status=audit.audit_status,
                    publication_status=derive_publication_status(
                        policy=brief.policy,
                        audit_status=audit.audit_status,
                        referenced_evidence_ids=evidence_ids,
                    ),
                    draft=draft,
                    audit_report=audit,
                    trace=build_trace(
                        brief=brief,
                        adapter=self._adapter,
                        attempt=attempt,
                        verifier=self._auditor.verifier,
                        material_prompts=prompts,
                    ),
                )
            except (ValueError, KeyError, httpx.HTTPError, json.JSONDecodeError) as exc:
                errors.append(str(exc))
        return CandidateLearningPackage(
            generation_status=GenerationStatus.FAILED,
            audit_status=AuditStatus.NOT_RUN,
            publication_status=PublicationStatus.CANDIDATE_DRAFT,
            draft=None,
            audit_report=None,
            trace=build_trace(
                brief=brief,
                adapter=self._adapter,
                attempt=2,
                verifier=self._auditor.verifier,
            ),
        )

    def _generate_materials(
        self, brief: ResourceGenerationBrief, *, repair: str | None
    ) -> tuple[StructuredResourceDraft, dict[str, str]]:
        prompts: dict[str, str] = {}

        def generate_one(name: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
            prompt = build_generation_prompt(brief, material=name, **kwargs)
            prompts[name] = prompt
            raw = self._adapter.complete(prompt, repair=repair)
            return schema.model_validate_json(raw)

        lecture = cast(LectureDraft, generate_one("lecture", LectureDraft))
        practical = cast(PracticalGuideDraft, generate_one("practical_guide", PracticalGuideDraft))
        quiz = cast(StudentQuizDraft, generate_one("student_quiz", StudentQuizDraft))
        teacher = cast(
            TeacherGuideDraft,
            generate_one("teacher_guide", TeacherGuideDraft, student_quiz=quiz),
        )
        return StructuredResourceDraft(
            lecture=lecture,
            practical_guide=practical,
            student_quiz=quiz,
            teacher_guide=teacher,
        ), prompts
