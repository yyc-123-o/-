"""AI/ML 知识图谱定义 — 5个知识域, 30个知识点, 含DAG前置依赖 + 章节映射"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class KnowledgePoint:
    """知识点节点"""
    id: str
    name: str
    domain: str
    difficulty: float          # IRT b 参数, -3~3, 越大越难
    prerequisites: List[str] = field(default_factory=list)  # 前置知识点ID
    description: str = ""


@dataclass
class Chapter:
    """章节定义 — 对应 learning_scope"""
    chapter_id: str
    chapter_name: str
    chapter_order: int
    primary_kp_id: str                    # 该章主知识点
    predecessor_kp_ids: List[str] = field(default_factory=list)   # 需先掌握的前驱
    co_requisite_kp_ids: List[str] = field(default_factory=list)  # 同时学习的共需知识点
    successor_chapter_ids: List[str] = field(default_factory=list) # 后继章节ID
    estimated_hours: float = 6.0


# ============================================================
# 章节定义 (6章学习路径)
# ============================================================

CHAPTERS: List[Chapter] = [
    Chapter(
        "ch01_foundation", "数学与编程基础回顾", 1,
        primary_kp_id="kp_005",
        predecessor_kp_ids=[],
        co_requisite_kp_ids=["kp_001", "kp_002", "kp_021"],
        successor_chapter_ids=["ch02_ml_review"],
        estimated_hours=3.0,
    ),
    Chapter(
        "ch02_ml_review", "机器学习核心回顾+神经网络入门", 2,
        primary_kp_id="kp_011",
        predecessor_kp_ids=["kp_005"],
        co_requisite_kp_ids=["kp_006", "kp_008", "kp_015", "kp_016"],
        successor_chapter_ids=["ch03_cnn"],
        estimated_hours=6.0,
    ),
    Chapter(
        "ch03_cnn", "卷积神经网络（CNN）", 3,
        primary_kp_id="kp_012",
        predecessor_kp_ids=["kp_011", "kp_004", "kp_005", "kp_016", "kp_017"],
        co_requisite_kp_ids=["kp_015", "kp_019", "kp_028", "kp_029", "kp_018", "kp_020"],
        successor_chapter_ids=["ch04_transfer", "ch05_rnn", "ch06_transformer"],
        estimated_hours=8.0,
    ),
    Chapter(
        "ch04_transfer", "迁移学习与数据增强", 4,
        primary_kp_id="kp_030",
        predecessor_kp_ids=["kp_012"],
        co_requisite_kp_ids=["kp_022", "kp_023"],
        successor_chapter_ids=[],
        estimated_hours=5.0,
    ),
    Chapter(
        "ch05_rnn", "循环神经网络RNN/LSTM", 5,
        primary_kp_id="kp_013",
        predecessor_kp_ids=["kp_011", "kp_012"],
        co_requisite_kp_ids=["kp_017", "kp_020"],
        successor_chapter_ids=[],
        estimated_hours=6.0,
    ),
    Chapter(
        "ch06_transformer", "Transformer与Attention", 6,
        primary_kp_id="kp_014",
        predecessor_kp_ids=["kp_011", "kp_013"],
        co_requisite_kp_ids=["kp_026", "kp_029"],
        successor_chapter_ids=[],
        estimated_hours=8.0,
    ),
]


# ============================================================
# AI/ML 知识图谱 (30个知识点, 5个知识域)
# ============================================================

KNOWLEDGE_POINTS: List[KnowledgePoint] = [
    # ---- 数学基础 (Math Foundations) ----
    KnowledgePoint("kp_001", "微积分基础", "数学基础", -1.0, [], "极限、连续性、基本微分积分概念"),
    KnowledgePoint("kp_002", "线性代数", "数学基础", -0.5, [], "向量、矩阵、线性变换"),
    KnowledgePoint("kp_003", "概率论", "数学基础", 0.0, [], "概率分布、期望、方差、贝叶斯定理"),
    KnowledgePoint("kp_004", "矩阵运算", "数学基础", 0.5, ["kp_002"], "矩阵乘法、转置、逆矩阵、特征分解"),
    KnowledgePoint("kp_005", "导数与梯度", "数学基础", 0.0, ["kp_001"], "偏导数、梯度、链式法则"),
    KnowledgePoint("kp_026", "信息论基础", "数学基础", 0.5, ["kp_003"], "熵、交叉熵、KL散度"),

    # ---- 机器学习基础 (ML Fundamentals) ----
    KnowledgePoint("kp_006", "监督学习", "机器学习基础", 0.0, ["kp_003", "kp_005"], "线性回归、逻辑回归、分类与回归"),
    KnowledgePoint("kp_007", "无监督学习", "机器学习基础", 0.5, ["kp_006"], "K-Means、PCA、层次聚类"),
    KnowledgePoint("kp_008", "过拟合与欠拟合", "机器学习基础", 0.5, ["kp_006"], "偏差-方差权衡、模型容量"),
    KnowledgePoint("kp_009", "交叉验证", "机器学习基础", 0.5, ["kp_006"], "K折交叉验证、留一法"),
    KnowledgePoint("kp_010", "评估指标", "机器学习基础", 0.0, ["kp_006"], "精确率、召回率、F1、AUC-ROC"),
    KnowledgePoint("kp_027", "集成学习", "机器学习基础", 1.0, ["kp_006", "kp_008"], "Bagging、Boosting、Stacking、随机森林"),

    # ---- 深度学习 (Deep Learning) ----
    KnowledgePoint("kp_011", "神经网络基础", "深度学习", 0.5, ["kp_004", "kp_005"], "感知机、MLP、前向传播"),
    KnowledgePoint("kp_012", "卷积神经网络CNN", "深度学习", 1.0, ["kp_011"], "卷积层、池化层、经典架构"),
    KnowledgePoint("kp_013", "循环神经网络RNN/LSTM", "深度学习", 1.5, ["kp_011"], "序列建模、门控机制、梯度消失"),
    KnowledgePoint("kp_014", "Transformer与Attention", "深度学习", 2.0, ["kp_011"], "自注意力、多头注意力、位置编码"),
    KnowledgePoint("kp_015", "激活函数", "深度学习", 0.5, ["kp_011"], "ReLU、Sigmoid、Tanh、GELU"),
    KnowledgePoint("kp_028", "BatchNorm与归一化", "深度学习", 1.0, ["kp_011"], "BN、LN、梯度稳定性"),

    # ---- 优化算法 (Optimization) ----
    KnowledgePoint("kp_016", "梯度下降", "优化算法", 0.5, ["kp_005"], "SGD、批量梯度下降、mini-batch"),
    KnowledgePoint("kp_017", "反向传播", "优化算法", 1.0, ["kp_011", "kp_016"], "链式法则求导、计算图"),
    KnowledgePoint("kp_018", "Adam优化器", "优化算法", 1.0, ["kp_016"], "动量、自适应学习率"),
    KnowledgePoint("kp_019", "正则化L1/L2/Dropout", "优化算法", 0.5, ["kp_008"], "权重衰减、Dropout、Early Stopping"),
    KnowledgePoint("kp_020", "学习率调度", "优化算法", 1.0, ["kp_016"], "Warmup、余弦退火、Reduce-on-Plateau"),
    KnowledgePoint("kp_029", "损失函数", "优化算法", 0.5, ["kp_003"], "MSE、CE、Focal Loss、对比损失"),

    # ---- 实践应用 (Practice) ----
    KnowledgePoint("kp_021", "数据预处理", "实践应用", 0.0, [], "清洗、归一化、缺失值处理"),
    KnowledgePoint("kp_022", "特征工程", "实践应用", 0.5, ["kp_021"], "特征选择、编码、构造衍生特征"),
    KnowledgePoint("kp_023", "模型调参", "实践应用", 1.0, ["kp_009", "kp_019"], "网格搜索、贝叶斯优化、超参数调优"),
    KnowledgePoint("kp_024", "模型部署", "实践应用", 1.5, ["kp_023"], "模型量化、ONNX、推理优化、服务化"),
    KnowledgePoint("kp_025", "模型评估与AB测试", "实践应用", 1.0, ["kp_010"], "离线评估、在线AB实验、指标监控"),
    KnowledgePoint("kp_030", "数据增强", "实践应用", 0.5, ["kp_022"], "图像增强、文本增强、Mixup、CutMix"),
]


class KnowledgeGraph:
    """知识图谱管理器"""

    def __init__(self, points: List[KnowledgePoint] | None = None, chapters: List[Chapter] | None = None):
        self.points = points if points is not None else KNOWLEDGE_POINTS
        self.chapters = chapters if chapters is not None else CHAPTERS
        self._index: Dict[str, KnowledgePoint] = {kp.id: kp for kp in self.points}
        self._chapter_index: Dict[str, Chapter] = {ch.chapter_id: ch for ch in self.chapters}
        self._domain_index: Dict[str, List[str]] = {}
        for kp in self.points:
            self._domain_index.setdefault(kp.domain, []).append(kp.id)

    def get(self, kp_id: str) -> KnowledgePoint | None:
        return self._index.get(kp_id)

    def get_chapter(self, chapter_id: str) -> Chapter | None:
        return self._chapter_index.get(chapter_id)

    def all_ids(self) -> List[str]:
        return list(self._index.keys())

    def domains(self) -> List[str]:
        return list(self._domain_index.keys())

    def domain_kp_ids(self, domain: str) -> List[str]:
        return self._domain_index.get(domain, [])

    def prerequisites(self, kp_id: str) -> List[str]:
        kp = self._index.get(kp_id)
        return kp.prerequisites if kp else []

    def all_prerequisites(self, kp_id: str) -> List[str]:
        """递归获取所有前置依赖"""
        result: List[str] = []
        seen = set()
        queue = list(self.prerequisites(kp_id))
        while queue:
            pid = queue.pop(0)
            if pid in seen:
                continue
            seen.add(pid)
            result.append(pid)
            queue.extend(self.prerequisites(pid))
        return result

    def get_chapter_successors(self, chapter_id: str) -> List[Chapter]:
        """获取某章节的后继章节对象列表"""
        ch = self._chapter_index.get(chapter_id)
        if not ch:
            return []
        return [self._chapter_index[cid] for cid in ch.successor_chapter_ids if cid in self._chapter_index]

    def to_dict_list(self) -> List[dict]:
        """序列化为字典列表"""
        return [
            {
                "id": kp.id,
                "name": kp.name,
                "domain": kp.domain,
                "difficulty": kp.difficulty,
                "prerequisites": kp.prerequisites,
                "description": kp.description,
            }
            for kp in self.points
        ]

    def chapters_to_dict(self) -> List[dict]:
        """序列化章节为字典列表"""
        return [
            {
                "chapter_id": ch.chapter_id,
                "chapter_name": ch.chapter_name,
                "chapter_order": ch.chapter_order,
                "primary_kp_id": ch.primary_kp_id,
                "predecessor_kp_ids": ch.predecessor_kp_ids,
                "co_requisite_kp_ids": ch.co_requisite_kp_ids,
                "successor_chapter_ids": ch.successor_chapter_ids,
                "estimated_hours": ch.estimated_hours,
            }
            for ch in self.chapters
        ]


# 全局单例
KG = KnowledgeGraph()
