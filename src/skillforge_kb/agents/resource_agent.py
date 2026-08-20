from enum import StrEnum
from itertools import chain, repeat
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skillforge_kb.domain.enums import ContentKind
from skillforge_kb.ontology.models import (
    CONCEPT_ID_PATTERN,
    DepthLevel,
    LearnerProfileSnapshot,
)
from skillforge_kb.resources.controlled_generation import (
    AllowedEvidence,
    CandidateLearningPackage,
    ControlledResourceGenerationService,
    EvidenceApprovalStatus,
    FakeLLMAdapter,
    GenerationPolicy,
    LectureDraft,
    PersonalizationPolicy,
    PracticalGuideDraft,
    PublicationStatus,
    ResourceGenerationBrief,
    StructuredResourceDraft,
    StudentQuizDraft,
    StudentQuizItem,
    TeacherAnswerItem,
    TeacherGuideDraft,
    TechnicalClaim,
)
from skillforge_kb.resources.evidence_bundle import EvidenceBundle
from skillforge_kb.resources.generator_contracts import ValidatedResourcePackage
from skillforge_kb.resources.handoff import ResourceHandoffContract
from skillforge_kb.resources.models import ResourceBrief

from .resource_tools import FakeResourceGenerator, ResourceGenerationTool
from .retrieval_agent_models import DomainRetrievalResult, RetrievedEvidence


class ResourceGenerationMode(StrEnum):
    STRICT = "strict"
    CANDIDATE_PREVIEW = "candidate_preview"


class ResourceAgentResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: ResourceGenerationMode
    profile_id: str = Field(min_length=1)
    path_id: str = Field(pattern=r"^path_[0-9a-f]{64}$")
    graph_version: str = Field(min_length=1)
    concept_id: str = Field(pattern=CONCEPT_ID_PATTERN)
    depth: DepthLevel
    publication_status: Literal["formal", "candidate_draft"]
    formal_package: ValidatedResourcePackage | None = None
    preview_package: CandidateLearningPackage | None = None

    @model_validator(mode="after")
    def validate_mode_and_identity(self) -> "ResourceAgentResult":
        if self.mode is ResourceGenerationMode.STRICT:
            if self.formal_package is None or self.preview_package is not None:
                raise ValueError("strict generation requires one formal package")
            if self.publication_status != "formal":
                raise ValueError("strict generation must have formal publication status")
            for artifact in self.formal_package.artifacts:
                if (
                    artifact.path_id != self.path_id
                    or artifact.graph_version != self.graph_version
                    or artifact.concept_id != self.concept_id
                    or artifact.delivery_depth is not self.depth
                ):
                    raise ValueError("formal resource package identity does not match result")
        else:
            if self.preview_package is None or self.formal_package is not None:
                raise ValueError("candidate preview requires one preview package")
            if self.publication_status != "candidate_draft":
                raise ValueError("candidate preview cannot be publishable")
            if self.preview_package.publication_status is not PublicationStatus.CANDIDATE_DRAFT:
                raise ValueError("candidate preview package cannot be promoted")
        return self


class ResourceGenerationAgent:
    def generate_strict(
        self,
        handoff: ResourceHandoffContract,
        bundle: EvidenceBundle,
    ) -> ResourceAgentResult:
        brief = ResourceBrief.model_validate(handoff.model_dump())
        package = ResourceGenerationTool().invoke(
            brief,
            bundle,
            FakeResourceGenerator(),
        )
        return ResourceAgentResult(
            mode=ResourceGenerationMode.STRICT,
            profile_id=handoff.profile_id,
            path_id=handoff.path_id,
            graph_version=handoff.graph_version,
            concept_id=handoff.concept_id,
            depth=handoff.delivery_depth,
            publication_status="formal",
            formal_package=package,
        )

    def generate_preview(
        self,
        profile: LearnerProfileSnapshot,
        handoff: ResourceHandoffContract,
        retrieval: DomainRetrievalResult,
    ) -> ResourceAgentResult:
        self._validate_preview_scope(profile, handoff, retrieval)
        selected = _select_candidate_evidence(handoff, retrieval)
        policy = _preview_policy(profile, handoff, selected)
        brief = ResourceGenerationBrief.create(
            profile_id=profile.profile_id,
            policy=policy,
            learner_context=_learner_context(profile, handoff.concept_id),
        )
        draft = _preview_draft(handoff, policy, selected)
        package = ControlledResourceGenerationService(FakeLLMAdapter(draft)).generate(
            brief,
            notebook_passed=False,
        )
        if package.publication_status is not PublicationStatus.CANDIDATE_DRAFT:
            raise ValueError("candidate preview unexpectedly received release rights")
        if package.draft is None:
            raise ValueError("candidate preview generation did not produce a draft")
        return ResourceAgentResult(
            mode=ResourceGenerationMode.CANDIDATE_PREVIEW,
            profile_id=handoff.profile_id,
            path_id=handoff.path_id,
            graph_version=handoff.graph_version,
            concept_id=handoff.concept_id,
            depth=handoff.delivery_depth,
            publication_status="candidate_draft",
            preview_package=package,
        )

    @staticmethod
    def _validate_preview_scope(
        profile: LearnerProfileSnapshot,
        handoff: ResourceHandoffContract,
        retrieval: DomainRetrievalResult,
    ) -> None:
        if (
            profile.profile_id != handoff.profile_id
            or profile.graph_version != handoff.graph_version
            or retrieval.request.profile_id != handoff.profile_id
            or retrieval.request.concept_id != handoff.concept_id
            or retrieval.request.depth is not handoff.delivery_depth
        ):
            raise ValueError("candidate preview inputs do not share one identity")
        blockers = set(handoff.generation_gate.blocking_codes)
        if "blocked_hard_prerequisite" in blockers:
            raise ValueError("candidate preview cannot bypass hard prerequisites")
        if handoff.generation_gate.allowed or blockers != {
            "blocked_missing_published_evidence"
        }:
            raise ValueError("candidate preview requires only a published-evidence gap")


def _select_candidate_evidence(
    handoff: ResourceHandoffContract,
    retrieval: DomainRetrievalResult,
) -> dict[ContentKind, RetrievedEvidence]:
    selected: dict[ContentKind, RetrievedEvidence] = {}
    for kind in handoff.evidence_filters.content_kinds:
        matching = [
            item for item in retrieval.candidate_evidence if item.content_kind is kind
        ]
        if not matching:
            continue
        selected[kind] = min(
            matching,
            key=lambda item: (-item.score, item.evidence_key),
        )
    return selected


def _preview_policy(
    profile: LearnerProfileSnapshot,
    handoff: ResourceHandoffContract,
    selected: dict[ContentKind, RetrievedEvidence],
) -> GenerationPolicy:
    allowed = [
        AllowedEvidence(
            evidence_id=item.evidence_key,
            source_id=item.source_id,
            span_id=item.chunk_id,
            text=item.excerpt,
            approval_status=EvidenceApprovalStatus.CANDIDATE,
        )
        for item in selected.values()
    ]
    for kind in handoff.evidence_filters.content_kinds:
        if kind not in selected:
            allowed.append(_evidence_gap(handoff, kind))
    return GenerationPolicy.create(
        concept_id=handoff.concept_id,
        knowledge_scope=(handoff.concept_id,),
        forbidden_scope=(
            "transposed convolution",
            "dcgan",
            "textcnn",
            "gan",
        ),
        learning_objectives=handoff.learning_outcomes,
        delivery_depth=handoff.delivery_depth.value,
        prerequisite_gate_passed=True,
        unresolved_prerequisites=(),
        allowed_evidence=tuple(allowed),
        notebook_execution_required=False,
        personalization=_personalization(profile, handoff.concept_id),
    )


def _personalization(
    profile: LearnerProfileSnapshot,
    concept_id: str,
) -> PersonalizationPolicy:
    mastery = next(
        (
            item.mastery_score
            for item in profile.knowledge_mastery
            if item.concept_id == concept_id and item.mastery_score is not None
        ),
        0.0,
    )
    coding_score = profile.abilities.get("coding_ability")
    coding = coding_score.score if coding_score is not None else 0.0
    scaffolding = 3 if coding < 0.45 or mastery < 0.30 else 2 if coding < 0.80 else 1
    distribution = (
        (5, 2, 1)
        if scaffolding == 3
        else (3, 3, 2)
        if scaffolding == 2
        else (1, 2, 5)
    )
    error_codes = {
        item.code
        for item in profile.error_patterns
        if not item.concept_ids or concept_id in item.concept_ids
    }
    return PersonalizationPolicy(
        scaffolding_level=scaffolding,
        explanation_order_hint=tuple(profile.preferences.content_order)
        or ("intuition", "formula", "code"),
        exercise_difficulty_distribution=distribution,
        review_intensity=3 if mastery < 0.30 else 2 if mastery < 0.70 else 1,
        debugging_emphasis=(
            3 if {"logic_jump", "calculation_error"} & error_codes else 2
        ),
        presentation_preferences=tuple(profile.preferences.presentation),
    )


def _learner_context(
    profile: LearnerProfileSnapshot,
    concept_id: str,
) -> dict[str, str | int | float | tuple[str, ...]]:
    mastery = next(
        (
            item.mastery_score
            for item in profile.knowledge_mastery
            if item.concept_id == concept_id and item.mastery_score is not None
        ),
        0.0,
    )
    coding_score = profile.abilities.get("coding_ability")
    return {
        "mastery": mastery,
        "coding_level": coding_score.score if coding_score is not None else 0.0,
        "error_patterns": tuple(item.code for item in profile.error_patterns),
        "presentation": tuple(profile.preferences.presentation),
    }


def _preview_draft(
    handoff: ResourceHandoffContract,
    policy: GenerationPolicy,
    selected: dict[ContentKind, RetrievedEvidence],
) -> StructuredResourceDraft:
    definition = selected.get(ContentKind.DEFINITION)
    code = selected.get(ContentKind.CODE)
    exercise = selected.get(ContentKind.EXERCISE)
    definition_text, definition_id = _evidence_text(definition, handoff, ContentKind.DEFINITION)
    code_text, code_id = _evidence_text(code, handoff, ContentKind.CODE)
    exercise_text, _ = _evidence_text(exercise, handoff, ContentKind.EXERCISE)
    lecture_claim = TechnicalClaim(
        claim_id="preview-lecture-claim",
        text=definition_text,
        scope_id=handoff.concept_id,
        evidence_ids=(definition_id,),
    )
    practical_claim = TechnicalClaim(
        claim_id="preview-practical-claim",
        text=code_text,
        scope_id=handoff.concept_id,
        evidence_ids=(code_id,),
    )
    difficulty_levels = tuple(
        chain.from_iterable(
            repeat(level, count)
            for level, count in enumerate(
                policy.personalization.exercise_difficulty_distribution,
                start=1,
            )
        )
    )
    kinds = tuple(
        chain.from_iterable(repeat(kind, count) for kind, count in policy.quiz_structure)
    )
    questions = tuple(
        StudentQuizItem(
            question_id=f"preview-question-{index}",
            kind=kind,
            difficulty=difficulty_levels[index - 1],
            prompt=f"{handoff.learning_outcomes[(index - 1) % len(handoff.learning_outcomes)]}",
            hints=(),
        )
        for index, kind in enumerate(kinds, start=1)
    )
    teacher_answers = tuple(
        TeacherAnswerItem(
            question_id=question.question_id,
            answer=exercise_text,
            scoring_points=handoff.assessment_kinds,
            error_diagnosis="Check the learner's reasoning against the cited exercise.",
            teaching_action="Return to the related learning outcome before retrying.",
        )
        for question in questions
    )
    return StructuredResourceDraft(
        lecture=LectureDraft(
            title=f"{handoff.concept_id} lecture",
            sections=handoff.learning_outcomes,
            claims=(lecture_claim,),
            explanation_order=policy.personalization.explanation_order_hint,
        ),
        practical_guide=PracticalGuideDraft(
            title=f"{handoff.concept_id} practical guide",
            learning_steps=handoff.learning_outcomes,
            claims=(practical_claim,),
            notebook_tasks=(code_text,),
            debug_hint_depth=policy.personalization.debugging_emphasis,
        ),
        student_quiz=StudentQuizDraft(
            instructions="Complete each item using the supplied learning resources.",
            items=questions,
        ),
        teacher_guide=TeacherGuideDraft(
            items=teacher_answers,
            review_task_count=policy.personalization.review_intensity,
            feedback_strategy=("diagnose", "review", "retry"),
        ),
    )


def _evidence_gap(
    handoff: ResourceHandoffContract,
    kind: ContentKind,
) -> AllowedEvidence:
    key = f"evidence_gap_{handoff.concept_id}_{kind.value}"
    text = f"未检索到已审核的{kind.value}证据；本次仅生成候选结构草稿。"
    return AllowedEvidence(
        evidence_id=key,
        source_id="evidence-gap",
        span_id=key,
        text=text,
        approval_status=EvidenceApprovalStatus.CANDIDATE,
    )


def _evidence_text(
    item: RetrievedEvidence | None,
    handoff: ResourceHandoffContract,
    kind: ContentKind,
) -> tuple[str, str]:
    if item is not None:
        return item.excerpt, item.evidence_key
    gap = _evidence_gap(handoff, kind)
    return gap.text, gap.evidence_id
