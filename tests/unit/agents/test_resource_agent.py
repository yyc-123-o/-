from skillforge_kb.agents.resource_agent import (
    ResourceGenerationAgent,
    ResourceGenerationMode,
    _preview_policy,
)
from skillforge_kb.agents.retrieval_agent_models import (
    DomainRetrievalRequest,
    DomainRetrievalResult,
    EvidenceGap,
    EvidenceSummary,
    RetrievalMethod,
    RetrievedEvidence,
)
from skillforge_kb.domain.enums import ContentKind, LicenseStatus
from skillforge_kb.evidence.models import EvidenceReviewStatus
from skillforge_kb.ontology.models import LearnerProfileSnapshot
from skillforge_kb.resources.handoff import ResourceHandoffContract
from skillforge_kb.resources.models import GenerationGate, build_brief_id


def _profile(handoff: ResourceHandoffContract) -> LearnerProfileSnapshot:
    return LearnerProfileSnapshot(
        schema_version="learner-profile.v1",
        profile_id=handoff.profile_id,
        learner_ref="0" * 64,
        graph_version=handoff.graph_version,
    )


def _handoff_with_gate(
    handoff: ResourceHandoffContract,
    gate: GenerationGate,
) -> ResourceHandoffContract:
    payload = handoff.model_dump(exclude={"brief_id"})
    payload["generation_gate"] = gate.model_dump(mode="json")
    return ResourceHandoffContract(
        **payload,
        brief_id=build_brief_id(payload),
    )


def _candidate_retrieval(handoff: ResourceHandoffContract) -> DomainRetrievalResult:
    request = DomainRetrievalRequest(
        original_query=handoff.concept_id,
        rewritten_queries=(handoff.concept_id,),
        profile_id=handoff.profile_id,
        concept_id=handoff.concept_id,
        depth=handoff.delivery_depth,
        top_k=5,
    )
    by_kind = {
        ContentKind.DEFINITION: "Convolution applies a local kernel to an input.",
        ContentKind.CODE: "nn.Conv2d maps an input tensor to an output tensor.",
        ContentKind.EXERCISE: "Calculate the output size from padding and stride.",
    }
    candidates = tuple(
        RetrievedEvidence(
            evidence_key=f"candidate-{kind.value}",
            chunk_id=f"chunk-{kind.value}",
            source_id="source-cnn",
            source_title="CNN learning material",
            heading_path=(kind.value,),
            excerpt=by_kind[kind],
            locator=f"section:{kind.value}",
            score=1.0,
            retrieval_method=RetrievalMethod.BM25,
            concept_id=handoff.concept_id,
            depth=handoff.delivery_depth,
            content_kind=kind,
            review_status=EvidenceReviewStatus.CANDIDATE,
            license_status=LicenseStatus.PENDING,
            evidence_status="candidate",
        )
        for kind in handoff.evidence_filters.content_kinds
    )
    missing = handoff.evidence_filters.content_kinds
    return DomainRetrievalResult(
        request=request,
        candidate_evidence=candidates,
        concept_evidence={
            handoff.concept_id: tuple(item.evidence_key for item in candidates)
        },
        evidence_summary=EvidenceSummary(
            formal_count=0,
            candidate_count=len(candidates),
            available_content_kinds=missing,
            missing_content_kinds=missing,
        ),
        evidence_gap=EvidenceGap(
            missing_content_kinds=missing,
            message="published evidence is missing",
        ),
    )


def test_strict_generation_uses_formal_tool(resource_case) -> None:
    brief, bundle = resource_case
    handoff = ResourceHandoffContract.from_brief(brief)

    result = ResourceGenerationAgent().generate_strict(handoff, bundle)

    assert result.mode is ResourceGenerationMode.STRICT
    assert result.formal_package is not None
    assert result.preview_package is None
    assert result.publication_status == "formal"


def test_preview_does_not_open_formal_gate(resource_case) -> None:
    brief, _ = resource_case
    handoff = _handoff_with_gate(
        ResourceHandoffContract.from_brief(brief),
        GenerationGate(
            allowed=False,
            status="blocked_missing_published_evidence",
            blocking_codes=("blocked_missing_published_evidence",),
            next_action="publish required evidence before generation",
        ),
    )

    result = ResourceGenerationAgent().generate_preview(
        _profile(handoff),
        handoff,
        _candidate_retrieval(handoff),
    )

    assert handoff.generation_gate.allowed is False
    assert result.formal_package is None
    assert result.preview_package is not None
    assert result.preview_package.draft is not None
    assert result.preview_package.audit_status.value == "passed"
    assert result.publication_status == "candidate_draft"


def test_preview_policy_does_not_carry_cnn_demo_scope_bans(resource_case) -> None:
    brief, _ = resource_case
    handoff = _handoff_with_gate(
        ResourceHandoffContract.from_brief(brief),
        GenerationGate(
            allowed=False,
            status="blocked_missing_published_evidence",
            blocking_codes=("blocked_missing_published_evidence",),
            next_action="publish required evidence before generation",
        ),
    )

    candidates = _candidate_retrieval(handoff).candidate_evidence
    policy = _preview_policy(
        _profile(handoff),
        handoff,
        {item.content_kind: item for item in candidates},
    )

    assert policy.forbidden_scope == ()


def test_preview_materials_are_specific_to_node_and_question_kind(resource_case) -> None:
    brief, _ = resource_case
    handoff = _handoff_with_gate(
        ResourceHandoffContract.from_brief(brief),
        GenerationGate(
            allowed=False,
            status="blocked_missing_published_evidence",
            blocking_codes=("blocked_missing_published_evidence",),
            next_action="publish required evidence before generation",
        ),
    )

    result = ResourceGenerationAgent().generate_preview(
        _profile(handoff),
        handoff,
        _candidate_retrieval(handoff),
    )
    assert result.preview_package is not None
    assert result.preview_package.draft is not None
    draft = result.preview_package.draft

    assert any("标量" in section for section in draft.lecture.sections)
    assert len({item.prompt for item in draft.student_quiz.items}) == len(
        draft.student_quiz.items
    )
    assert any("概念" in item.prompt for item in draft.student_quiz.items)
    assert any("形状" in item.prompt for item in draft.student_quiz.items)
    assert any("代码" in item.prompt for item in draft.student_quiz.items)


def test_preview_contains_readable_lesson_and_editable_practice(resource_case) -> None:
    brief, _ = resource_case
    handoff = _handoff_with_gate(
        ResourceHandoffContract.from_brief(brief),
        GenerationGate(
            allowed=False,
            status="blocked_missing_published_evidence",
            blocking_codes=("blocked_missing_published_evidence",),
            next_action="publish required evidence before generation",
        ),
    )

    result = ResourceGenerationAgent().generate_preview(
        _profile(handoff), handoff, _candidate_retrieval(handoff)
    )
    draft = result.preview_package.draft  # type: ignore[union-attr]

    assert {block.kind for block in draft.lecture.blocks} == {
        "objective", "intuition", "definition", "derivation", "example", "pitfall", "summary"
    }
    assert all(len(block.body) > 40 for block in draft.lecture.blocks)
    assert draft.practical_guide.exercise.language == "python"
    assert "TODO" in draft.practical_guide.exercise.starter_code
    assert draft.practical_guide.exercise.checks
    assert all(len(item.choices) >= 2 for item in draft.student_quiz.items)
    assert all(item.correct_choice is not None for item in draft.student_quiz.items)


def test_public_preview_json_hides_teacher_guide_and_choice_key(resource_case) -> None:
    brief, _ = resource_case
    handoff = _handoff_with_gate(
        ResourceHandoffContract.from_brief(brief),
        GenerationGate(
            allowed=False,
            status="blocked_missing_published_evidence",
            blocking_codes=("blocked_missing_published_evidence",),
            next_action="publish required evidence before generation",
        ),
    )
    result = ResourceGenerationAgent().generate_preview(
        _profile(handoff), handoff, _candidate_retrieval(handoff)
    )
    public = result.model_dump(mode="json")
    draft = public["preview_package"]["draft"]
    assert "teacher_guide" not in draft
    assert all("correct_choice" not in item for item in draft["student_quiz"]["items"])


def test_preview_rejects_hard_prerequisite_block(resource_case) -> None:
    brief, _ = resource_case
    handoff = _handoff_with_gate(
        ResourceHandoffContract.from_brief(brief),
        GenerationGate(
            allowed=False,
            status="blocked_prerequisite_and_evidence",
            blocking_codes=(
                "blocked_hard_prerequisite",
                "blocked_missing_published_evidence",
            ),
            next_action="complete prerequisites and publish evidence",
        ),
    )

    try:
        ResourceGenerationAgent().generate_preview(
            _profile(handoff),
            handoff,
            _candidate_retrieval(handoff),
        )
    except ValueError as exc:
        assert "hard prerequisites" in str(exc)
    else:
        raise AssertionError("hard prerequisite blocker was bypassed")
