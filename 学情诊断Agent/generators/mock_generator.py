"""模拟数据生成器 — 生成3组差异化学习者数据

学习者类型:
1. 初学者: 专科, 能力θ≈-0.5, 正确率低, 交互少
2. 中级:   本科, 能力θ≈0.3, 正确率中等, 交互适中
3. 高级:   硕士, 能力θ≈0.8, 正确率高, 交互活跃
"""

from __future__ import annotations
import json
import os
import sys
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from models.schemas import (
    Learner, Education, SelfAssessment, TestRecord, InteractionRecord,
    CourseSelfAssessment, DomainAssessment, ProjectExperience,
)
from models.knowledge_graph import KG, KnowledgePoint

# 错题时的错误模式候选
_ERROR_PATTERNS = ["概念混淆", "计算错误", "逻辑跳跃", "忽略条件"]

# 难度档 (IRT b) → 三级标注
_TIER_LABEL = {"easy": "易", "medium": "中", "hard": "难"}


# ============================================================
# 测试题库生成
# ============================================================

def _load_real_questions() -> List[dict]:
    """从 JSON 文件加载真实题目

    优先读取完整知识库 question_bank.json (含 difficulty_level 低/中/高 分类);
    若不存在则回退到 real_questions.json。
    """
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    primary = os.path.join(data_dir, "question_bank.json")
    fallback = os.path.join(data_dir, "real_questions.json")
    for qfile in (primary, fallback):
        if os.path.exists(qfile):
            with open(qfile, "r", encoding="utf-8") as f:
                return json.load(f)
    return []


def _difficulty_tier(difficulty: float) -> str:
    """根据 IRT b 值划分难度档 — 与自适应测试的难度梯度档位保持一致

    易: b ≤ -0.2 / 中: -0.2 < b ≤ 0.8 / 难: b > 0.8
    """
    if difficulty <= -0.2:
        return "easy"
    elif difficulty <= 0.8:
        return "medium"
    return "hard"


def generate_test_bank(kg: KnowledgeGraph, rng: np.random.Generator) -> List[dict]:
    """生成测试题库 — 加载真实题目并附加难度档标注

    题库在 data/real_questions.json 中已覆盖全部知识点;
    若有遗漏仅打印警告, 不再生成占位符题。
    """
    real = _load_real_questions()
    bank = []
    for q in real:
        item = dict(q)
        item["level"] = _difficulty_tier(item.get("difficulty", 0.0))
        item["level_label"] = _TIER_LABEL[item["level"]]
        bank.append(item)

    covered_kps = {q["knowledge_point_id"] for q in bank}
    missing = [kp.id for kp in kg.points if kp.id not in covered_kps]
    if missing:
        print(f"[题库] 警告: 以下知识点缺少真实题目: {missing}")

    return bank


# ============================================================
# 学习者数据生成
# ============================================================

def _bernoulli(p: float, rng: np.random.Generator) -> bool:
    """以概率p返回True"""
    return rng.random() < p


def _generate_test_records_for_kp(
    kp: KnowledgePoint,
    theta: float,
    n_questions: int,
    rng: np.random.Generator,
    start_time: datetime,
) -> List[TestRecord]:
    """为单个知识点生成测试记录"""
    records: List[TestRecord] = []
    for i in range(n_questions):
        difficulty = round(kp.difficulty + rng.uniform(-0.4, 0.4), 2)
        discrimination = round(rng.uniform(0.6, 1.4), 2)
        # IRT概率
        from core.irt import probability
        p_correct = probability(theta, discrimination, difficulty)
        is_correct = bool(_bernoulli(p_correct, rng))

        # 答题时间: 答对通常快一些, 高难度题耗时更长
        base_time = 30 + difficulty * 15
        if is_correct:
            time_spent = int(base_time * rng.uniform(0.7, 1.0))
        else:
            time_spent = int(base_time * rng.uniform(1.0, 1.8))

        # 提示使用: 能力低或难度高时更可能用提示
        hint_prob = max(0.05, 0.3 - theta * 0.15 + max(0, difficulty - theta) * 0.2)
        hint_used = bool(_bernoulli(hint_prob, rng))

        # 错题标注错误模式
        error_pattern = None
        if not is_correct and rng.random() < 0.6:
            error_pattern = str(rng.choice(_ERROR_PATTERNS))

        records.append(TestRecord(
            knowledge_point_id=kp.id,
            question_id=f"q_{kp.id}_{i+1}",
            difficulty=difficulty,
            discrimination=discrimination,
            is_correct=is_correct,
            timestamp=start_time + timedelta(minutes=i * 3),
            time_spent=min(time_spent, 300),
            hint_used=hint_used,
            error_pattern=error_pattern,
        ))
    return records


def _generate_interactions_for_kp(
    kp: KnowledgePoint,
    theta: float,
    n_interactions: int,
    rng: np.random.Generator,
    start_time: datetime,
) -> List[InteractionRecord]:
    """为单个知识点生成交互记录"""
    records: List[InteractionRecord] = []
    interaction_types = ["view", "practice", "discussion", "quiz"]

    for i in range(n_interactions):
        # 偏好类型: 能力低更多view, 能力高更多practice
        if theta < 0:
            type_weights = [0.5, 0.2, 0.1, 0.2]
        else:
            type_weights = [0.3, 0.4, 0.15, 0.15]
        itype = rng.choice(interaction_types, p=type_weights)

        duration = int(rng.uniform(60, 600))

        records.append(InteractionRecord(
            knowledge_point_id=kp.id,
            type=itype,
            duration=duration,
            timestamp=start_time + timedelta(hours=i * 2),
            detail=f"{itype}: {kp.name}",
        ))
    return records


def generate_learner(
    learner_id: str,
    name: str,
    education: Education,
    target_theta: float,
    kg: KnowledgeGraph,
    rng: np.random.Generator,
    n_tested_kps: int = 15,
    max_questions_per_kp: int = 4,
    interaction_density: float = 0.5,
) -> Learner:
    """生成一个模拟学习者

    Args:
        target_theta: 目标能力θ (决定答题正确率)
        n_tested_kps: 测试的知识点数量
        max_questions_per_kp: 每个知识点最多测试题数
        interaction_density: 交互密度 0~1 (0=少, 1=多)
    """
    # 随机选择要测试的知识点
    all_kp_ids = kg.all_ids()
    tested_kp_ids = rng.choice(all_kp_ids, size=min(n_tested_kps, len(all_kp_ids)), replace=False)

    start_time = datetime(2026, 6, 15, 9, 0)

    all_tests: List[TestRecord] = []
    all_interactions: List[InteractionRecord] = []

    for kp_id in tested_kp_ids:
        kp = kg.get(kp_id)
        if not kp:
            continue

        # 题目数量: 2~max
        n_q = int(rng.integers(2, max_questions_per_kp + 1))
        tests = _generate_test_records_for_kp(kp, target_theta, n_q, rng, start_time)
        all_tests.extend(tests)

        # 交互记录: 按密度生成
        if rng.random() < interaction_density:
            n_inter = int(rng.integers(1, 5))
            interactions = _generate_interactions_for_kp(kp, target_theta, n_inter, rng, start_time)
            all_interactions.extend(interactions)

        # 时间推进
        start_time += timedelta(days=1)

    return Learner(
        id=learner_id,
        name=name,
        education=education,
        test_records=all_tests,
        interaction_records=all_interactions,
    )


def generate_all_mock_data() -> Tuple[List[Learner], List[dict]]:
    """生成全部模拟数据: 3组学习者 + 测试题库"""
    rng = np.random.default_rng(42)

    # 测试题库
    test_bank = generate_test_bank(KG, rng)

    # 学习者1: 初学者
    learner1 = generate_learner(
        learner_id="learner_001",
        name="张小明",
        education=Education(
            level="专科",
            major="计算机应用技术",
            institution="某职业技术学院",
            graduation_year=2025,
            relevant_courses=["Python程序设计", "数据结构基础"],
        ),
        target_theta=-0.5,
        kg=KG,
        rng=rng,
        n_tested_kps=15,
        max_questions_per_kp=3,
        interaction_density=0.4,
    )
    learner1.self_assessment = SelfAssessment(
        learning_goal="入门AI，能看懂简单的ML代码",
        weekly_hours=5,
        domain_assessments=[
            DomainAssessment(domain="数学基础", note="数学基础薄弱，概率论与线代几乎遗忘", courses=[
                CourseSelfAssessment(name="高等数学", level="入门", note="学过但忘了很多"),
                CourseSelfAssessment(name="线性代数", level="未学过", note=""),
                CourseSelfAssessment(name="概率论与数理统计", level="未学过", note=""),
                CourseSelfAssessment(name="最优化方法", level="未学过", note=""),
            ]),
            DomainAssessment(domain="机器学习基础", note="跑过demo，了解基本概念", courses=[
                CourseSelfAssessment(name="机器学习", level="入门", note="跑过demo"),
                CourseSelfAssessment(name="数据结构与算法", level="入门", note="了解数组/链表"),
            ]),
            DomainAssessment(domain="深度学习", note="零基础", courses=[
                CourseSelfAssessment(name="深度学习", level="未学过", note=""),
                CourseSelfAssessment(name="计算机视觉", level="未学过", note=""),
                CourseSelfAssessment(name="自然语言处理", level="未学过", note=""),
            ]),
            DomainAssessment(domain="优化算法", note="未接触", courses=[
                CourseSelfAssessment(name="最优化方法", level="未学过", note=""),
                CourseSelfAssessment(name="凸优化", level="未学过", note=""),
            ]),
            DomainAssessment(domain="实践应用", note="能写简单Python脚本", courses=[
                CourseSelfAssessment(name="Python编程", level="基础", note="能写简单脚本"),
                CourseSelfAssessment(name="数据处理与特征工程", level="未学过", note=""),
                CourseSelfAssessment(name="模型调参与部署", level="未学过", note=""),
            ]),
        ],
        projects=[],
    )

    # 学习者2: 中级
    learner2 = generate_learner(
        learner_id="learner_002",
        name="李文博",
        education=Education(
            level="本科",
            major="计算机科学与技术",
            institution="某理工大学",
            graduation_year=2025,
            gpa=3.4,
            relevant_courses=["机器学习", "数据结构", "概率论与数理统计", "高等数学"],
        ),
        target_theta=0.3,
        kg=KG,
        rng=rng,
        n_tested_kps=20,
        max_questions_per_kp=4,
        interaction_density=0.6,
    )
    learner2.self_assessment = SelfAssessment(
        learning_goal="系统掌握深度学习，能独立完成CV方向项目",
        weekly_hours=10,
        domain_assessments=[
            DomainAssessment(domain="数学基础", note="微积分和线代尚可，概率论偏弱", courses=[
                CourseSelfAssessment(name="高等数学", level="基础", note="微积分基本掌握"),
                CourseSelfAssessment(name="线性代数", level="基础", note="矩阵运算熟练"),
                CourseSelfAssessment(name="概率论与数理统计", level="入门", note="偏弱"),
                CourseSelfAssessment(name="最优化方法", level="入门", note=""),
            ]),
            DomainAssessment(domain="机器学习基础", note="会特征工程与调参", courses=[
                CourseSelfAssessment(name="机器学习", level="基础", note="会线性回归/分类/聚类"),
                CourseSelfAssessment(name="数据结构与算法", level="基础", note=""),
            ]),
            DomainAssessment(domain="深度学习", note="只懂概念、缺乏代码实操", courses=[
                CourseSelfAssessment(name="深度学习", level="入门", note="只懂CNN/RNN概念"),
                CourseSelfAssessment(name="计算机视觉", level="未学过", note=""),
                CourseSelfAssessment(name="自然语言处理", level="未学过", note=""),
            ]),
            DomainAssessment(domain="优化算法", note="基础优化方法入门", courses=[
                CourseSelfAssessment(name="最优化方法", level="入门", note=""),
                CourseSelfAssessment(name="凸优化", level="未学过", note=""),
            ]),
            DomainAssessment(domain="实践应用", note="能独立完成sklearn项目", courses=[
                CourseSelfAssessment(name="Python编程", level="熟练", note="做过sklearn项目"),
                CourseSelfAssessment(name="数据处理与特征工程", level="基础", note=""),
                CourseSelfAssessment(name="模型调参与部署", level="入门", note=""),
            ]),
        ],
        projects=[
            ProjectExperience(name="房价预测回归分析", role="独立完成",
                              description="基于sklearn的房价预测，含数据清洗、特征工程、网格搜索调参",
                              tech_stack=["Python", "scikit-learn", "pandas"], duration_months=2),
            ProjectExperience(name="新闻文本分类", role="合作者",
                              description="用朴素贝叶斯和TF-IDF做新闻分类，负责数据预处理",
                              tech_stack=["Python", "jieba", "scikit-learn"], duration_months=1),
        ],
    )

    # 学习者3: 高级
    learner3 = generate_learner(
        learner_id="learner_003",
        name="王思远",
        education=Education(
            level="硕士",
            major="人工智能",
            institution="某科技大学",
            graduation_year=2025,
            gpa=3.8,
            relevant_courses=["深度学习", "机器学习", "计算机视觉", "自然语言处理", "最优化方法", "矩阵论"],
        ),
        target_theta=0.8,
        kg=KG,
        rng=rng,
        n_tested_kps=25,
        max_questions_per_kp=4,
        interaction_density=0.8,
    )
    learner3.self_assessment = SelfAssessment(
        learning_goal="深入LLM前沿，准备发表一篇NLP方向论文",
        weekly_hours=20,
        domain_assessments=[
            DomainAssessment(domain="数学基础", note="数学基础扎实，能推公式", courses=[
                CourseSelfAssessment(name="高等数学", level="熟练", note="能看懂论文公式推导"),
                CourseSelfAssessment(name="线性代数", level="熟练", note="矩阵分解/特征分解熟练"),
                CourseSelfAssessment(name="概率论与数理统计", level="熟练", note=""),
                CourseSelfAssessment(name="最优化方法", level="基础", note=""),
            ]),
            DomainAssessment(domain="机器学习基础", note="有Kaggle竞赛经验", courses=[
                CourseSelfAssessment(name="机器学习", level="熟练", note="有Kaggle经验"),
                CourseSelfAssessment(name="数据结构与算法", level="熟练", note=""),
            ]),
            DomainAssessment(domain="深度学习", note="熟悉CNN/RNN/Transformer", courses=[
                CourseSelfAssessment(name="深度学习", level="熟练", note="独立完成过CV/NLP项目"),
                CourseSelfAssessment(name="计算机视觉", level="熟练", note=""),
                CourseSelfAssessment(name="自然语言处理", level="熟练", note=""),
            ]),
            DomainAssessment(domain="优化算法", note="最优化方法基础扎实", courses=[
                CourseSelfAssessment(name="最优化方法", level="基础", note=""),
                CourseSelfAssessment(name="凸优化", level="基础", note=""),
            ]),
            DomainAssessment(domain="实践应用", note="有竞赛与项目经验，部署经验较少", courses=[
                CourseSelfAssessment(name="Python编程", level="精通", note=""),
                CourseSelfAssessment(name="数据处理与特征工程", level="熟练", note=""),
                CourseSelfAssessment(name="模型调参与部署", level="熟练", note=""),
            ]),
        ],
        projects=[
            ProjectExperience(name="Kaggle图像分割竞赛", role="队长",
                              description="基于U-Net/DeepLab的医学图像分割，Top 5%",
                              tech_stack=["Python", "PyTorch", "segmentation_models"], duration_months=3),
            ProjectExperience(name="基于Transformer的文本分类", role="独立完成",
                              description="用BERT微调做多分类，含数据增强与对抗训练",
                              tech_stack=["Python", "PyTorch", "transformers"], duration_months=2),
        ],
    )

    return [learner1, learner2, learner3], test_bank


def save_mock_data(data_dir: str):
    """生成并保存模拟数据到JSON文件"""
    os.makedirs(data_dir, exist_ok=True)
    learners, test_bank = generate_all_mock_data()

    # 保存测试题库
    with open(os.path.join(data_dir, "test_bank.json"), "w", encoding="utf-8") as f:
        json.dump(test_bank, f, ensure_ascii=False, indent=2)

    # 保存学习者数据
    mock_dir = os.path.join(data_dir, "mock_learners")
    os.makedirs(mock_dir, exist_ok=True)

    for learner in learners:
        filepath = os.path.join(mock_dir, f"{learner.id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(learner.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    # 同时保存知识图谱
    with open(os.path.join(data_dir, "knowledge_points.json"), "w", encoding="utf-8") as f:
        json.dump(KG.to_dict_list(), f, ensure_ascii=False, indent=2)

    return learners, test_bank


if __name__ == "__main__":
    import sys
    # 添加项目根目录到路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    data_dir = os.path.join(project_root, "data")
    learners, bank = save_mock_data(data_dir)
    print(f"已生成 {len(learners)} 组学习者数据, {len(bank)} 道测试题")
    for l in learners:
        print(f"  - {l.name} ({l.education.level}): {len(l.test_records)}条测试, {len(l.interaction_records)}条交互")
