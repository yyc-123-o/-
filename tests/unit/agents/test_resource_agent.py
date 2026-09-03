from datetime import UTC, datetime

from skillforge_kb.agents.resource_agent import (
    ResourceGenerationAgent,
    ResourceGenerationMode,
    _lesson_details,
    _lesson_enrichment,
    _preview_policy,
    _preview_quiz_content,
)
from skillforge_kb.agents.resource_tools import _resource_items
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
from skillforge_kb.ontology.models import (
    AbilityScore,
    AssessmentStatus,
    KnowledgeMastery,
    LearnerProfileSnapshot,
    LearningPreferences,
)
from skillforge_kb.ontology.resource_blueprints import ResourceType
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


def test_formal_resource_items_expose_learner_adaptation(resource_case) -> None:
    brief, _ = resource_case

    items = _resource_items(ResourceType.LECTURE, brief)

    assert items[0].startswith("个性化支架") or items[0].startswith("个性化路径")
    assert any(
        str(brief.resource_allocation.estimated_minutes) in item for item in items
    )


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


def test_preview_uses_a_multi_round_review_transcript(resource_case) -> None:
    """generate_preview wires ContentReviewAgent with max_attempts=3 (not the
    service default of 2): a passing draft still records its one review
    round, proving the transcript is wired through end to end."""

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
    assert len(result.preview_package.review_rounds) >= 1
    assert result.preview_package.review_rounds[-1].report == result.preview_package.audit_report


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
    assert {item.kind.value for item in draft.student_quiz.items} >= {
        "concept", "shape_reasoning", "code"
    }
    assert {item.correct_choice for item in draft.student_quiz.items} == {0, 1}
    assert all(len(set(item.choices)) == len(item.choices) for item in draft.student_quiz.items)
    assert all("用自己的话定义" not in item.prompt for item in draft.student_quiz.items)


def test_preview_lesson_changes_with_learner_evidence(resource_case) -> None:
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
    low_profile = _profile(handoff)
    high_profile = low_profile.model_copy(update={
        "abilities": {"coding_ability": AbilityScore(score=.9, confidence=.9, assessment_run_id="run-high")},
        "knowledge_mastery": [KnowledgeMastery(
            concept_id=handoff.concept_id,
            mastery_score=.85,
            assessment_status=AssessmentStatus.ASSESSED,
            confidence=.9,
            observed_at=datetime.now(UTC),
        )],
        "preferences": LearningPreferences(content_order=["formula", "code"], presentation=["示例优先"]),
    })
    low = ResourceGenerationAgent().generate_preview(low_profile, handoff, _candidate_retrieval(handoff)).preview_package.draft
    high = ResourceGenerationAgent().generate_preview(high_profile, handoff, _candidate_retrieval(handoff)).preview_package.draft
    assert low.lecture.sections[0] != high.lecture.sections[0]
    assert "分步支架" in low.lecture.sections[0]
    assert "较好掌握" in high.lecture.sections[0]
    assert low.student_quiz.instructions != high.student_quiz.instructions


def test_vector_preview_quiz_is_answerable_and_content_specific() -> None:
    first_prompt, first_choices, first_answer = _preview_quiz_content(
        "向量", "concept", 1
    )
    dot_prompt, dot_choices, dot_answer = _preview_quiz_content("向量", "code", 6)

    assert "$v=[3,4]$" in first_prompt
    assert first_choices[first_answer].startswith("它表示两个有顺序的分量")
    assert "np.dot" in dot_prompt
    assert dot_choices[dot_answer] == "11"
    assert {
        _preview_quiz_content("向量", "concept", index)[2]
        for index in range(1, 9)
    } == {0, 1, 2}


def test_matrix_multiplication_preview_quiz_is_unique_and_answerable() -> None:
    items = [
        _preview_quiz_content("矩阵乘法", "concept", index)
        for index in range(1, 9)
    ]

    prompts = [item[0] for item in items]
    choices = [choice for _, item_choices, _ in items for choice in item_choices]
    assert len(set(prompts)) == 8
    assert all(len(item_choices) == 3 for _, item_choices, _ in items)
    assert all(len(set(item_choices)) == 3 for _, item_choices, _ in items)
    assert all(item[2] in range(3) for item in items)
    assert "只需记住名称" not in choices
    assert "对所有输入都适用" not in choices


def test_generic_preview_quiz_varies_by_check_angle() -> None:
    items = [
        _preview_quiz_content("注意力机制", "concept", index)
        for index in range(1, 9)
    ]

    prompts = [item[0] for item in items]
    choices = [choice for _, item_choices, _ in items for choice in item_choices]
    assert len(set(prompts)) == 8
    assert all(len(set(item_choices)) == 3 for _, item_choices, _ in items)
    assert "只需记住名称" not in choices
    assert "对所有输入都适用" not in choices


def test_lesson_formulas_use_katex_delimiters() -> None:
    details = (
        _lesson_details("标量")
        + _lesson_details("向量")
        + _lesson_details("矩阵")
        + _lesson_details("卷积运算")
    )
    enrichment = (
        _lesson_enrichment("标量")
        + _lesson_enrichment("向量")
        + _lesson_enrichment("矩阵")
        + _lesson_enrichment("卷积运算")
    )
    formula_text = " ".join((*details, *enrichment))

    assert "$" in formula_text
    assert "v' = s·v" not in formula_text
    assert "floor((H+2P-K)/S)+1" not in formula_text


def test_generic_preview_quiz_uses_current_node_evidence() -> None:
    facts = (
        "Embedding 将离散词索引映射为稠密向量表示。",
        "代码示例使用 embedding_layer(token_ids) 得到每个词的向量。",
        "练习要求比较相似词与无关词的余弦相似度。",
        "能够解释嵌入表示如何支持语义检索。",
    )
    prompt, choices, answer = _preview_quiz_content(
        "嵌入表示", "concept", 2, facts
    )

    assert "嵌入表示" in prompt
    assert choices[answer].startswith("代码示例使用")
    assert "只需记住名称" not in choices[answer]


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
