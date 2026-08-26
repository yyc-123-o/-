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
    ResourceAuditor,
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

    @property
    def llm_adapter(self) -> LLMAdapter | None:
        return self._llm_adapter

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
        # The first learning screen must be available immediately.  Candidate lesson
        # structure is deterministic and evidence-bounded; the configured LLM is
        # reserved for the learner's later code-review feedback.
        adapter = FakeLLMAdapter(draft)
        auditor = ResourceAuditor()
        package = ControlledResourceGenerationService(adapter, auditor=auditor).generate(
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
    topic = _concept_label(handoff.concept_id)
    outcome = handoff.learning_outcomes[0]
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
            prompt=_quiz_prompt(topic, outcome, kind, index),
            hints=(),
            choices=_quiz_choices(topic, kind, index),
            correct_choice=0,
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
            sections=_lecture_sections(topic, outcome, definition_text),
            claims=(lecture_claim,),
            explanation_order=policy.personalization.explanation_order_hint,
            blocks=_lesson_blocks(topic, outcome, definition_text),
        ),
        practical_guide=PracticalGuideDraft(
            title=f"{topic}：实操指南",
            learning_steps=_practical_steps(topic, outcome, code_text),
            claims=(practical_claim,),
            notebook_tasks=(code_text,),
            debug_hint_depth=policy.personalization.debugging_emphasis,
            exercise=_practice_exercise(topic, outcome),
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


def _lecture_sections(topic: str, outcome: str, definition_text: str) -> tuple[str, ...]:
    explanation = _CONCEPT_EXPLANATIONS.get(topic, f"{topic}是本节需要掌握的核心概念。")
    return (
        f"学习目标：{outcome}",
        f"核心概念：{explanation}",
        f"证据导读：{definition_text}",
        f"自检：不用看资料，说明“{topic}”与相邻前置知识的一个区别。",
    )


def _lesson_blocks(topic: str, outcome: str, definition_text: str) -> tuple[LessonBlock, ...]:
    """Build a complete lesson spine for the deterministic candidate preview."""
    explanation = _CONCEPT_EXPLANATIONS.get(
        topic, f"{topic}是本节点的核心概念，必须先明确输入、变换规则和输出。"
    )
    derivation, example, pitfall = _lesson_details(topic)
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
        LessonBlock(kind="example", title="带着数值或代码走一遍", body=example),
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
            "标量只有一个数值，因此加、减、乘、除都围绕这个单值进行。标量与向量相乘时，"
            "向量的每个分量都乘同一个数；符号会改变方向，绝对值会改变长度。",
            "设 s = -2.5，v = [3, 0, -1]。逐项计算 s × v，得到 [-7.5, -0.0, 2.5]。"
            "这里没有维度扩展：一个标量只是作用到向量的每个位置。",
            "不要把标量乘法和矩阵乘法混淆。标量乘法不要求形状匹配；它只把同一个数应用到每个元素。",
        ),
        "向量": (
            "把向量写成按顺序排列的分量，例如 v = [v1, v2, v3]。相加时对应位置相加；"
            "点积时对应位置相乘后求和，因此两个向量必须有相同长度。",
            "令 a = [1, 2, 3]，b = [4, 0, -1]。a + b = [5, 2, 2]；"
            "a · b = 1×4 + 2×0 + 3×(-1) = 1。",
            "向量的逗号顺序就是维度顺序。把行向量、列向量或不同长度的向量直接相加，会得到错误或不符合预期的广播。",
        ),
        "矩阵": (
            "矩阵用行和列组织数据。A 的形状记为 (m, n)：m 表示行数，n 表示列数。"
            "逐元素运算需要对应位置存在；矩阵乘法还要求左矩阵列数等于右矩阵行数。",
            "A = [[1, 2], [3, 4]]，B = [[5, 6], [7, 8]]。A + B 逐元素相加；"
            "A @ B 的左上角是 1×5 + 2×7 = 19。",
            "`*` 在 NumPy 中通常表示逐元素乘法，`@` 才表示矩阵乘法。"
            "先打印 shape，再决定用哪个运算符。",
        ),
        "张量": (
            "张量把标量、向量和矩阵推广到更多维度。深度学习中一批彩色图像常写成 "
            "(batch, channel, height, width)，"
            "每个轴都表达不同含义，不能因为元素个数相同就随意交换轴。",
            "一张 RGB 图像的形状可以是 (3, 32, 32)：3 个通道，每个通道 32×32。"
            "加入 8 张图像的批次后，形状变为 (8, 3, 32, 32)。",
            "最常见的错误是把 HWC 图像直接传给要求 NCHW 的 PyTorch 层。"
            "尺寸看似正确，但通道轴含义已经错位。",
        ),
        "卷积运算": (
            "二维卷积层在输入特征图上滑动一个小窗口。每个位置把窗口元素与卷积核逐项相乘并求和，"
            "得到输出特征图的一个值。padding 决定边界如何补齐，stride 决定窗口每次移动几格。",
            "输入高度 H=5，卷积核 K=3，padding P=1，stride S=1 时，输出高度为"
            " floor((H + 2P - K) / S) + 1 = floor((5 + 2 - 3)/1)+1 = 5。",
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
                "完成标量与向量相乘：用标量 s 逐项缩放向量 v，打印结果并验证结果仍有 3 个元素。"
                f"完成后，用一句注释说明这段代码如何帮助你达成“{outcome}”。"
            ),
            starter_code=(
                "s = -2.5\n"
                "v = [3, 0, -1]\n\n"
                "# TODO: 将 s 乘到 v 的每个元素上\n"
                "scaled = []\n\n"
                "print(scaled)\n"
                "assert len(scaled) == 3\n"
            ),
            expected_output="[-7.5, -0.0, 2.5]",
            checks=(
                "结果包含 3 个元素",
                "每个元素都由 s 与对应 v 元素相乘得到",
                "保留 assert 验证",
            ),
            required_tokens=("s", "v", "scaled", "print"),
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
                "补全一个 3×3 输入与 2×2 卷积核的单位置互相关计算。先逐元素相乘，再求和，"
                "最后打印输出值。该练习对应深度学习框架中 Conv2d 的核心局部计算。"
            ),
            starter_code=(
                "import numpy as np\n\n"
                "image = np.array([[1, 2, 0], [0, 1, 3], [2, 2, 1]])\n"
                "kernel = np.array([[1, 0], [0, -1]])\n"
                "window = image[:2, :2]\n\n"
                "# TODO: 计算 window 与 kernel 的逐元素乘积之和\n"
                "output = None\n"
                "print(output)\n"
            ),
            expected_output="输出值为 0；请写出窗口、卷积核和逐元素乘积如何得到该结果。",
            checks=("保留 image、kernel 与 window", "使用逐元素乘法后求和", "打印 output"),
            required_tokens=("image", "kernel", "window", "output", "print"),
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


def _practical_steps(topic: str, outcome: str, code_text: str) -> tuple[str, ...]:
    return (
        f"准备：把“{topic}”的输入、输出和关键参数写成一行，确认它们的类型或形状。",
        f"实现：围绕“{topic}”完成一个最小可运行示例，并记录运行结果。",
        f"验证：用一个边界值或反例检查实现是否满足“{outcome}”。",
        f"参考代码/证据：{code_text}",
    )


def _quiz_prompt(topic: str, outcome: str, kind: object, index: int) -> str:
    kind_value = getattr(kind, "value", str(kind))
    label = _QUIZ_KIND_LABELS.get(kind_value, kind_value)
    prompts = {
        "concept": (
            f"[{label}] 用自己的话定义“{topic}”，并说明它解决的核心问题。"
            if index % 2
            else f"[{label}] 从一个实际例子出发，解释“{topic}”的输入、输出和作用。"
        ),
        "calculation": f"[{label}] 为“{topic}”设计一个最小数值例子，写出计算步骤和最终结果。",
        "shape_reasoning": (
            f"[{label}] 给定输入和关键参数后，推导“{topic}”的输出形状，并解释每一步变化。"
            if index % 2
            else f"[{label}] 修改一个关键参数，重新计算“{topic}”的输出形状并说明影响。"
        ),
        "code": (
            f"[{label}] 用 Python 或 PyTorch 写出“{topic}”的最小实现，标注输入和输出。"
            if index % 2
            else f"[{label}] 在“{topic}”示例中加入一次参数变化，打印并解释新的输出。"
        ),
        "debugging": f"[{label}] 找出“{topic}”实现中一个可能的错误，说明错误原因和修复方法。",
        "synthesis": f"[{label}] 将“{topic}”与一个前置知识联系起来，说明何时应该使用它。",
        "analysis": f"[{label}] 分析“{topic}”的适用边界，并给出一个不适合使用它的场景。",
    }
    fallback = f"[{label}] 围绕“{topic}”完成一次解释、验证或迁移。"
    return prompts.get(kind_value, fallback) + f"（第 {index} 题）"


def _quiz_choices(topic: str, kind: object, index: int) -> tuple[str, ...]:
    kind_value = getattr(kind, "value", str(kind))
    if kind_value == "concept":
        return (
            f"准确说明{topic}的输入、规则和输出",
            "只记住名词，不说明输入输出",
            "把它与任意相似术语混用",
        )
    if kind_value == "shape_reasoning":
        return (
            "先检查输入形状，再代入参数公式",
            "只看通道数，不看空间尺寸",
            "忽略 padding 和 stride",
        )
    if kind_value == "code":
        return (
            "写出最小实现并打印输入输出",
            "只复制代码，不验证结果",
            "用随机结果代替计算",
        )
    if kind_value == "debugging":
        return (
            "定位输入、类型或形状约束并修正",
            "直接删除报错代码",
            "只增加随机打印",
        )
    return (
        f"把{topic}与前置知识联系起来并解释边界",
        "只背诵定义，不分析条件",
        "认为任何输入都适用",
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
