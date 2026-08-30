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
from pydantic import BaseModel, Field, field_validator


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

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = {"专科", "本科", "硕士", "博士"}
        if v not in valid_levels:
            raise ValueError(f"level 必须是 {valid_levels} 之一, 当前: {v}")
        return v


# 五维领域自评的默认细分课程 (数学/ML/DL/优化/实践)
DOMAIN_COURSES = {
    "数学基础": ["高等数学", "线性代数", "概率论与数理统计", "最优化方法"],
    "机器学习基础": ["机器学习", "数据结构与算法"],
    "深度学习": ["深度学习", "计算机视觉", "自然语言处理"],
    "优化算法": ["最优化方法", "凸优化"],
    "实践应用": ["Python编程", "数据处理与特征工程", "模型调参与部署"],
}

# 评价标准 (供用户选择)
# 0825 最终版：用户侧简化为 3 档，同时保留旧版 5 档字符串（用于示例JSON/上传数据/旧Mock兼容校验）
LEVEL_OPTIONS = ["未学过", "基本了解", "熟练掌握", "入门", "基础", "熟练", "精通"]

# ============================================================
# 0825 更新：领域自评呈现形式配置
# mode: "knowledge_points" -> 模式1：细化知识点选择掌握程度
# mode: "guided_questions"  -> 模式2：文字引导回答
# ============================================================
DOMAIN_ASSESSMENT_CONFIG = {
    "数学基础": {
        "mode": "knowledge_points",
        "description": "",
        "knowledge_points": [
            {"group": "高等数学（微积分）", "items": [
                {"name": "偏导数与梯度", "kp_id": "kp_005"},
                {"name": "链式法则与雅可比矩阵", "kp_id": "kp_005"},
            ]},
            {"group": "线性代数", "items": [
                {"name": "矩阵乘法与转置", "kp_id": "kp_004"},
                {"name": "逆矩阵与秩", "kp_id": "kp_004"},
                {"name": "特征值与特征分解", "kp_id": "kp_004"},
                {"name": "SVD奇异值分解", "kp_id": "kp_004"},
            ]},
            {"group": "概率论与数理统计", "items": [
                {"name": "条件概率与贝叶斯定理", "kp_id": "kp_003"},
                {"name": "常见概率分布（高斯/伯努利/多项式）", "kp_id": "kp_003"},
                {"name": "期望、方差与协方差", "kp_id": "kp_003"},
                {"name": "最大似然估计MLE", "kp_id": "kp_003"},
                {"name": "信息论基础（熵/交叉熵/KL散度）", "kp_id": "kp_026"},
            ]},
        ],
    },
    "机器学习基础": {
        "mode": "guided_questions",
        "description": "",
        "guided_questions": [
            {
                "id": "q_ml_methods",
                "prompt": "1. 快速列举你知道的机器学习算法，标注类别即可（建议写5-8个）。\n例：线性回归(监督) / K-Means(无监督) / ...",
                "placeholder": "例：\n监督学习：线性回归、逻辑回归、SVM、随机森林、XGBoost、KNN、朴素贝叶斯\n无监督学习：K-Means、DBSCAN、PCA、t-SNE\n强化学习：Q-learning、DQN(仅听说过即可)",
                "height": 140,
            },
            {
                "id": "q_ml_model_compare",
                "prompt": "2. 从下列 4 组中任选 2 组，只写 1-2 句核心区别即可。\n• 线性回归 vs 逻辑回归\n• L1(Lasso) vs L2(Ridge) 正则化\n• Bagging vs Boosting\n• 决策树 vs 随机森林",
                "placeholder": "例：\n线性回归 vs 逻辑回归：前者输出连续值用MSE，后者经Sigmoid输出概率用交叉熵做分类。\nBagging vs Boosting：Bagging并行训练后投票（如随机森林），Boosting串行聚焦错例（如XGBoost）。",
                "height": 130,
            },
            {
                "id": "q_ml_practice",
                "prompt": "3. 用 1-2 句话简述一个你做过的 ML 小项目/练习：\n用什么模型？解决什么问题？结果大概如何？（没做过就写准备做什么）",
                "placeholder": "例1：用XGBoost做电信客户流失预测，AUC大概0.85。\n例2：用KMeans对客户分群做了5类画像，报告给市场部参考。\n例3：跟着教程做过MNIST手写数字识别，逻辑回归Baseline92%，MLP到97%。",
                "height": 110,
            },
            {
                "id": "q_ml_metrics",
                "prompt": "4. 从下列 4 个场景任选 2 个，只写你会用的评估指标名称（不必解释理由）。\n• 癌症筛查\n• 垃圾邮件过滤\n• 商品推荐排序\n• 不平衡二分类",
                "placeholder": "例：\n癌症筛查 → 召回率(Recall)\n垃圾邮件过滤 → 精确率(Precision)\n商品推荐 → NDCG / MAP\n不平衡二分类 → F1-score / AUC-ROC",
                "height": 120,
            },
        ],
    },
    "深度学习": {
        "mode": "knowledge_points",
        "description": "",
        "knowledge_points": [
            {"group": "深度学习基础（BP/MLP）", "items": [
                {"name": "感知机与多层感知机(MLP)", "kp_id": "kp_011"},
                {"name": "前向传播计算过程", "kp_id": "kp_011"},
                {"name": "激活函数（ReLU/Sigmoid/Tanh/GELU）", "kp_id": "kp_015"},
                {"name": "反向传播与链式求导", "kp_id": "kp_017"},
            ]},
            {"group": "卷积神经网络 CNN", "items": [
                {"name": "卷积运算（互相关 vs 卷积）", "kp_id": "kp_012"},
                {"name": "卷积核/步长/填充/感受野", "kp_id": "kp_012"},
                {"name": "池化层（Max/Avg Pooling）", "kp_id": "kp_012"},
                {"name": "经典架构：LeNet / AlexNet / VGG / ResNet", "kp_id": "kp_012"},
                {"name": "1×1卷积的作用与用途", "kp_id": "kp_012"},
            ]},
            {"group": "循环神经网络 RNN / LSTM", "items": [
                {"name": "RNN序列建模原理", "kp_id": "kp_013"},
                {"name": "梯度消失问题与LSTM门控机制", "kp_id": "kp_013"},
                {"name": "LSTM/GRU内部结构（遗忘/输入/输出门）", "kp_id": "kp_013"},
                {"name": "Seq2Seq与Encoder-Decoder", "kp_id": "kp_013"},
            ]},
            {"group": "注意力机制与 Transformer", "items": [
                {"name": "自注意力Self-Attention计算过程", "kp_id": "kp_014"},
                {"name": "多头注意力Multi-Head Attention", "kp_id": "kp_014"},
                {"name": "位置编码Positional Encoding", "kp_id": "kp_014"},
                {"name": "Transformer整体结构（Encoder/Decoder）", "kp_id": "kp_014"},
            ]},
            {"group": "归一化与训练技巧", "items": [
                {"name": "Batch Normalization原理与维度", "kp_id": "kp_028"},
                {"name": "Layer Normalization / InstanceNorm", "kp_id": "kp_028"},
                {"name": "残差连接Residual Connection", "kp_id": "kp_012"},
            ]},
        ],
    },
    "优化算法": {
        "mode": "knowledge_points",
        "description": "",
        "knowledge_points": [
            {"group": "梯度下降变体", "items": [
                {"name": "批量梯度下降BGD", "kp_id": "kp_016"},
                {"name": "随机梯度下降SGD", "kp_id": "kp_016"},
                {"name": "Mini-batch SGD", "kp_id": "kp_016"},
                {"name": "带动量的SGD（Momentum/Nesterov）", "kp_id": "kp_016"},
            ]},
            {"group": "自适应优化器", "items": [
                {"name": "AdaGrad / RMSProp 原理", "kp_id": "kp_018"},
                {"name": "Adam优化器（动量+自适应学习率）", "kp_id": "kp_018"},
                {"name": "AdamW（权重衰减解耦）", "kp_id": "kp_018"},
            ]},
            {"group": "正则化技术", "items": [
                {"name": "L1/L2权重衰减", "kp_id": "kp_019"},
                {"name": "Dropout随机失活", "kp_id": "kp_019"},
                {"name": "Early Stopping早停", "kp_id": "kp_019"},
                {"name": "数据增强Data Augmentation", "kp_id": "kp_030"},
            ]},
            {"group": "学习率调度", "items": [
                {"name": "Warmup预热策略", "kp_id": "kp_020"},
                {"name": "StepLR / Reduce-on-Plateau", "kp_id": "kp_020"},
            ]},
            {"group": "损失函数", "items": [
                {"name": "MSE均方误差（回归）", "kp_id": "kp_029"},
                {"name": "交叉熵Cross-Entropy（分类）", "kp_id": "kp_029"},
            ]},
        ],
    },
    "实践应用": {
        "mode": "guided_questions",
        "description": "",
        "guided_questions": [
            {
                "id": "q_py_stack",
                "prompt": "1. 快速列出你最熟练的 3-5 个工具/框架，并在后面用一个词标出熟练度（熟练/会用/用过）。\n例：NumPy(熟练) / PyTorch(会用) / ...",
                "placeholder": "例：\nPython(熟练)、NumPy/Pandas(熟练)、PyTorch(会用)、sklearn(熟练)、Matplotlib(会用)\n或（若零基础）：Python(入门)、还没学过PyTorch，计划下个月开始学",
                "height": 110,
            },
            {
                "id": "q_data_pipeline",
                "prompt": "2. 数据预处理时，你最常用的 3 个操作是什么？各写 1 句话说明用在什么场景（不会就写你听说过的3个）。",
                "placeholder": "例：\n1. StandardScaler标准化：把数值型特征缩到均值0方差1，用于梯度下降类模型\n2. OneHot编码：把类别特征转成0/1向量，喂给逻辑回归/MLP\n3. SMOTE过采样：解决正负样本1:10这种严重不平衡的分类问题",
                "height": 140,
            },
            {
                "id": "q_tuning_deploy",
                "prompt": "3. 用一句话回答两个小问题（不会就大胆写「还不会，以后学」）：\n① 你调超参常用的方法是？\n② 你有没有把训练好的模型导出或部署过？有则写 1 种导出格式。",
                "placeholder": "例1：调参用Optuna贝叶斯优化，模型导出过ONNX格式做推理。\n例2：调参手调网格搜索都用过，还没部署过，只会保存pth文件。\n例3：还不会调参，没部署过，以后学。",
                "height": 100,
            },
            {
                "id": "q_debug_story",
                "prompt": "4. 快速列举你做模型训练时最常见的 1-2 个「坑」，每个坑用半句话写解决思路（没遇到过就写你怕遇到的坑）。",
                "placeholder": "例：\n坑1 Loss不下降 → 检查是不是忘了ToTensor/归一化/写loss.backward()，调小学习率\n坑2 严重过拟合 → 加Dropout + L2正则 + 早停 + 数据增强\n或（还没踩坑）：最怕遇到梯度消失/NAN损失，准备以后逐层打印梯度来排查",
                "height": 130,
            },
        ],
    },
}


class CourseSelfAssessment(BaseModel):
    """细分课程自评 — 某个领域下的具体课程评价
    0825 更新: 新增 kp_id（模式1：知识点掌握度选择对应教学点ID）, 兼容旧结构
    """
    name: str = Field("", description="课程/知识点 名")
    level: str = Field("未学过", description="评价标准: 未学过/基本了解/熟练掌握（旧版兼容：入门/基础/熟练/精通）")
    note: str = Field("", description="自评填空")
    kp_id: Optional[str] = Field(None, description="【0825新增】对应知识点教学点ID（模式1：knowledge_points下可用）")

    model_config = {"extra": "allow"}  # 允许前端传来的 _synthetic 等临时字段

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        if v not in LEVEL_OPTIONS:
            raise ValueError(f"level 必须是 {LEVEL_OPTIONS} 之一, 当前: {v}")
        return v


class DomainAssessment(BaseModel):
    """五维领域自评（数学基础/机器学习基础/深度学习/优化算法/实践应用）
    0825 更新: 新增 mode 字段区分呈现形式；guided_answers 字典保存模式2的问答文本
    """
    domain: str = Field("", description="领域名")
    courses: List[CourseSelfAssessment] = Field(default_factory=list, description="细分课程/知识点自评")
    note: str = Field("", description="该领域自评填空（模式2下会拼接所有引导回答）")
    mode: Optional[str] = Field(None, description="【0825新增】自评呈现形式: knowledge_points（模式1） / guided_questions（模式2） / legacy（旧版）")
    guided_answers: Optional[Dict[str, str]] = Field(None, description="【0825新增】模式2（guided_questions）下各引导题目的问答原文, key=题目ID, value=用户作答")

    model_config = {"extra": "allow"}


class ProjectExperience(BaseModel):
    """项目经历"""
    name: str = Field("", description="项目名")
    role: str = Field("", description="担任角色/职责")
    description: str = Field("", description="项目描述")
    tech_stack: List[str] = Field(default_factory=list, description="技术栈")
    duration_months: int = Field(0, description="持续月数")


class SelfAssessment(BaseModel):
    """自填问卷摘要"""
    # 旧版扁平字段（兼容历史上传数据）
    ml_level: str = ""
    dl_level: str = ""
    math_level: str = ""
    programming_level: str = ""
    position: str = Field("", description="职位/担任角色")
    strengths: str = Field("", description="优势/已掌握内容详细描述")
    weaknesses: str = Field("", description="薄弱/待提升内容详细描述")
    courses: List[CourseSelfAssessment] = Field(default_factory=list, description="分课程自评（旧版兼容）")
    # 通用字段
    learning_goal: str = Field("", description="学习目标")
    weekly_hours: int = Field(5, description="每周学习小时数")
    domain_assessments: List[DomainAssessment] = Field(default_factory=list, description="五维领域自评")
    projects: List[ProjectExperience] = Field(default_factory=list, description="项目经历")


class TestRecord(BaseModel):
    """测试记录"""
    knowledge_point_id: str
    question_id: str = ""
    difficulty: float = Field(..., allow_inf_nan=False, description="题目难度 b, IRT参数")
    discrimination: float = Field(1.0, gt=0, allow_inf_nan=False, description="题目区分度 a, IRT参数")
    is_correct: bool
    timestamp: datetime = Field(default_factory=datetime.now)
    time_spent: int = Field(60, ge=0, description="答题用时(秒)")
    hint_used: bool = False
    error_pattern: Optional[str] = Field(None, description="概念混淆/计算错误/逻辑跳跃/忽略条件")

    @field_validator("time_spent")
    @classmethod
    def validate_time_spent(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"time_spent 必须 >= 0, 当前: {v}")
        return v

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: float) -> float:
        if v < -5 or v > 5:
            raise ValueError(f"difficulty 必须在 [-5, 5] 范围内, 当前: {v}")
        return v

    @field_validator("discrimination")
    @classmethod
    def validate_discrimination(cls, v: float) -> float:
        if v < -5 or v > 5:
            raise ValueError(f"discrimination 必须在 [-5, 5] 范围内, 当前: {v}")
        return v

    @field_validator("error_pattern")
    @classmethod
    def validate_error_pattern(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        valid_patterns = {"概念混淆", "计算错误", "逻辑跳跃", "忽略条件"}
        if v not in valid_patterns:
            raise ValueError(f"error_pattern 必须是 {valid_patterns} 之一 或 None, 当前: {v}")
        return v


class InteractionRecord(BaseModel):
    """交互记录"""
    knowledge_point_id: str
    type: str = Field("view", description="view/quiz/practice/discussion")
    duration: int = Field(60, description="持续时长(秒)")
    timestamp: datetime = Field(default_factory=datetime.now)
    detail: str = Field("", description="动作描述")

    @field_validator("duration")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"duration 必须 >= 0, 当前: {v}")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid_types = {"view", "quiz", "practice", "discussion"}
        if v not in valid_types:
            raise ValueError(f"type 必须是 {valid_types} 之一, 当前: {v}")
        return v


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
    mastery: Optional[float] = Field(None, description="掌握度数值，未测评节点为null")
    status: str = "unexplored"
    theta_kp: float = 0.0
    test_count: int = 0
    confidence: float = 0.0
    standard_error: Optional[float] = None
    evidence_level: str = "none"


class DomainSummaryItem(BaseModel):
    mean_mastery: Optional[float] = None
    kps_covered: int = 0
    total_kps: int = 0
    tested_kps: int = 0
    evidence_confidence: float = 0.0


class StatusDistributionItem(BaseModel):
    range: str = ""
    count: int = 0


class KnowledgeMastery(BaseModel):
    """知识点掌握度矩阵"""
    global_theta: float = 0.0
    standard_error: Optional[float] = None
    estimation_method: str = "prior-only"
    item_calibration_status: str = "provisional"
    ability_level: str = "beginner"
    overall_accuracy: float = 0.0
    overall_mastery: Optional[float] = None
    overall_confidence: float = 0.0
    tested_kps: int = 0
    total_kps: int = 0
    coverage_ratio: float = 0.0
    confidence_note: str = ""
    domain_summary: Dict[str, DomainSummaryItem] = Field(default_factory=dict)
    points: Dict[str, KpMasteryPoint] = Field(default_factory=dict)
    status_distribution: Dict[str, StatusDistributionItem] = Field(default_factory=dict)


# --- 能力等级 ---

class SubDimension(BaseModel):
    score: Optional[float] = None
    level: str = "insufficient_evidence"
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
    graph_version: str = "ai-course-v1"
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


# ============================================================
# 学习成果检验报告 (第二流程)
# ============================================================

class KpChange(BaseModel):
    """单个知识点的掌握度变化"""
    kp_id: str
    name: str
    domain: str
    before: Optional[float] = None
    after: Optional[float] = None
    delta: float = 0.0
    category: str = Field("不变", description="显著提升/提升/不变/下降")


class DomainChange(BaseModel):
    """单个领域的掌握度变化"""
    domain: str
    before: float = 0.0
    after: float = 0.0
    delta: float = 0.0


class GapChange(BaseModel):
    """盲区变化条目"""
    kp_id: str
    name: str
    domain: str
    before: float = 0.0
    after: float = 0.0


class ErrorPatternChange(BaseModel):
    """错误模式变化"""
    category: str
    before_ratio: float = 0.0
    after_ratio: float = 0.0
    delta: float = 0.0


class LearningOutcomeReport(BaseModel):
    """学习成果检验报告 — 第二流程核心输出"""
    report_id: str = ""
    learner_id: str = ""
    chapter_id: str = ""
    baseline_profile_id: str = ""
    post_profile_id: str = ""
    overall_verdict: str = Field("", description="显著提升/一般提升/无明显提升/退步")
    theta: Dict = Field(default_factory=dict, description="{before, after, delta}")
    accuracy: Dict = Field(default_factory=dict, description="{before, after, delta}")
    ability_level: Dict = Field(default_factory=dict, description="{before, after}")
    domain_changes: List[DomainChange] = Field(default_factory=list)
    kp_changes: List[KpChange] = Field(default_factory=list)
    gaps_resolved: List[GapChange] = Field(default_factory=list)
    gaps_remaining: List[GapChange] = Field(default_factory=list)
    gaps_new: List[GapChange] = Field(default_factory=list)
    error_pattern_changes: List[ErrorPatternChange] = Field(default_factory=list)
    recommendation: str = ""
