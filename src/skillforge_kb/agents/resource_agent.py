import json
import re
from enum import StrEnum
from itertools import chain, repeat
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from skillforge_kb.domain.enums import ContentKind
from skillforge_kb.ontology.models import (
    CONCEPT_ID_PATTERN,
    DepthLevel,
    LearnerProfileSnapshot,
)
from skillforge_kb.resources.controlled_generation import (
    AllowedEvidence,
    CandidateLearningPackage,
    ContentReviewAgent,
    ControlledResourceGenerationService,
    EvidenceApprovalStatus,
    FakeLLMAdapter,
    GenerationPolicy,
    LectureDraft,
    LessonBlock,
    LLMAdapter,
    PersonalizationPolicy,
    PracticalGuideDraft,
    PracticeExercise,
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

    @model_serializer(mode="wrap")
    def serialize_public(self, handler, info):
        """Keep teacher answers and choice keys server-side in JSON responses."""
        data = handler(self)
        if info.mode == "json" and self.preview_package is not None:
            preview = data.get("preview_package")
            if isinstance(preview, dict):
                draft = preview.get("draft")
                if isinstance(draft, dict):
                    draft.pop("teacher_guide", None)
                    quiz = draft.get("student_quiz")
                    if isinstance(quiz, dict):
                        for item in quiz.get("items", []):
                            if isinstance(item, dict):
                                item.pop("correct_choice", None)
        return data

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
    def __init__(self, llm_adapter: LLMAdapter | None = None) -> None:
        self._llm_adapter = llm_adapter
        # A separately addressable "审核 Agent" role: the generation agent
        # hands its drafts to this agent for cross-verification rather than
        # auditing its own output. Held once here so callers (and future
        # orchestration/tracing hooks) can reach it directly.
        self._review_agent = ContentReviewAgent()

    @property
    def llm_adapter(self) -> LLMAdapter | None:
        return self._llm_adapter

    @property
    def review_agent(self) -> ContentReviewAgent:
        return self._review_agent

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
        fallback_draft = _preview_draft(handoff, policy, selected)
        # Let the configured model personalize learner-facing materials. Scope,
        # evidence, depth and publication status remain controlled locally; invalid
        # responses fall back to the deterministic evidence-bounded draft.
        adapter = (
            _ModelFirstAdapter(self._llm_adapter, fallback_draft)
            if self._llm_adapter is not None
            else FakeLLMAdapter(fallback_draft)
        )
        # max_attempts=3: a genuine multi-round generation-review trip, not the
        # library default's single retry -- the review Agent gets up to two
        # chances to send a rejected draft back before this preview gives up.
        package = ControlledResourceGenerationService(
            adapter,
            auditor=self._review_agent.auditor,
            max_attempts=3,
        ).generate(brief, notebook_passed=False)
        if package.draft is None and self._llm_adapter is not None:
            package = ControlledResourceGenerationService(
                FakeLLMAdapter(fallback_draft),
                auditor=self._review_agent.auditor,
                max_attempts=3,
            ).generate(brief, notebook_passed=False)
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


class _ModelFirstAdapter:
    """Use the external model for learner materials with local fallbacks."""

    structured_output_mode = "json_object"

    def __init__(self, model: LLMAdapter, fallback: StructuredResourceDraft) -> None:
        self._model = model
        self._fallback = FakeLLMAdapter(fallback)
        self.model_name = model.model_name
        self._student_question_ids: tuple[str, ...] = ()

    def complete(self, prompt: str, *, repair: str | None = None) -> str:
        material_match = re.match(r"MATERIAL: ([a-z_]+)", prompt)
        material = material_match.group(1) if material_match else None
        if material in {"lecture", "practical_guide", "student_quiz", "teacher_guide"}:
            try:
                raw = self._model.complete(prompt, repair=repair)
            except Exception:
                raw = self._fallback.complete(prompt, repair=repair)
            if material == "student_quiz":
                self._remember_student_ids(raw)
            elif material == "teacher_guide":
                raw = self._align_teacher_ids(raw)
            return raw
        return self._fallback.complete(prompt, repair=repair)

    def _remember_student_ids(self, raw: str) -> None:
        try:
            items = json.loads(raw).get("items", [])
            ids = tuple(item["question_id"] for item in items if item.get("question_id"))
        except (AttributeError, KeyError, TypeError, json.JSONDecodeError):
            ids = ()
        if ids:
            self._student_question_ids = ids

    def _align_teacher_ids(self, raw: str) -> str:
        if not self._student_question_ids:
            return raw
        try:
            payload = json.loads(raw)
            items = payload.get("items")
            if not isinstance(items, list) or len(items) != len(self._student_question_ids):
                return raw
            for item, question_id in zip(items, self._student_question_ids, strict=True):
                if isinstance(item, dict):
                    item["question_id"] = question_id
            return json.dumps(payload, ensure_ascii=False)
        except (AttributeError, TypeError, json.JSONDecodeError):
            return raw


def _select_candidate_evidence(
    handoff: ResourceHandoffContract,
    retrieval: DomainRetrievalResult,
) -> dict[ContentKind, RetrievedEvidence]:
    selected: dict[ContentKind, RetrievedEvidence] = {}
    for kind in handoff.evidence_filters.content_kinds:
        matching = [
            item
            for item in retrieval.candidate_evidence
            if item.content_kind is kind and _candidate_matches_topic(item, handoff)
        ]
        if not matching:
            continue
        selected[kind] = min(
            matching,
            key=lambda item: (-item.score, item.evidence_key),
        )
    return selected


def _candidate_matches_topic(
    item: RetrievedEvidence,
    handoff: ResourceHandoffContract,
) -> bool:
    """Keep adjacent-topic retrieval hits out of student-facing lesson prose."""
    text = " ".join((item.source_title, *item.heading_path, item.excerpt)).casefold()
    if handoff.concept_id.startswith("dl.cnn."):
        distractors = (
            "gan", "dcgan", "生成对抗", "textcnn", "lstm", "n-gram", "注意力",
        )
        if any(marker in text for marker in distractors):
            cnn_markers = (
                "conv2d", "padding", "stride", "输出尺寸", "互相关",
            )
            return any(marker in text for marker in cnn_markers)
    return True


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
        forbidden_scope=(),
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
            3 if {"logic_gap", "calculation_error"} & error_codes else 2
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
    topic = _concept_label(handoff.concept_id)
    outcome = _clean_outcome(handoff.learning_outcomes[0])
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
        _preview_quiz_item(
            topic=topic,
            kind=kind,
            index=index,
            difficulty=difficulty_levels[index - 1],
            # Learning outcomes describe the goal, not evidence for a quiz answer.
            facts=(definition_text, code_text, exercise_text),
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
            title=f"{topic}：概念讲义",
            sections=_lecture_sections(topic, outcome, definition_text, policy.personalization),
            claims=(lecture_claim,),
            explanation_order=policy.personalization.explanation_order_hint,
            blocks=_lesson_blocks(topic, outcome, definition_text),
        ),
        practical_guide=PracticalGuideDraft(
            title=f"{topic}：实操指南",
            learning_steps=_practical_steps(topic, outcome, code_text, policy.personalization),
            claims=(practical_claim,),
            notebook_tasks=_notebook_tasks(topic, outcome, code_text),
            experiment_protocol=_experiment_protocol(topic),
            debug_hint_depth=policy.personalization.debugging_emphasis,
            exercise=_practice_exercise(topic, outcome),
            project_exercise=_project_exercise(topic, outcome),
        ),
        student_quiz=StudentQuizDraft(
            instructions=_quiz_instructions(policy.personalization),
            items=questions,
        ),
        teacher_guide=TeacherGuideDraft(
            items=teacher_answers,
            review_task_count=policy.personalization.review_intensity,
            feedback_strategy=("diagnose", "review", "retry"),
        ),
    )


_CONCEPT_LABELS = {
    "scalar": "标量",
    "vector": "向量",
    "matrix": "矩阵",
    "tensor": "张量",
    "matrix-operations": "矩阵运算",
    "matrix-multiplication": "矩阵乘法",
    "norm": "范数",
    "eigen-decomposition": "特征值分解",
    "svd": "奇异值分解",
    "derivative-gradient": "导数与梯度",
    "random-variable": "随机变量",
    "probability-distribution": "概率分布",
    "convolution": "卷积运算",
    "cross-correlation": "互相关",
    "pooling": "池化",
    "cnn": "卷积神经网络",
}

_CONCEPT_EXPLANATIONS = {
    "标量": "标量是只包含一个数值的量，不携带方向或多个坐标；损失值、学习率和温度都是常见例子。",
    "向量": "向量是一组按顺序排列的数值，既可以表示多个特征，也可以表示带方向的量。",
    "矩阵": "矩阵是按行和列组织的二维数值表，可用于表示线性变换、样本特征或参数。",
    "张量": "张量是对标量、向量和矩阵的多维推广，深度学习中的图像通常以批次、通道和空间维度组织。",
    "矩阵运算": "矩阵运算包括加法、乘法和转置等操作，必须先检查维度是否满足对应运算规则。",
    "矩阵乘法": "矩阵乘法通过左矩阵的行与右矩阵的列做内积，结果的形状由外侧两个维度决定。",
    "卷积运算": "卷积运算用局部窗口和可学习的卷积核提取邻域模式，并将输入特征映射为新的空间特征。",
    "互相关": (
        "互相关保持卷积核的原有排列，在输入上滑动并逐元素乘加；"
        "多数深度学习框架的 Conv2d 实际实现它。"
    ),
    "池化": "池化在局部窗口内进行聚合，用更少的空间位置保留主要响应并降低特征图分辨率。",
}

_QUIZ_KIND_LABELS = {
    "concept": "概念题",
    "calculation": "计算题",
    "shape_reasoning": "形状推理题",
    "code": "代码题",
    "debugging": "调试题",
    "synthesis": "综合题",
    "analysis": "分析题",
}


def _concept_label(concept_id: str) -> str:
    slug = concept_id.rsplit(".", 1)[-1]
    return _CONCEPT_LABELS.get(slug, slug.replace("-", " "))


def _clean_outcome(value: str) -> str:
    """Normalize generated prose so outcome text does not create doubled punctuation."""
    return str(value).strip().rstrip("。.!！?？")


def _lecture_sections(topic: str, outcome: str, definition_text: str, personalization: PersonalizationPolicy | None = None) -> tuple[str, ...]:
    explanation = _CONCEPT_EXPLANATIONS.get(topic, f"{topic}是本节需要掌握的核心概念。")
    derivation, example, pitfall = _lesson_details(topic)
    enrichment = _lesson_enrichment(topic)
    code_examples = _lesson_code_examples(topic)
    personalization_note = _personalization_note(personalization)
    return (
        f"学习目标：{outcome}。个性化起点：{personalization_note}完成本节后，你应能从输入约束出发解释“{topic}”，手算一个最小例子，"
        "并用代码或实验结果验证推导，而不是只复述术语。",
        f"核心概念：{explanation}。先区分对象的表示、允许的操作和输出含义，再决定使用哪条公式或 API。",
        f"证据导读：{definition_text}。阅读证据时圈出定义中的输入、变换和边界条件，后续实验必须覆盖它们。",
        f"推导骨架：{derivation} 将推导拆成可检查的小步，每一步都保留中间量，便于定位形状或数值错误。",
        f"工作示例：{example} 先写预测，再运行代码；若结果不一致，优先检查维度、参数顺序和边界处理。",
        f"易错边界：{pitfall} 这个反例提醒我们，名称相近的操作可能有不同语义，必须用输入输出对照确认。",
        f"自检与迁移：不用看资料，说明“{topic}”与相邻前置知识的一个区别；再修改一个参数，预测结果如何变化并验证。",
    )


def _lesson_blocks(topic: str, outcome: str, definition_text: str) -> tuple[LessonBlock, ...]:
    """Build a complete lesson spine for the deterministic candidate preview."""
    explanation = _CONCEPT_EXPLANATIONS.get(
        topic, f"{topic}是本节点的核心概念，必须先明确输入、变换规则和输出。"
    )
    derivation, example, pitfall = _lesson_details(topic)
    enrichment = _lesson_enrichment(topic)
    code_examples = _lesson_code_examples(topic)
    return (
        LessonBlock(
            kind="objective",
            title="学完本节你应该能够",
            body=(
                f"本节的目标是：{outcome}。学习时请不要只记住名词；你需要能说清“{topic}”"
                "接收什么输入、按什么规则处理、得到什么输出，并能在代码中验证这个过程。"
            ),
        ),
        LessonBlock(
            kind="intuition",
            title="先建立直觉",
            body=(
                f"{explanation} 可以把它想成一次受规则约束的局部计算：先观察对象的组成，"
                "再按照固定规则变换，最后检查结果是否仍符合输入与输出之间的关系。"
            ),
        ),
        LessonBlock(
            kind="definition",
            title="正式定义与边界",
            body=(
                f"{definition_text} 这一定义强调三件事：对象的表示方式、允许的操作，以及结果"
                f"应如何解释。遇到“{topic}”相关题目时，先确认这些条件，不能只凭名称套用公式。"
            ),
        ),
        LessonBlock(kind="derivation", title="按步骤推导", body=derivation),
        LessonBlock(
            kind="example",
            title="带着数值或代码走一遍",
            body=example,
            code=code_examples[0],
        ),
        LessonBlock(kind="definition", title="公式与不变量", body=enrichment[0]),
        LessonBlock(
            kind="example",
            title="代码观察与对照",
            body=enrichment[1],
            code=code_examples[1],
        ),
        LessonBlock(kind="example", title="实验前先预测", body=enrichment[2]),
        LessonBlock(kind="pitfall", title="最容易出错的地方", body=pitfall),
        LessonBlock(
            kind="summary",
            title="本节小结",
            body=(
                f"回到学习目标：{outcome}。请用一句话总结“{topic}”的输入、规则和输出；"
                "再完成下面的代码练习。若不能解释运行结果，先回看推导步骤，而不是直接修改参数。"
            ),
        ),
    )


def _lesson_details(topic: str) -> tuple[str, str, str]:
    details = {
        "标量": (
            "标量只有一个数值，不携带方向或坐标。它与向量相乘时会广播到每个分量："
            "$v' = s \\cdot v$；$s$ 的符号决定是否反向，$|s|$ 决定缩放倍数，$s=0$ 时所有分量都归零。",
            "设 $s=-2.5$、$v=[3,0,-1]$。逐项计算得到 $[-7.5,-0.0,2.5]$；长度缩放比例为 $|s|=2.5$，"
            "方向因 $s<0$ 发生反转。再用 $s=1$、$0$、$0.5$ 三个对照值，可以检查单位元、零元和缩放关系。",
            "不要把标量乘法和矩阵乘法混淆：前者只需把同一个数应用到每个元素，不要求两个矩阵满足内维相等。"
            "还要注意 Python 列表不能直接做数值缩放，需显式遍历或转换为 NumPy 数组。",
        ),
        "向量": (
            "把向量写成按顺序排列的分量，例如 $v=[v_1,v_2,v_3]$。相加时对应位置相加；"
            "点积时对应位置相乘后求和，因此两个向量必须有相同长度。",
            "令 $a=[1,2,3]$，$b=[4,0,-1]$。$a+b=[5,2,2]$；"
            "$a \\cdot b = 1\\times4 + 2\\times0 + 3\\times(-1) = 1$。",
            "向量的逗号顺序就是维度顺序。把行向量、列向量或不同长度的向量直接相加，会得到错误或不符合预期的广播。",
        ),
        "矩阵": (
            "矩阵用行和列组织数据。$A$ 的形状记为 $(m,n)$：$m$ 表示行数，$n$ 表示列数。"
            "逐元素运算需要对应位置存在；矩阵乘法还要求左矩阵列数等于右矩阵行数。",
            "$A=\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}$，$B=\\begin{bmatrix}5&6\\\\7&8\\end{bmatrix}$。$A+B$ 逐元素相加；"
            "$A \\cdot B$ 的左上角是 $1\\times5 + 2\\times7 = 19$。",
            "`*` 在 NumPy 中通常表示逐元素乘法，`@` 才表示矩阵乘法。"
            "先打印 shape，再决定用哪个运算符。",
        ),
        "张量": (
            "张量把标量、向量和矩阵推广到更多维度。深度学习中一批彩色图像常写成 "
            "$(batch,channel,height,width)$，"
            "每个轴都表达不同含义，不能因为元素个数相同就随意交换轴。",
            "一张 RGB 图像的形状可以是 $(3,32,32)$：3 个通道，每个通道 $32\\times32$。"
            "加入 8 张图像的批次后，形状变为 $(8,3,32,32)$。",
            "最常见的错误是把 HWC 图像直接传给要求 NCHW 的 PyTorch 层。"
            "尺寸看似正确，但通道轴含义已经错位。",
        ),
        "卷积运算": (
            "二维卷积层在输入特征图上滑动一个小窗口。每个位置把窗口元素与卷积核逐项相乘并求和，"
            "得到输出特征图的一个值。padding 决定边界如何补齐，stride 决定窗口每次移动几格。",
            "输入高度 $H=5$，卷积核 $K=3$，padding $P=1$，stride $S=1$ 时，输出高度为 "
            "$\\left\\lfloor\\frac{H+2P-K}{S}\\right\\rfloor+1"
            "$=\\left\\lfloor\\frac{5+2-3}{1}\\right\\rfloor+1=5$。",
            "不要只看 Conv2d 的 `out_channels`。输出空间尺寸同时受 "
            "kernel_size、stride、padding、dilation 影响；"
            "还要确认输入的通道数与 in_channels 一致。",
        ),
    }
    return details.get(
        topic,
        (
            f"先写出“{topic}”的输入类型和输出类型，再把规则拆成逐步操作。每一步都应能用一个小例子验证。",
            f"选择一个最小输入，手工完成一次“{topic}”操作；再用代码打印输入、中间过程和输出，逐项比对预期结果。",
            f"不要跳过输入约束。多数“{topic}”错误来自形状、类型或前置条件不满足，而不是公式本身。",
        ),
    )


def _practice_exercise(topic: str, outcome: str) -> PracticeExercise:
    exercises = {
        "标量": PracticeExercise(
            task=(
                "完成一个标量缩放实验：用标量 s 逐项缩放向量 v，验证输出长度、方向和长度比例。"
                "再将 s 改为 1、0、-1 和 0.5 做四组对照，打印结果并用断言验证单位元、零元和反向缩放。"
                f"最后用一句注释说明实验如何支持“{outcome}”。"
            ),
            starter_code=(
                "s = -2.5\n"
                "v = [3, 0, -1]\n\n"
                "def scale_vector(scalar, vector):\n"
                "    # TODO 1: 将 scalar 乘到 vector 的每个元素上\n"
                "    return []\n\n"
                "scaled = scale_vector(s, v)\n"
                "print('baseline:', scaled)\n"
                "assert len(scaled) == 3\n"
                "assert scaled[0] == -7.5\n\n"
                "# TODO 2: 完成四组标量的对照实验\n"
                "scalars = [1, 0, -1, 0.5]\n"
                "report = [(value, scale_vector(value, v)) for value in scalars]\n"
                "print('comparison:', report)\n"
                "assert scale_vector(1, v) == v\n"
                "assert scale_vector(0, v) == [0, 0, 0]\n"
                "assert scale_vector(-1, v) == [-3, 0, 1]\n"
            ),
            expected_output=(
                "baseline: [-7.5, -0.0, 2.5]；comparison 应显示 s=1 保持原向量、s=0 全部归零、"
                "s=-1 反向、s=0.5 缩短一半。"
            ),
            checks=(
                "scale_vector 逐元素计算且结果包含 3 个元素",
                "基线输出为 [-7.5, -0.0, 2.5]，并验证长度不变",
                "完成 s=1、0、-1、0.5 四组对照并打印 report",
                "保留 assert 验证单位元、零元和反向缩放",
            ),
            required_tokens=("scale_vector", "scalar", "vector", "scaled", "report", "print"),
        ),
        "矩阵": PracticeExercise(
            task=(
                "用 NumPy 分别计算逐元素乘法和矩阵乘法，打印两个结果并观察它们为什么不同。"
                f"你的代码需要支持学习目标：{outcome}。"
            ),
            starter_code=(
                "import numpy as np\n\n"
                "a = np.array([[1, 2], [3, 4]])\n"
                "b = np.array([[5, 6], [7, 8]])\n\n"
                "# TODO: 分别完成逐元素乘法与矩阵乘法\n"
                "elementwise = None\n"
                "matmul = None\n\n"
                "print(elementwise)\n"
                "print(matmul)\n"
            ),
            expected_output="逐元素乘法 [[5, 12], [21, 32]]；矩阵乘法 [[19, 22], [43, 50]]",
            checks=(
                "使用 np.array 创建输入",
                "同时输出 elementwise 与 matmul",
                "矩阵乘法使用 @ 或 np.matmul",
            ),
            required_tokens=("np.array", "elementwise", "matmul", "print"),
        ),
        "卷积运算": PracticeExercise(
            task=(
                "完成一个可复现实验：先补全 $3\\times3$ 输入与 $2\\times2$ 卷积核的单位置互相关，"
                "再实现输出尺寸公式并比较 stride=1/2、padding=0/1 四组参数。"
                "最后用断言验证手算结果，说明该实验如何对应深度学习框架中的 Conv2d。"
            ),
            starter_code=(
                "import numpy as np\n\n"
                "image = np.array([[1, 2, 0], [0, 1, 3], [2, 2, 1]])\n"
                "kernel = np.array([[1, 0], [0, -1]])\n"
                "window = image[:2, :2]\n\n"
                "# TODO 1: 计算 window 与 kernel 的逐元素乘积之和\n"
                "output = None\n\n"
                "def output_size(size, kernel_size, padding, stride):\n"
                "    # TODO 2: 补全输出尺寸公式\n"
                "    return None\n\n"
                "# TODO 3: 完成四组参数的对照实验\n"
                "cases = [(5, 3, 1, 1), (5, 3, 1, 2), (5, 3, 0, 1), (5, 3, 0, 2)]\n"
                "shape_report = []\n"
                "for size, k, p, s in cases:\n"
                "    shape_report.append((s, p, output_size(size, k, p, s)))\n\n"
                "print('single_position:', output)\n"
                "print('shape_report:', shape_report)\n"
                "assert output == 0\n"
                "assert len(shape_report) == 4\n"
            ),
            expected_output=(
                "single_position: 0；shape_report 应包含 (stride, padding, output_size) 四组记录，"
                "其中 (1,1) 输出尺寸为 5、(2,1) 为 3、(1,0) 为 3、(2,0) 为 2。"
            ),
            checks=(
                "保留 image、kernel 与 window，并使用逐元素乘法后求和",
                "output_size 使用 $\\left\\lfloor\\frac{size+2\\cdot padding-kernel\\_size}{stride}\\right\\rfloor+1$",
                "四组参数都生成 shape_report，且 stride=2 的输出更小",
                "保留 assert 验证单位置结果和实验记录数量",
            ),
            required_tokens=(
                "image", "kernel", "window", "output", "output_size", "shape_report", "print"
            ),
        ),
        "互相关": PracticeExercise(
            task=(
                "用一个非对称 2×2 kernel 对输入窗口分别执行互相关和 kernel 翻转后的数学卷积。"
                "打印两种结果，再用一个对称 kernel 做对照，解释为什么 Conv2d 通常实现的是互相关。"
            ),
            starter_code=(
                "import numpy as np\n\n"
                "window = np.array([[2, 1], [0, 3]])\n"
                "kernel = np.array([[1, 2], [3, 4]])\n\n"
                "# TODO 1: 保持 kernel 原方向，计算互相关\n"
                "cross_correlation = None\n"
                "# TODO 2: 上下、左右翻转 kernel，再计算数学卷积\n"
                "convolution = None\n"
                "symmetric = np.array([[1, 0], [0, 1]])\n"
                "# TODO 3: 验证对称 kernel 翻转前后结果\n"
                "symmetric_check = None\n\n"
                "print('cross_correlation:', cross_correlation)\n"
                "print('convolution:', convolution)\n"
                "print('symmetric_check:', symmetric_check)\n"
            ),
            expected_output=(
                "互相关为 16，翻转 kernel 后的数学卷积为 14；对称 kernel 的翻转前后结果相同。"
            ),
            checks=(
                "保留 window 与非对称 kernel，并完成逐元素乘加",
                "convolution 使用 np.flip(kernel) 后再计算",
                "打印三组结果并说明互相关与数学卷积的差异",
            ),
            required_tokens=(
                "window", "kernel", "cross_correlation", "convolution", "np.flip", "print"
            ),
        ),
    }
    return exercises.get(
        topic,
        PracticeExercise(
            task=(
                f"为“{topic}”写一个最小 Python 示例：创建一个输入，完成一次核心变换并打印结果。"
                f"用注释说明该结果如何验证学习目标：{outcome}。"
            ),
            starter_code=(
                "# TODO: 创建一个最小输入并完成本节的核心变换\n"
                "result = None\n"
                "print(result)\n"
            ),
            expected_output="打印一个可解释的结果，并在注释中说明输入、操作和输出。",
            checks=("定义输入", "计算 result", "打印 result 并解释"),
            required_tokens=("result", "print"),
        ),
    )


def _practical_steps(topic: str, outcome: str, code_text: str, personalization: PersonalizationPolicy | None = None) -> tuple[str, ...]:
    policy_note = _personalization_note(personalization)
    steps = (
        f"问题定义：把“{topic}”要解释的现象写成一个可验证问题，并明确本次要支持的学习目标“{outcome}”。",
        f"输入检查：记录输入的类型、形状、取值范围和关键参数；先预测输出，再开始编码。",
        f"基线实现：围绕“{topic}”完成一个最小可运行示例，打印输入、中间值和最终结果。",
        "结果核对：把运行结果与手工计算或公式逐项对照，标记第一个出现差异的位置。",
        "单变量实验：一次只修改一个参数，保留其他输入不变，比较输出形状、数值和计算成本。",
        "边界实验：使用最小尺寸、全零输入或不满足约束的输入，记录程序行为并解释原因。",
        f"迁移验证：把实现改写到一个稍有变化的场景，确认规则仍能支持“{outcome}”。",
        f"结论记录：用三句话写清输入、变换规则、输出变化，并保留可复现的参数表。参考证据：{code_text}",
    )
    if policy_note:
        steps = (f"个性化起点：{policy_note}", *steps)
    if personalization is not None and personalization.review_intensity >= 3:
        steps = (*steps, "间隔复习：完成练习后，隔一天不看讲义重做基线题，再用错题原因表复盘。")
    return steps


def _personalization_note(personalization: PersonalizationPolicy | None) -> str:
    if personalization is None:
        return ""
    order_labels = {"intuition": "直觉", "formula": "公式", "code": "代码", "diagram": "图示", "debug": "调试"}
    order = " → ".join(order_labels.get(item, item) for item in personalization.explanation_order_hint)
    if personalization.scaffolding_level >= 3:
        level = "你当前需要更细的分步支架，先完成小例子再进入综合题。"
    elif personalization.scaffolding_level == 2:
        level = "你已有部分基础，本节采用示例与公式交替推进。"
    else:
        level = "你对相关知识已有较好掌握，本节压缩基础讲解，增加迁移挑战。"
    presentation = "、".join(personalization.presentation_preferences) or "分步讲解"
    debug = "重点检查概念混淆和计算过程。" if personalization.debugging_emphasis >= 3 else "遇到错误时记录输入、规则和输出的第一个差异。"
    return f"{level}讲解顺序为 {order}，呈现方式偏好：{presentation}。{debug}"


def _quiz_instructions(personalization: PersonalizationPolicy) -> str:
    difficulty = personalization.exercise_difficulty_distribution
    return (
        f"本次小测按你的学习证据安排：基础题 {difficulty[0]} 道、进阶题 {difficulty[1]} 道、挑战题 {difficulty[2]} 道。"
        f"请按“{' → '.join(personalization.explanation_order_hint)}”回想解题过程；答错后先记录原因，再进行第 {personalization.review_intensity} 轮复习。"
    )


def _lesson_code_examples(topic: str) -> tuple[str, str]:
    """Provide runnable teaching snippets before the separate TODO exercises."""
    examples = {
        "标量": (
            "s = -2.5\nv = [3, 0, -1]\nscaled = [s * value for value in v]\nprint(scaled)",
            "for s in (1, 0, -1, 0.5):\n    result = [s * value for value in v]\n    print(f's={s}: {result}')",
        ),
        "向量": (
            "a = [1, 2, 3]\nb = [4, 0, -1]\nsum_vector = [x + y for x, y in zip(a, b)]\ndot = sum(x * y for x, y in zip(a, b))\nprint(sum_vector, dot)",
            "import numpy as np\na = np.array([1, 2, 3])\nb = np.array([4, 0, -1])\nprint('dot:', a @ b)\nprint('norms:', np.linalg.norm(a), np.linalg.norm(b))",
        ),
        "矩阵": (
            "import numpy as np\nA = np.array([[1, 2], [3, 4]])\nB = np.array([[5, 6], [7, 8]])\nprint('elementwise:', A * B)\nprint('matmul:', A @ B)",
            "import numpy as np\nX = np.array([[1., 2.], [3., 4.]])\nW = np.array([[1., 0., -1.], [0.5, 2., 1.]])\nY = X @ W\nprint('X shape:', X.shape, 'W shape:', W.shape, 'Y shape:', Y.shape)",
        ),
        "张量": (
            "import numpy as np\nimage = np.zeros((32, 32, 3))\nbatch = image[None, ...]\nprint('NHWC:', batch.shape)",
            "import numpy as np\nnhwc = np.zeros((8, 32, 32, 3))\nnchw = np.transpose(nhwc, (0, 3, 1, 2))\nprint('NHWC -> NCHW:', nhwc.shape, '->', nchw.shape)",
        ),
        "卷积运算": (
            "import numpy as np\nwindow = np.array([[1., 2.], [3., 4.]])\nkernel = np.array([[1., 0.], [0., -1.]])\nvalue = float((window * kernel).sum())\nprint('single output:', value)",
            "import torch\nfor stride, padding in ((1, 0), (2, 0), (1, 1)):\n    layer = torch.nn.Conv2d(1, 2, kernel_size=3, stride=stride, padding=padding)\n    y = layer(torch.zeros(1, 1, 5, 5))\n    print({'stride': stride, 'padding': padding, 'shape': tuple(y.shape)})",
        ),
        "互相关": (
            "import numpy as np\nwindow = np.array([[2., 1.], [0., 3.]])\nkernel = np.array([[1., 2.], [3., 4.]])\nprint('cross-correlation:', float((window * kernel).sum()))",
            "import numpy as np\nwindow = np.array([[2., 1.], [0., 3.]])\nkernel = np.array([[1., 2.], [3., 4.]])\nprint('cross:', (window * kernel).sum())\nprint('convolution:', (window * np.flip(kernel)).sum())",
        ),
    }
    return examples.get(
        topic,
        (
            "values = [1, 2, 3]\nresult = values\nprint('input:', values)\nprint('result:', result)",
            "values = [1, 2, 3]\nfor variant in (values, list(reversed(values))):\n    print('variant:', variant)",
        ),
    )


def _project_exercise(topic: str, outcome: str) -> PracticeExercise:
    """Build a second, project-shaped exercise for every concept in the course graph."""
    exercises = {
        "标量": PracticeExercise(
            task=(
                "项目任务：实现一个批量特征缩放器。输入多条样本和缩放配置，输出缩放后的数据、"
                "每条样本的 L2 长度以及异常输入报告；要求用函数封装并通过汇总指标验证结果。"
                f"最终在 README 中说明它如何支撑“{outcome}”。"
            ),
            starter_code=(
                "records = [[3, 0, -1], [1, 2, 2], [0, 0, 0]]\n"
                "scales = [1, 0.5, -1]\n\n"
                "def scale_batch(records, scales):\n"
                "    # TODO: 校验长度并返回逐样本缩放结果\n"
                "    return []\n\n"
                "def l2_norm(vector):\n"
                "    # TODO: 计算向量的 L2 长度\n"
                "    return 0\n\n"
                "scaled = scale_batch(records, scales)\n"
                "norms = [l2_norm(row) for row in scaled]\n"
                "print('scaled:', scaled)\n"
                "print('norms:', norms)\n"
                "assert len(scaled) == len(records)\n"
                "assert all(len(row) == 3 for row in scaled)\n"
            ),
            expected_output="scaled 保留 3 条样本且每条长度为 3；norms 能反映缩放绝对值对向量长度的影响。",
            checks=("实现 scale_batch 并逐样本使用对应 scalar", "实现 l2_norm 并输出 norms", "处理 records/scales 长度不一致", "保留结果数量与形状断言"),
            required_tokens=("records", "scales", "scale_batch", "l2_norm", "scaled", "norms", "assert"),
        ),
        "向量": PracticeExercise(
            task=(
                "项目任务：实现一个小型向量检索器。给定候选向量和查询向量，计算点积与余弦相似度，"
                "返回 Top-K 结果并解释排序依据。"
                f"在结论中连接学习目标“{outcome}”。"
            ),
            starter_code=(
                "import math\n\n"
                "query = [1, 2, 0]\n"
                "candidates = {'doc-a': [1, 1, 0], 'doc-b': [0, 2, 2], 'doc-c': [2, 4, 0]}\n\n"
                "def dot(a, b):\n"
                "    # TODO: 计算点积并校验维度\n"
                "    return 0\n\n"
                "def cosine(a, b):\n"
                "    # TODO: 用 dot 和向量长度计算余弦相似度\n"
                "    return 0\n\n"
                "scores = sorted(((name, cosine(query, vector)) for name, vector in candidates.items()), key=lambda item: item[1], reverse=True)\n"
                "print('ranking:', scores)\n"
                "assert scores[0][0] == 'doc-c'\n"
            ),
            expected_output="ranking 按余弦相似度降序排列，方向相同但长度不同的 doc-c 应排在前面。",
            checks=("实现 dot 的维度检查", "实现 cosine 并处理零向量", "返回排序后的 name/score", "保留 Top-1 断言"),
            required_tokens=("query", "candidates", "dot", "cosine", "ranking", "sorted", "assert"),
        ),
        "矩阵": PracticeExercise(
            task=(
                "项目任务：搭建一个两层线性变换流水线。对一批输入先执行矩阵乘法，再加偏置，"
                "输出预测并比较交换层顺序后的差异；要求检查矩阵形状并记录每层中间结果。"
                f"说明这对“{outcome}”的工程意义。"
            ),
            starter_code=(
                "import numpy as np\n\n"
                "x = np.array([[1., 2.], [3., 4.], [5., 6.]])\n"
                "w1 = np.array([[1., 0., -1.], [0.5, 2., 1.]])\n"
                "w2 = np.array([[1.], [-1.], [0.5]])\n"
                "bias = np.array([0.25])\n\n"
                "def linear(x, weight, bias=None):\n"
                "    # TODO: 检查内维并完成 x @ weight + bias\n"
                "    return None\n\n"
                "hidden = linear(x, w1)\n"
                "prediction = linear(hidden, w2, bias)\n"
                "swapped = linear(linear(x, w2), w1) if False else None\n"
                "print('hidden_shape:', hidden.shape)\n"
                "print('prediction:', prediction)\n"
                "assert prediction.shape == (3, 1)\n"
            ),
            expected_output="hidden_shape 为 (3, 3)，prediction 为 (3, 1)；交换层顺序不能随意替代原流水线。",
            checks=("linear 使用 @ 并检查 shape", "保留 hidden 中间结果", "输出 prediction 与形状", "解释层顺序和偏置的作用"),
            required_tokens=("np.array", "linear", "hidden", "prediction", "shape", "assert"),
        ),
        "张量": PracticeExercise(
            task=(
                "项目任务：实现一个批量图像张量预处理器。输入 NHWC 图像批次，转换为 NCHW，"
                "完成按通道标准化并输出每个通道的统计量；要求显式记录轴语义，避免静默转置错误。"
                f"用结果解释“{outcome}”。"
            ),
            starter_code=(
                "import numpy as np\n\n"
                "images = np.arange(2 * 4 * 4 * 3, dtype=float).reshape(2, 4, 4, 3)\n\n"
                "def to_nchw(batch):\n"
                "    # TODO: 将 NHWC 转为 NCHW 并检查 batch/channel 轴\n"
                "    return None\n\n"
                "def normalize_channels(batch):\n"
                "    # TODO: 按 NCHW 的空间维计算均值和标准差\n"
                "    return None, None, None\n\n"
                "nchw = to_nchw(images)\n"
                "normalized, mean, std = normalize_channels(nchw)\n"
                "print('shape:', nchw.shape)\n"
                "print('mean:', mean)\n"
                "print('std:', std)\n"
                "assert nchw.shape == (2, 3, 4, 4)\n"
            ),
            expected_output="shape 为 (2, 3, 4, 4)，mean/std 各有 3 个通道统计值，normalized 保持同一形状。",
            checks=("实现 NHWC 到 NCHW 的轴变换", "统计量只沿空间维计算", "输出 normalized/mean/std", "保留轴形状断言"),
            required_tokens=("images", "to_nchw", "normalize_channels", "normalized", "mean", "std", "shape"),
        ),
        "卷积运算": PracticeExercise(
            task=(
                "项目任务：实现一个可测试的二维卷积层原型。支持 padding/stride，返回输出特征图，"
                "并对多组参数生成 shape 报告；要求用单元断言验证边界尺寸和一个已知数值。"
                f"将实现限制与“{outcome}”关联起来。"
            ),
            starter_code=(
                "import numpy as np\n\n"
                "image = np.arange(25, dtype=float).reshape(5, 5)\n"
                "kernel = np.array([[1., 0., -1.], [1., 0., -1.], [1., 0., -1.]])\n\n"
                "def conv2d(image, kernel, padding=0, stride=1):\n"
                "    # TODO: padding 后按 stride 滑窗并完成逐元素乘加\n"
                "    return None\n\n"
                "def shape_report(image, kernel):\n"
                "    # TODO: 记录四组 padding/stride 的输出 shape\n"
                "    return {}\n\n"
                "output = conv2d(image, kernel, padding=1, stride=1)\n"
                "report = shape_report(image, kernel)\n"
                "print('output_shape:', output.shape)\n"
                "print('report:', report)\n"
                "assert output.shape == (5, 5)\n"
            ),
            expected_output="output_shape 为 (5, 5)，report 至少包含 (padding, stride) 四组输出尺寸。",
            checks=("实现 padding/stride 滑窗", "使用 kernel 与窗口逐元素乘加", "生成 report 并覆盖四组参数", "保留输出 shape 断言"),
            required_tokens=("image", "kernel", "conv2d", "padding", "stride", "shape_report", "report"),
        ),
        "互相关": PracticeExercise(
            task=(
                "项目任务：实现一个模板匹配器。对二维特征图滑动非对称模板，返回响应图、最高响应坐标，"
                "并对比翻转模板后的数学卷积结果；要求输出可解释的排序/定位结果。"
                f"最后说明它如何验证“{outcome}”。"
            ),
            starter_code=(
                "import numpy as np\n\n"
                "feature_map = np.array([[1., 2., 0., 1.], [0., 3., 1., 0.], [2., 1., 4., 2.], [0., 1., 2., 3.]])\n"
                "template = np.array([[1., 2.], [0., -1.]])\n\n"
                "def response_map(feature_map, template):\n"
                "    # TODO: 滑窗计算互相关响应图\n"
                "    return None\n\n"
                "cross = response_map(feature_map, template)\n"
                "convolution = response_map(feature_map, np.flip(template))\n"
                "best = np.unravel_index(np.argmax(cross), cross.shape)\n"
                "print('cross_shape:', cross.shape)\n"
                "print('best_match:', best, cross[best])\n"
                "print('convolution_max:', convolution.max())\n"
                "assert cross.shape == (3, 3)\n"
            ),
            expected_output="cross_shape 为 (3, 3)，best_match 给出响应最高的窗口坐标，并可与翻转模板结果比较。",
            checks=("实现滑窗 response_map", "使用 np.flip 生成数学卷积对照", "输出 best_match 坐标和响应", "保留响应图形状断言"),
            required_tokens=("feature_map", "template", "response_map", "cross", "convolution", "np.flip", "argmax"),
        ),
    }
    return exercises.get(
        topic,
        PracticeExercise(
            task=(
                f"项目任务：围绕“{topic}”实现一个可复用的小型数据处理流水线，包含输入校验、核心变换、"
                f"结果指标和边界报告，并用项目日志说明它如何支撑“{outcome}”。"
            ),
            starter_code=(
                "records = []\n\n"
                "def validate_records(records):\n"
                "    # TODO: 校验输入记录并报告问题\n"
                "    return True\n\n"
                "def transform(records):\n"
                "    # TODO: 完成当前知识点的核心变换\n"
                "    return []\n\n"
                "assert validate_records(records)\n"
                "result = transform(records)\n"
                "print('result:', result)\n"
            ),
            expected_output="输出包含经过校验的 result，以及对边界输入的可解释处理结果。",
            checks=("实现 validate_records", "实现 transform", "记录输入问题或边界情况", "打印 result 并解释指标"),
            required_tokens=("records", "validate_records", "transform", "result", "assert", "print"),
        ),
    )


def _lesson_enrichment(topic: str) -> tuple[str, str, str]:
    details = {
        "标量": (
            "标量缩放的核心公式是 $v'=s\\cdot v$。三个不变量可以用来快速验算：输出长度与输入相同；"
            "$s=1$ 时输出不变；$s=0$ 时输出全为零。若 $s<0$，向量方向反转但各分量绝对值按 $|s|$ 缩放。",
            "在 Python 中列表需要显式遍历；在 NumPy 中可直接写 `s * np.array(v)`。请同时打印原向量、"
            "缩放结果和 `np.linalg.norm` 的长度比例，确认代码结果与公式一致，而不是只看一个元素。",
            "实验前写下四个预测：$s=1$、$s=0$、$s=-1$、$s=0.5$ 分别会发生什么。运行后把预测、实际输出、"
            "方向变化和长度比例整理成表格，再用一句话说明哪条规律被验证或推翻。",
        ),
        "向量": (
            "向量加法满足逐分量规则，点积满足 $a\\cdot b=\\sum_i a_i b_i$。点积为零表示正交，交换两个向量不改变结果；"
            "但逐元素除法与点积不是同一个操作，必须先明确目标输出是标量还是向量。",
            "用 NumPy 分别打印 `a + b`、`a * b` 和 `a @ b`，并标注每个结果的 shape。通过同一组输入观察："
            "逐元素运算保留形状，点积会把对应分量乘积求和成一个标量。",
            "实验前预测 b 改成全零、与 a 平行或与 a 垂直时点积的变化，再用三组输入验证几何解释。",
        ),
        "矩阵": (
            "矩阵乘法的形状规则是 $(m,n) \\cdot (n,k) \\rightarrow (m,k)$，每个输出元素是左矩阵一行与右矩阵一列的内积。"
            "逐元素乘法不改变形状，不能用 * 代替 @。",
            "为同一对矩阵分别计算 `A * B` 与 `A @ B`，逐项解释左上角元素的来源，并用 shape 检查维度约束。"
            "再交换 A、B，观察结果是否相同，以验证矩阵乘法通常不满足交换律。",
            "实验前预测转置、交换顺序和单位矩阵会如何影响结果；运行后保留中间乘积，定位任何不一致的步骤。",
        ),
        "张量": (
            "张量的每个轴都有语义。图像常用 NCHW 表示 $(batch, channel, height, width)$，改变轴顺序不会改变元素总数，"
            "但会改变算子的解释。卷积层还要求输入 channel 与 in_channels 对齐。",
            "构造一个 $(2,3,4,4)$ 的张量，分别沿 batch、channel 和空间轴求均值并打印 shape，观察每一步保留的语义。"
            "再用 permute 交换轴，比较同一层接收前后的 shape。",
            "实验前预测 NCHW 与 NHWC 互换后哪一维会触发错误；用断言和异常信息记录框架真正检查的是哪个约束。",
        ),
        "卷积运算": (
            "二维卷积输出尺寸为 $\\left\\lfloor\\frac{H+2P-K}{S}\\right\\rfloor+1$，通道和空间尺寸是两套独立约束。参数量为"
            "$K_h\\cdot K_w\\cdot C_{in}\\cdot C_{out}$（若有 bias 再加 $C_{out}$），不能只根据输出高宽判断模型大小。",
            "用同一输入依次改变 stride、padding 和 out_channels，分别打印输出 shape 与参数量。"
            "将手算公式、框架结果和参数量放在一行对照，确认空间下采样与通道扩展是不同现象。",
            "实验前预测 stride=2、padding=0 和 kernel 变大时的输出尺寸；运行后解释每个差异来自公式中的哪一项。",
        ),
    }
    return details.get(topic, (
        f"为“{topic}”写出输入、核心规则、输出和至少一个不变量；不变量应能在代码中用断言验证。",
        f"用最小输入实现“{topic}”，同时打印输入、关键中间量、输出和 shape，比较手算结果与代码结果。",
        f"实验前预测一个参数变化对“{topic}”的影响，再用基线、对照和边界三组结果验证预测。",
    ))


def _notebook_tasks(topic: str, outcome: str, code_text: str) -> tuple[str, ...]:
    return (
        f"Notebook 0 · 基线：实现 {topic} 的最小例子，先写下预测输出，再运行并保存实际输出。",
        "Notebook 1 · 参数扫描：固定输入，只改变一个核心参数，至少记录三组参数与对应结果。",
        "Notebook 2 · 边界与反例：测试全零、最小尺寸或不匹配形状，解释报错或退化输出。",
        "Notebook 3 · 对照表：将手算结果、代码结果和差异原因整理成三列表格。",
        f"Notebook 4 · 迁移：把实验结论连接回学习目标“{outcome}”，补充一个真实应用场景。",
        f"参考代码片段（候选证据）：{code_text}",
    )


def _experiment_protocol(topic: str) -> tuple[str, ...]:
    specific = {
        "标量": (
            "基线：固定向量 [3, 0, -1] 与标量 -2.5，预测每个分量和长度比例。",
            "单位元：将标量改为 1，验证输出与原向量逐项相同。",
            "零元与反向：分别使用 0、-1、0.5，记录归零、反向和长度缩放现象。",
            "边界：测试空向量、长度不一致的输入和 Python 列表与 NumPy 数组的差异。",
            "结论：用一张表说明标量的符号、绝对值如何影响向量的方向与长度。",
        ),
        "卷积运算": (
            "基线：输入 $5\\times5$，`kernel=3`、`padding=1`、`stride=1`；手算并记录输出尺寸。",
            "变量一：只将 stride 改为 2，比较空间尺寸变化，解释下采样来源。",
            "变量二：只将 padding 改为 0，观察边界信息减少后的输出差异。",
            "边界：使用 kernel 大于输入的组合，记录框架报错并说明约束。",
            "结论：用输出 shape 和公式逐项验证 Conv2d 的参数含义。",
        ),
        "互相关": (
            "基线：用非对称 $2\\times2$ kernel 完成一次滑窗逐元素乘加。",
            "变量：将 kernel 上下、左右翻转，分别记录互相关与数学卷积结果。",
            "对照：使用对称 kernel，确认翻转后结果可能相同的条件。",
            "边界：改变 stride，说明采样位置减少如何影响输出覆盖范围。",
            "结论：用一个具体数值例子说明深度学习 Conv2d 为什么称为互相关。",
        ),
    }
    return specific.get(topic, (
        f"基线：为 {topic} 选择最小输入，写下预期输出与判断依据。",
        "单变量：只修改一个参数或输入维度，记录输出变化。",
        "边界：使用最小、最大或不满足约束的输入，记录异常行为。",
        "对照：把手工推导、代码结果和证据片段放在同一张表中。",
        f"结论：用实验结果回答 {topic} 在什么条件下成立，以及它如何服务于本节目标。",
    ))


_PREVIEW_QUIZ_BANK: dict[str, tuple[tuple[str, tuple[str, ...], int], ...]] = {
    "标量": (
        ("下列哪一项是标量？", ("图像的高和宽", "模型训练中的学习率 $0.01$", "二维坐标 $(2,3)$"), 1),
        ("标量与向量的主要区别是什么？", ("标量只有一个数值，不携带方向或多个分量", "标量一定比向量大", "标量只能是正数"), 0),
        ("向量 $v=[2,-1]$ 乘以标量 $3$，结果是？", ("$[6,-3]$", "$[5,2]$", "$[2,-1,3]$"), 0),
        ("向量 $v=[2,-1]$ 乘以标量 $0$，结果是？", ("$[2,-1]$", "$[0,0]$", "$[-2,1]$"), 1),
        ("NumPy 中 `np.array([1, 2]) * 4` 的结果是？", ("[1, 2, 1, 2, 1, 2, 1, 2]", "[4, 8]", "6"), 1),
        ("训练代码中 `loss.item()` 通常用于得到什么？", ("一个可记录的标量损失值", "损失函数的完整代码", "一个新的特征向量"), 0),
        ("若 `scale = [0.5]`，却想用它缩放向量 `v`，更合适的写法是？", ("把 `scale` 转成一个数值标量后再与 `v` 相乘", "把 `v` 转成字符串", "删除 `v` 的所有元素"), 0),
        ("下列哪个任务最适合用标量表示？", ("记录一次预测的置信度", "表示一张 RGB 图像", "保存一批样本的特征矩阵"), 0),
    ),
    "向量": (
        ("二维向量 $v=[3,4]$ 最恰当的解释是？", ("它表示两个有顺序的分量，可描述位移或两个特征", "它是一个只有大小、没有分量的数", "它是一张二维表格"), 0),
        ("点 $(2,1)$ 与向量 $[2,1]$ 的区别是？", ("二者完全等价，任何场景都可替换", "点表示位置，向量表示位移或方向和大小", "向量只能有一个分量"), 1),
        ("$a=[1,2,3]$，$b=[4,5,6]$，$a+b$ 的结果是？", ("$[5,7,9]$", "$[4,10,18]$", "$[1,2,3,4,5,6]$"), 0),
        ("长度为 3 的向量与长度为 2 的向量能直接逐元素相加吗？", ("能，短向量会自动补零", "不能，逐元素加法要求对应分量数量一致", "能，结果一定是长度为 5 的向量"), 1),
        ("NumPy 中 `np.array([1, 2]) * 3` 的结果是？", ("[1, 2, 1, 2, 1, 2]", "[3, 6]", "5"), 1),
        ("`np.dot([1, 2], [3, 4])` 的结果是？", ("[3, 8]", "[4, 6]", "11"), 2),
        ("Python 列表 `a = [1, 2]` 与 `b = [3, 4]` 直接执行 `a + b`，为什么不是向量加法？", ("列表的 `+` 会拼接，应用 NumPy 数组再做逐元素加法", "Python 会自动计算内积", "因为向量不能包含整数"), 0),
        ("下列哪个场景最适合用向量表示？", ("用一个数记录当前学习率", "用 [身高, 体重, 年龄] 表示一个样本的三个特征", "用行和列组织整批样本"), 1),
    ),
    "矩阵": (
        ("矩阵最恰当的表示是什么？", ("按行和列组织的二维数值表", "只能包含一个数值的变量", "没有维度限制的一段文本"), 0),
        ("矩阵 A 的形状为 2×3，表示什么？", ("2 个元素组成 3 个矩阵", "2 行 3 列", "3 行 2 列"), 1),
        ("两个同形状矩阵做逐元素加法时，必须满足什么条件？", ("行数和列数分别相等", "只要元素总数相等", "只要行数相等即可"), 0),
        ("矩阵转置会怎样变化？", ("元素值全部变成相反数", "行列互换", "矩阵一定变成单位矩阵"), 1),
        ("在 NumPy 中，矩阵乘法通常使用哪个运算符？", ("`@`", "`//`", "`%`"), 0),
        ("矩阵的形状主要用于检查什么？", ("输入、运算规则与输出是否匹配", "变量名是否足够长", "代码是否使用了循环"), 0),
        ("下列哪项可以表示一批样本的特征？", ("一个单独的标量", "按行排列样本、按列排列特征的矩阵", "一个没有数值的字符串"), 1),
        ("矩阵运算前最应该先做什么？", ("确认矩阵的行列维度和运算类型", "删除所有零元素", "把矩阵转换成文字"), 0),
    ),
    "矩阵运算": (
        ("矩阵运算前最重要的检查是什么？", ("维度和运算类型是否匹配", "矩阵变量名是否相同", "是否所有元素都为正数"), 0),
        ("同形状矩阵 A、B 的逐元素加法结果是什么？", ("对应位置元素分别相加", "A 的行乘 B 的列", "把 A、B 的元素拼成一行"), 0),
        ("矩阵转置的结果是？", ("行列互换", "每个元素平方", "只保留主对角线"), 0),
        ("NumPy 中 `A * B`（同形状）通常表示什么？", ("逐元素乘法", "矩阵乘法", "矩阵求逆"), 0),
        ("NumPy 中 `A @ B` 表示什么？", ("矩阵乘法", "逐元素比较", "转置"), 0),
        ("若 A 是 2×3，B 是 3×4，A @ B 的形状是？", ("2×4", "3×3", "4×2"), 0),
        ("形状不匹配的矩阵乘法通常会怎样？", ("应被拒绝或报维度错误", "自动补零后永远成功", "结果必然是标量"), 0),
        ("选择矩阵操作时，应依据什么？", ("任务语义与维度约束", "只依据变量名长度", "只依据矩阵元素的颜色"), 0),
    ),
    "矩阵乘法": (
        (
            "矩阵 A（m×n）与 B（p×q）可以相乘的条件是什么？",
            ("n = p，左矩阵列数等于右矩阵行数", "m = q，两个外侧维度相等", "两个矩阵必须完全同形状"),
            0,
        ),
        (
            "A=[[1,2],[3,4]]，B=[[5],[6]]，A @ B 的结果是？",
            ("[[6,8],[18,24]]", "[[17],[39]]", "[[5,12]]"),
            1,
        ),
        (
            "若 A 的形状为 2×3，B 的形状为 3×4，则 A @ B 的形状为？",
            ("3×3", "4×2", "2×4"),
            2,
        ),
        (
            "矩阵乘法中，结果第 i 行第 j 列的元素如何得到？",
            ("A 的第 i 行与 B 的第 j 列做内积", "A 的第 i 列与 B 的第 j 行做拼接", "A 与 B 的对应元素相减"),
            0,
        ),
        (
            "在 NumPy 中，`A * B` 与 `A @ B` 的主要区别是什么？",
            ("前者是转置，后者是求逆", "前者通常是逐元素乘法，后者是矩阵乘法", "两者永远完全相同"),
            1,
        ),
        (
            "若 A 为 2×3、B 为 2×4，直接计算 A @ B 会怎样？",
            ("自动把 B 转置后计算且结果不变", "一定得到 2×4 矩阵", "因 A 的列数 3 不等于 B 的行数 2 而维度不匹配"),
            2,
        ),
        (
            "为什么一般不能交换矩阵乘法顺序？",
            ("矩阵只能从右向左读取", "A @ B 与 B @ A 的维度或数值结果可能不同", "交换后只会改变变量名"),
            1,
        ),
        (
            "矩阵乘法最适合描述哪类操作？",
            ("用线性变换把输入特征映射到输出特征", "记录一个布尔值", "存储不带结构的文本"),
            0,
        ),
    ),
}

_GENERIC_QUIZ_PROMPT_TEMPLATES = (
    "关于“{topic}”，哪项描述最符合本节学习目标？",
    "学习“{topic}”时，哪项输入或前置条件需要优先确认？",
    "下面哪种做法最适合验证“{topic}”的结果？",
    "“{topic}”出现结果异常时，最合理的排查方向是什么？",
    "改变哪项因素最可能影响“{topic}”的输出？",
    "关于“{topic}”的输入、规则和输出，哪项说法准确？",
    "把“{topic}”迁移到新任务时，哪项做法更稳妥？",
    "哪项实验最能区分“{topic}”与相邻概念？",
)

_GENERIC_QUIZ_ANSWERS = (
    "先从输入表示、核心规则和输出含义三部分解释这个概念。",
    "先确认输入类型、形状和必要的前置条件。",
    "用一个最小可运行样例打印输入、中间结果和输出进行核对。",
    "依次比较输入、参数、关键中间量和输出，定位第一个不一致处。",
    "一次只改变一个关键参数，并记录输出形状或数值的变化。",
    "同时检查输入约束、运算规则和输出结果，而不是只看接口是否调用成功。",
    "先明确新任务的目标和验收指标，再选择对应的输入、规则和实现。",
    "固定其余条件，改变一个能体现语义差异的因素并比较结果。",
)


def _preview_quiz_item(
    *,
    topic: str,
    kind: object,
    index: int,
    difficulty: int,
    facts: tuple[str, ...] = (),
) -> StudentQuizItem:
    prompt, choices, correct_choice = _preview_quiz_content(topic, kind, index, facts)
    return StudentQuizItem(
        question_id=f"preview-question-{index}",
        kind=kind,
        difficulty=difficulty,
        prompt=prompt,
        hints=(),
        choices=choices,
        correct_choice=correct_choice,
    )


def _preview_quiz_content(
    topic: str,
    kind: object,
    index: int,
    facts: tuple[str, ...] = (),
) -> tuple[str, tuple[str, ...], int]:
    """Return a closed, answerable item; previews must not disguise open prompts as MCQs."""
    bank = _PREVIEW_QUIZ_BANK.get(topic)
    if bank is not None:
        return bank[index - 1]

    kind_value = getattr(kind, "value", str(kind))
    label = _QUIZ_KIND_LABELS.get(kind_value, kind_value)
    evidence_facts = tuple(
        statement
        for value in facts
        if (statement := _quiz_statement(value)) is not None
    )
    explanation = _CONCEPT_EXPLANATIONS.get(
        topic,
        evidence_facts[0] if evidence_facts else f"{topic}是本节学习的核心概念。",
    )
    focus = (
        evidence_facts[(index - 1) % len(evidence_facts)]
        if evidence_facts
        else _GENERIC_QUIZ_ANSWERS[index - 1]
    )
    correct_position = (index - 1) % 3
    alternatives = [
        focus,
        "可以跳过输入输出约束，直接套用同一组参数。",
        "只要接口调用成功，就不必核对结果形状和数值。",
    ]
    correct = alternatives.pop(0)
    alternatives.insert(correct_position, correct)
    return (
        f"[{label}] {(_GENERIC_QUIZ_PROMPT_TEMPLATES[index - 1]).format(topic=topic)}",
        tuple(alternatives),
        correct_position,
    )


def _quiz_statement(value: str) -> str | None:
    """Keep fallback questions tied to the current node's evidence, not a global script."""
    normalized = " ".join(str(value).split()).strip()
    if not normalized or normalized.startswith("未检索到已审核"):
        return None
    for separator in ("。", ". ", "！", "？"):
        head = normalized.split(separator, 1)[0].strip()
        if head:
            normalized = head
            break
    return normalized[:180]


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
