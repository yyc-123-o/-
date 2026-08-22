# ruff: noqa: E501
from __future__ import annotations

from skillforge_kb.resources.controlled_evaluation import (
    EvaluationProfile,
    evaluate_profiles,
)
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
from skillforge_kb.resources.controlled_input import build_brief_from_handoffs


class SupportingVerifier:
    def verify(self, *, claim: str, evidence_span: str) -> ClaimSupportStatus:
        return ClaimSupportStatus.SUPPORTED


class UncertainVerifier:
    def verify(self, *, claim: str, evidence_span: str) -> ClaimSupportStatus:
        return ClaimSupportStatus.UNCERTAIN


def _policy(*, gate: bool = False, approved: bool = False) -> GenerationPolicy:
    return GenerationPolicy.create(
        concept_id="dl.cnn.convolution",
        knowledge_scope=("cnn_basics", "conv2d"),
        forbidden_scope=("resnet",),
        learning_objectives=("explain convolution", "calculate output shape", "build Conv2d"),
        delivery_depth="intro",
        prerequisite_gate_passed=gate,
        unresolved_prerequisites=() if gate else ("image_tensor",),
        allowed_evidence=(
            AllowedEvidence(
                evidence_id="E-1",
                source_id="cnn-book",
                span_id="chunk-1",
                text="convolution uses local kernels",
                approval_status=EvidenceApprovalStatus.APPROVED
                if approved
                else EvidenceApprovalStatus.REVIEWED,
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
        claim_id="C-1",
        text="convolution uses local kernels",
        scope_id="cnn_basics",
        evidence_ids=("E-1",),
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
            question_id=f"Q-{index}",
            kind=kind,
            difficulty=2,
            prompt=("答案：local kernels" if leaked and index == 1 else f"question {index}"),
        )
        for index, kind in enumerate(kinds, start=1)
    )
    answers = tuple(
        TeacherAnswerItem(
            question_id=item.question_id,
            answer="teacher-only answer",
            scoring_points=("point",),
            error_diagnosis="misconception",
            teaching_action="review",
        )
        for item in questions
    )
    return StructuredResourceDraft(
        lecture=LectureDraft(title="CNN", sections=("intuition",), claims=(claim,)),
        practical_guide=PracticalGuideDraft(
            title="Conv2d lab",
            learning_steps=("predict", "run"),
            claims=(claim,),
            notebook_tasks=("observe output shape",),
        ),
        student_quiz=StudentQuizDraft(instructions="Complete all questions.", items=questions),
        teacher_guide=TeacherGuideDraft(items=answers),
    )


def _brief(policy: GenerationPolicy) -> ResourceGenerationBrief:
    return ResourceGenerationBrief.create(
        profile_id="current-profile",
        policy=policy,
        learner_context={"coding_level": 0.7, "pace": "medium"},
    )


def test_policy_is_immutable_and_identity_bound() -> None:
    policy = _policy()
    assert policy.policy_id.startswith("policy_")
    assert policy.policy_hash == policy.policy_id.removeprefix("policy_")


def test_generation_completed_but_gate_keeps_candidate_draft() -> None:
    policy = _policy(gate=False, approved=True)
    package = ControlledResourceGenerationService(
        FakeLLMAdapter(_draft()), ResourceAuditor(SupportingVerifier())
    ).generate(_brief(policy), notebook_passed=True)

    assert package.generation_status.value == "completed"
    assert package.audit_status is AuditStatus.PASSED
    assert package.publication_status is PublicationStatus.CANDIDATE_DRAFT
    assert set(package.trace.material_prompt_hashes) == {
        "lecture",
        "practical_guide",
        "student_quiz",
        "teacher_guide",
    }


def test_release_candidate_requires_referenced_approved_evidence_and_passed_audit() -> None:
    policy = _policy(gate=True, approved=True)
    package = ControlledResourceGenerationService(
        FakeLLMAdapter(_draft()), ResourceAuditor(SupportingVerifier())
    ).generate(_brief(policy), notebook_passed=True)

    assert package.audit_status is AuditStatus.PASSED
    assert package.publication_status is PublicationStatus.RELEASE_CANDIDATE


def test_answer_leakage_is_audit_failure_after_successful_generation() -> None:
    package = ControlledResourceGenerationService(
        FakeLLMAdapter(_draft(leaked=True)), ResourceAuditor(SupportingVerifier())
    ).generate(_brief(_policy()), notebook_passed=True)

    assert package.generation_status.value == "completed"
    assert package.audit_status is AuditStatus.FAILED
    assert any(item.code == "answer_leakage" for item in package.audit_report.findings)  # type: ignore[union-attr]


def test_invalid_model_shape_is_generation_failure_and_audit_is_not_run() -> None:
    package = ControlledResourceGenerationService(FakeLLMAdapter({"lecture": {}})).generate(
        _brief(_policy()), notebook_passed=True
    )

    assert package.generation_status.value == "failed"
    assert package.audit_status is AuditStatus.NOT_RUN


def test_uncertain_claim_needs_review_without_hard_failure() -> None:
    package = ControlledResourceGenerationService(
        FakeLLMAdapter(_draft()), ResourceAuditor(UncertainVerifier())
    ).generate(_brief(_policy()), notebook_passed=True)

    assert package.generation_status.value == "completed"
    assert package.audit_status is AuditStatus.NEEDS_REVIEW


def test_three_profile_evaluation_only_varies_personalization() -> None:
    base = _policy()
    profiles = (
        EvaluationProfile(
            profile_id="support",
            role="control",
            learner_context={"coding_level": 0.2},
            personalization=PersonalizationPolicy(
                scaffolding_level=3,
                explanation_order_hint=("intuition", "diagram", "code"),
                exercise_difficulty_distribution=(5, 2, 1),
                review_intensity=3,
                debugging_emphasis=1,
            ),
        ),
        EvaluationProfile(
            profile_id="current",
            role="baseline",
            learner_context={"coding_level": 0.7},
            personalization=base.personalization,
        ),
        EvaluationProfile(
            profile_id="advanced",
            role="control",
            learner_context={"coding_level": 0.9},
            personalization=PersonalizationPolicy(
                scaffolding_level=1,
                explanation_order_hint=("formula", "debug", "code"),
                exercise_difficulty_distribution=(1, 2, 5),
                review_intensity=1,
                debugging_emphasis=3,
            ),
        ),
    )
    report = evaluate_profiles(
        base_policy=base,
        profiles=profiles,
        service_factory=lambda: ControlledResourceGenerationService(
            FakeLLMAdapter(_draft()), ResourceAuditor(SupportingVerifier())
        ),
        notebook_passed=True,
    )

    assert report.reference_profile_id == "current"
    assert report.comparison_matrix["support"]["scaffolding_level"] == 3
    assert report.comparison_matrix["advanced"]["advanced_question_count"] == 5
    assert all(
        item.package.publication_status is PublicationStatus.CANDIDATE_DRAFT
        for item in report.results
    )


def test_handoff_adapter_preserves_blocked_gate_and_candidate_evidence() -> None:
    brief = build_brief_from_handoffs(
        profile={"profile_id": "P-1"},
        handoff={
            "profile_id": "P-1",
            "concept_id": "dl.cnn.convolution",
            "depth": "intro",
            "learning_requirements": {"learning_outcomes": ["explain convolution"]},
            "resource_generation_gate": {"allowed": False},
            "prerequisites": {
                "canonical_hard_prerequisites": [
                    {"concept_id": "dl.vision.image-tensor", "blocking": True}
                ]
            },
            "learner_adaptation": {
                "source_mastery": {"mastery": 0.18},
                "ability_summary": {"coding_ability": 0.7},
                "presentation_preferences": {"content_order": ["intuition", "code"]},
            },
        },
        retrieval={
            "candidate_evidence": [
                {
                    "chunk_id": "cnn-1",
                    "doc_id": "course-note",
                    "excerpt": "convolution uses local kernels",
                    "review_status": "unreviewed",
                }
            ]
        },
    )

    assert brief.policy.prerequisite_gate_passed is False
    assert brief.policy.unresolved_prerequisites == ("dl.vision.image-tensor",)
    assert brief.policy.allowed_evidence[0].approval_status is EvidenceApprovalStatus.CANDIDATE
