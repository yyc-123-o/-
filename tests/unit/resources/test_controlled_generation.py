from skillforge_kb.resources.controlled_generation import (
    AllowedEvidence,
    AuditStatus,
    ClaimSupportStatus,
    ControlledResourceGenerationService,
    EvidenceApprovalStatus,
    FakeLLMAdapter,
    GenerationPolicy,
    LectureDraft,
    PersonalizationPolicy,
    PracticalGuideDraft,
    PublicationStatus,
    QuizKind,
    ResourceAuditor,
    ResourceGenerationBrief,
    StructuredResourceDraft,
    StudentQuizDraft,
    StudentQuizItem,
    TeacherAnswerItem,
    TeacherGuideDraft,
    TechnicalClaim,
)


class SupportingVerifier:
    def verify(self, *, claim: str, evidence_span: str) -> ClaimSupportStatus:
        return ClaimSupportStatus.SUPPORTED


class UncertainVerifier:
    def verify(self, *, claim: str, evidence_span: str) -> ClaimSupportStatus:
        return ClaimSupportStatus.UNCERTAIN


def _policy(*, gate: bool = False, approved: bool = False) -> GenerationPolicy:
    return GenerationPolicy.create(
        concept_id="dl.cnn.convolution",
        knowledge_scope=("dl.cnn.convolution",),
        forbidden_scope=("transposed convolution", "dcgan"),
        learning_objectives=("explain convolution", "calculate output shape", "build Conv2d"),
        delivery_depth="intro",
        prerequisite_gate_passed=gate,
        unresolved_prerequisites=() if gate else ("dl.vision.image-tensor",),
        allowed_evidence=(
            AllowedEvidence(
                evidence_id="candidate-definition-1",
                source_id="cnn-source",
                span_id="cnn-chunk-1",
                text="convolution uses local kernels",
                approval_status=(
                    EvidenceApprovalStatus.APPROVED
                    if approved
                    else EvidenceApprovalStatus.REVIEWED
                ),
            ),
        ),
        personalization=PersonalizationPolicy(
            scaffolding_level=2,
            explanation_order_hint=("intuition", "formula", "code"),
            exercise_difficulty_distribution=(3, 3, 2),
            review_intensity=2,
            debugging_emphasis=2,
        ),
    )


def _draft(*, leaked: bool = False) -> StructuredResourceDraft:
    claim = TechnicalClaim(
        claim_id="claim-1",
        text="convolution uses local kernels",
        scope_id="dl.cnn.convolution",
        evidence_ids=("candidate-definition-1",),
    )
    kinds = (
        QuizKind.CONCEPT,
        QuizKind.CONCEPT,
        QuizKind.SHAPE_REASONING,
        QuizKind.SHAPE_REASONING,
        QuizKind.CODE,
        QuizKind.CODE,
        QuizKind.DEBUGGING,
        QuizKind.SYNTHESIS,
    )
    questions = tuple(
        StudentQuizItem(
            question_id=f"question-{index}",
            kind=kind,
            difficulty=2,
            prompt=(
                "答案：local kernels"
                if leaked and index == 1
                else f"Question {index}: explain the target concept."
            ),
        )
        for index, kind in enumerate(kinds, start=1)
    )
    answers = tuple(
        TeacherAnswerItem(
            question_id=item.question_id,
            answer="Review the evidence-bound explanation.",
            scoring_points=("identifies the concept",),
            error_diagnosis="concept confusion",
            teaching_action="revisit the lecture definition",
        )
        for item in questions
    )
    return StructuredResourceDraft(
        lecture=LectureDraft(
            title="Convolution",
            sections=("intuition", "shape"),
            claims=(claim,),
        ),
        practical_guide=PracticalGuideDraft(
            title="Conv2d lab",
            learning_steps=("predict output", "run the layer"),
            claims=(claim,),
            notebook_tasks=("observe output shape",),
        ),
        student_quiz=StudentQuizDraft(
            instructions="Complete all questions.",
            items=questions,
        ),
        teacher_guide=TeacherGuideDraft(items=answers),
    )


def _brief(policy: GenerationPolicy) -> ResourceGenerationBrief:
    return ResourceGenerationBrief.create(
        profile_id="PROFILE-2026-0001-DEMO",
        policy=policy,
        learner_context={"coding_level": 0.7, "pace": "medium"},
    )


def test_policy_is_immutable_and_identity_bound() -> None:
    policy = _policy()
    assert policy.policy_id.startswith("policy_")
    assert policy.policy_hash == policy.policy_id.removeprefix("policy_")


def test_generation_completes_but_blocked_gate_keeps_candidate_status() -> None:
    package = ControlledResourceGenerationService(
        FakeLLMAdapter(_draft()),
        ResourceAuditor(SupportingVerifier()),
    ).generate(_brief(_policy(approved=True)), notebook_passed=True)

    assert package.generation_status.value == "completed"
    assert package.audit_status is AuditStatus.PASSED
    assert package.publication_status is PublicationStatus.CANDIDATE_DRAFT


def test_allowed_gate_can_produce_release_candidate() -> None:
    package = ControlledResourceGenerationService(
        FakeLLMAdapter(_draft()),
        ResourceAuditor(SupportingVerifier()),
    ).generate(_brief(_policy(gate=True, approved=True)), notebook_passed=True)

    assert package.audit_status is AuditStatus.PASSED
    assert package.publication_status is PublicationStatus.RELEASE_CANDIDATE


def test_invalid_model_shape_is_generation_failure() -> None:
    package = ControlledResourceGenerationService(
        FakeLLMAdapter({"lecture": {}}),
    ).generate(_brief(_policy()), notebook_passed=True)

    assert package.generation_status.value == "failed"
    assert package.audit_status is AuditStatus.NOT_RUN


def test_uncertain_claim_needs_review_without_hard_failure() -> None:
    package = ControlledResourceGenerationService(
        FakeLLMAdapter(_draft()),
        ResourceAuditor(UncertainVerifier()),
    ).generate(_brief(_policy()), notebook_passed=True)

    assert package.generation_status.value == "completed"
    assert package.audit_status is AuditStatus.NEEDS_REVIEW
