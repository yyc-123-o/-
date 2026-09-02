# ruff: noqa: E501
from __future__ import annotations

from skillforge_kb.resources.controlled_generation import (
    AllowedEvidence,
    AuditStatus,
    ClaimSupportStatus,
    ContentReviewAgent,
    EvidenceApprovalStatus,
    GenerationPolicy,
    LectureDraft,
    PersonalizationPolicy,
    PracticalGuideDraft,
    QuizKind,
    ResourceAuditor,
    ReviewDecisionStatus,
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


def _policy() -> GenerationPolicy:
    return GenerationPolicy.create(
        concept_id="dl.cnn.convolution",
        knowledge_scope=("cnn_basics", "conv2d"),
        forbidden_scope=("resnet",),
        learning_objectives=("explain convolution", "calculate output shape", "build Conv2d"),
        delivery_depth="intro",
        prerequisite_gate_passed=True,
        unresolved_prerequisites=(),
        allowed_evidence=(
            AllowedEvidence(
                evidence_id="E-1",
                source_id="cnn-book",
                span_id="chunk-1",
                text="convolution uses local kernels",
                approval_status=EvidenceApprovalStatus.APPROVED,
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


def test_review_approves_a_clean_draft_backed_by_supported_evidence() -> None:
    agent = ContentReviewAgent(ResourceAuditor(SupportingVerifier()))

    decision = agent.review(_draft(), _policy(), notebook_passed=True)

    assert decision.status is ReviewDecisionStatus.APPROVED
    assert decision.report.audit_status is AuditStatus.PASSED
    assert decision.revision_instructions is None


def test_review_approves_with_needs_review_when_a_claim_is_uncertain() -> None:
    agent = ContentReviewAgent(ResourceAuditor(UncertainVerifier()))

    decision = agent.review(_draft(), _policy(), notebook_passed=True)

    assert decision.status is ReviewDecisionStatus.APPROVED
    assert decision.report.audit_status is AuditStatus.NEEDS_REVIEW
    assert decision.revision_instructions is None


def test_review_sends_a_leaked_answer_draft_back_for_revision() -> None:
    agent = ContentReviewAgent(ResourceAuditor(SupportingVerifier()))

    decision = agent.review(_draft(leaked=True), _policy(), notebook_passed=True)

    assert decision.status is ReviewDecisionStatus.NEEDS_REVISION
    assert decision.report.audit_status is AuditStatus.FAILED
    assert decision.revision_instructions is not None
    assert "answer" in decision.revision_instructions.lower() or any(
        finding.code == "answer_leakage" for finding in decision.report.findings
    )
    assert decision.revision_instructions == "; ".join(
        finding.message for finding in decision.report.findings
    )


def test_review_defaults_to_its_own_auditor_when_none_is_supplied() -> None:
    agent = ContentReviewAgent()

    decision = agent.review(_draft(), _policy(), notebook_passed=True)

    assert agent.auditor is not None
    assert decision.status is ReviewDecisionStatus.APPROVED
