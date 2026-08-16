"""Pydantic 数据模型 — 学习者/测试记录/交互记录/画像

v2.1 升级 (0803):
- 画像输出对齐 学情画像输出-最终版 0803修改.json
- 新增 LearningScope 章节级学习范围
- 重构 KnowledgeMastery / AbilityLevel / ErrorPatterns / LearningPreferences 为 0803 嵌套结构
- ResourceGenerationHints 标注 scope="chapter"
- 所有关键字段补充 confidence
"""

from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ============================================================
# 输入数据模型
# ============================================================

class Education(BaseModel):
    """学历背景"""
    level: str = Field(..., description="专科/本科/硕士/博士")
    major: str = Field("", description="专业")
    institution: str = Field("", description="学校")
    graduation_year: int = Field(2025, description="毕业年份")
    gpa: Optional[float] = Field(None, description="GPA")
    relevant_courses: List[str] = Field(default_factory=list, description="相关课程")


class SelfAssessment(BaseModel):
    """自填问卷摘要"""
    ml_level: str = ""
    dl_level: str = ""
    math_level: str = ""
    learning_goal: str = ""
    weekly_hours: int = 5


class TestRecord(BaseModel):
    """测试记录"""
    knowledge_point_id: str
    question_id: str = ""
    difficulty: float = Field(..., description="题目难度 b, IRT参数")
    discrimination: float = Field(1.0, description="题目区分度 a, IRT参数")
    is_correct: bool
    timestamp: datetime = Field(default_factory=datetime.now)
    time_spent: int = Field(60, description="答题用时(秒)")
    hint_used: bool = False
    error_pattern: Optional[str] = Field(None, description="概念混淆/计算错误/逻辑跳跃/忽略条件")


class InteractionRecord(BaseModel):
    """交互记录"""
    knowledge_point_id: str
    type: str = Field("view", description="view/quiz/practice/discussion")
    duration: int = Field(60, description="持续时长(秒)")
    timestamp: datetime = Field(default_factory=datetime.now)
    detail: str = Field("", description="动作描述")


class Learner(BaseModel):
    """学习者"""
    id: str
    name: str
    education: Education
    self_assessment: Optional[SelfAssessment] = Field(default=None, description="自填问卷")
    test_records: List[TestRecord] = Field(default_factory=list)
    interaction_records: List[InteractionRecord] = Field(default_factory=list)


# ============================================================
# 输出数据模型 — 子结构 (0803 对齐)
# ============================================================

# --- 学习范围 ---

class SuccessorChapter(BaseModel):
    chapter_id: str
    kp_id: str
    name: str
    depth_planned: str = "入门"


class LearningScope(BaseModel):
    """章节级学习范围"""
    scope_type: str = Field("chapter", description="固定为 chapter")
    chapter_id: str
    chapter_name: str
    chapter_order: int = 1
    primary_kp_id: str
    primary_kp_name: str
    target_depth: str = "进阶"
    estimated_hours: float = 8.0
    resource_generation_target: str = ""
    predecessor_kp_ids: List[str] = Field(default_factory=list)
    co_requisite_kp_ids: List[str] = Field(default_factory=list)
    successor_chapters: List[SuccessorChapter] = Field(default_factory=list)
    path_note: str = ""


# --- 知识点掌握度 ---

class KpMasteryPoint(BaseModel):
    """单个知识点掌握度"""
    name: str
    domain: str
    mastery: float = 0.0
    status: str = "unexplored"
    theta_kp: float = 0.0
    test_count: int = 0
    confidence: float = 0.0


class DomainSummaryItem(BaseModel):
    mean_mastery: float = 0.0
    kps_covered: int = 0


class StatusDistributionItem(BaseModel):
    range: str = ""
    count: int = 0


class KnowledgeMastery(BaseModel):
    """知识点掌握度矩阵"""
    global_theta: float = 0.0
    ability_level: str = "beginner"
    overall_accuracy: float = 0.0
    confidence_note: str = ""
    domain_summary: Dict[str, DomainSummaryItem] = Field(default_factory=dict)
    points: Dict[str, KpMasteryPoint] = Field(default_factory=dict)
    status_distribution: Dict[str, StatusDistributionItem] = Field(default_factory=dict)


# --- 能力等级 ---

class SubDimension(BaseModel):
    score: float = 0.0
    level: str = "beginner"
    confidence: float = 0.0


class AbilityLevel(BaseModel):
    """能力等级"""
    overall: str = "beginner"
    global_theta: float = 0.0
    rationale: str = ""
    sub_dimensions: Dict[str, SubDimension] = Field(default_factory=dict)


# --- 错误模式 ---

class ErrorPatternItem(BaseModel):
    """单个错误模式"""
    category: str
    count: int = 0
    ratio: float = 0.0
    confidence: float = 0.0
    description: str = ""
    typical_examples: List[str] = Field(default_factory=list)
    involved_kp_ids: List[str] = Field(default_factory=list)


class ErrorPatterns(BaseModel):
    """错误模式集合"""
    total_questions: int = 0
    total_correct: int = 0
    total_wrong: int = 0
    overall_accuracy: float = 0.0
    primary_weakness: str = ""
    primary_weakness_ratio: float = 0.0
    classification_confidence: float = 0.0
    confidence_note: str = ""
    items: List[ErrorPatternItem] = Field(default_factory=list)


# --- 学习偏好 (0803 五组结构) ---

class FormatPreference(BaseModel):
    content_order: List[str] = Field(default_factory=list)
    code_language: str = "Python"
    framework: str = "PyTorch"
    framework_level: str = ""
    framework_confidence: float = 0.0
    confidence_note: str = ""


class StylePreference(BaseModel):
    visual_learner: bool = True
    prefers_step_by_step: bool = True
    prefers_comparison_tables: bool = False
    prefers_diagrams: bool = True
    prefers_math_formulas: bool = True


class PacePreference(BaseModel):
    weekly_hours: int = 5
    session_attention_minutes: int = 45
    avg_test_time_seconds: int = 60
    learning_pace_inferred: str = "medium"


class InteractionPreference(BaseModel):
    level: str = "low"
    hint_dependency: float = 0.0
    view_practice_ratio: str = "1:1"
    prefers_discussion: bool = False


class MotivationPreference(BaseModel):
    primary: str = ""
    secondary: str = ""
    project_driven: bool = False
    target_project: str = ""


class LearningPreferences(BaseModel):
    """学习偏好 (0803 五组嵌套结构)"""
    format: FormatPreference = Field(default_factory=FormatPreference)
    style: StylePreference = Field(default_factory=StylePreference)
    pace: PacePreference = Field(default_factory=PacePreference)
    interaction: InteractionPreference = Field(default_factory=InteractionPreference)
    motivation: MotivationPreference = Field(default_factory=MotivationPreference)


# --- 知识盲区 ---

class KnowledgeGap(BaseModel):
    """知识盲区条目"""
    kp_id: str
    kp_name: str
    domain: str
    mastery: float
    gap_type: str = Field(..., description="blindspot/weak/blocked/difficult")
    priority: str = Field("medium", description="high/medium/low")
    description: str = ""
    blocked_by: List[str] = Field(default_factory=list)
    blocks: List[str] = Field(default_factory=list)
    suggested_action: str = ""
    confidence: float = 0.0


# --- 深度标签 ---

class DepthLabel(BaseModel):
    """知识点深度标签"""
    kp_id: str
    kp_name: str
    depth: str = Field("entry", description="skip/review/entry/advanced")
    rationale: str = ""


# --- 资源生成提示 (章节级) ---

class LectureNotesHints(BaseModel):
    must_include: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)
    comparison_tables: List[str] = Field(default_factory=list)
    error_pattern_attention: str = ""
    estimated_pages: str = ""


class PracticalGuideHints(BaseModel):
    must_include: List[str] = Field(default_factory=list)
    code_style: str = ""
    dataset: str = ""
    framework: str = ""
    estimated_cells: str = ""


class TestQuestionsHints(BaseModel):
    total: int = 10
    distribution: Dict[str, int] = Field(default_factory=dict)
    difficulty: Dict[str, Dict] = Field(default_factory=dict)
    target_overall_accuracy_range: List[float] = Field(default_factory=lambda: [0.60, 0.85])
    error_pattern_mitigations: List[str] = Field(default_factory=list)
    must_cover: List[str] = Field(default_factory=list)
    estimated_time_minutes: int = 45


class ResourceGenerationHints(BaseModel):
    """资源生成提示 — 章节级"""
    scope: str = Field("chapter", description="固定为 chapter")
    scope_note: str = ""
    target_chapter_id: str = ""
    target_chapter_name: str = ""
    target_depth: str = "进阶"
    depth_rationale: str = ""
    lecture_notes: LectureNotesHints = Field(default_factory=LectureNotesHints)
    practical_guide: PracticalGuideHints = Field(default_factory=PracticalGuideHints)
    test_questions: TestQuestionsHints = Field(default_factory=TestQuestionsHints)


# --- 前序章节 ---

class PriorChapter(BaseModel):
    """前序章节表现"""
    chapter_id: str
    chapter_name: str
    accuracy: float = 0.0
    time_spent_hours: float = 0.0
    depth_assigned: str = "entry"
    kps_covered: List[str] = Field(default_factory=list)
    error_patterns_observed: List[str] = Field(default_factory=list)
    completed_at: Optional[str] = None
    conclusion: str = ""


# --- 证据 ---

class EvidenceRecord(BaseModel):
    """证据溯源"""
    claim: str = ""
    source: str = Field("", description="irt_estimation/answer_history/self_assessment/gap_analysis/self_assessment_and_interaction")
    detail: str = ""
    confidence: float = 0.0


# --- 诊断摘要 ---

class DiagnosisSummary(BaseModel):
    short: str = ""
    full: str = ""
    profile_confidence: str = ""


# ============================================================
# 顶层输出 — LearnerProfile (0803 对齐)
# ============================================================

class LearnerProfile(BaseModel):
    """学习者画像 — 学情诊断Agent完整输出 (v2.1, 对齐 0803)

    顶层字段与 学情画像输出-最终版 0803修改.json 完全一致
    """
    profile_id: str = ""
    profile_version: str = "2.1"
    generated_by: str = "学情诊断Agent v2.1"
    generated_at: str = ""
    learner_id: str = ""
    update_cycle: str = "per-chapter"

    learner: Dict = Field(default_factory=dict, description="{name, education, self_assessment}")
    learning_scope: LearningScope = Field(default_factory=LearningScope)
    knowledge_mastery: KnowledgeMastery = Field(default_factory=KnowledgeMastery)
    ability_level: AbilityLevel = Field(default_factory=AbilityLevel)
    error_patterns: ErrorPatterns = Field(default_factory=ErrorPatterns)
    learning_preferences: LearningPreferences = Field(default_factory=LearningPreferences)
    knowledge_gaps: List[KnowledgeGap] = Field(default_factory=list)
    depth_labels: List[DepthLabel] = Field(default_factory=list)
    resource_generation_hints: ResourceGenerationHints = Field(default_factory=ResourceGenerationHints)
    prior_chapters: List[PriorChapter] = Field(default_factory=list)
    evidence: List[EvidenceRecord] = Field(default_factory=list)
    diagnosis_summary: DiagnosisSummary = Field(default_factory=DiagnosisSummary)

    meta: Dict = Field(default_factory=dict, description="{total_test_count, total_interaction_count, diagnosed_at, next_suggested_diagnosis}")


class DiagnosisResult(BaseModel):
    """诊断结果包装"""
    success: bool
    profile: Optional[LearnerProfile] = None
    message: str = ""
