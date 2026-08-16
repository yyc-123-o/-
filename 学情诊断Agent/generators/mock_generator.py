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

from models.schemas import Learner, Education, SelfAssessment, TestRecord, InteractionRecord
from models.knowledge_graph import KG, KnowledgePoint

# 错题时的错误模式候选
_ERROR_PATTERNS = ["概念混淆", "计算错误", "逻辑跳跃", "忽略条件"]


# ============================================================
# 测试题库生成
# ============================================================

def _load_real_questions() -> List[dict]:
    """从 JSON 文件加载真实题目"""
    qfile = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "real_questions.json")
    if os.path.exists(qfile):
        with open(qfile, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def generate_test_bank(kg: KnowledgeGraph, rng: np.random.Generator) -> List[dict]:
    """生成测试题库 — 优先使用真实题目，不足时自动生成补充"""
    real = _load_real_questions()
    real_ids = {q["question_id"] for q in real}
    bank = list(real)

    # 为没有真实题目的知识点生成补充题
    covered_kps = {q["knowledge_point_id"] for q in bank}
    for kp in kg.points:
        if kp.id not in covered_kps:
            for i in range(3):
                qid = f"q_{kp.id}_{i+1}"
                if qid not in real_ids:
                    difficulty = round(kp.difficulty + rng.uniform(-0.5, 0.5), 2)
                    discrimination = round(rng.uniform(0.6, 1.4), 2)
                    bank.append({
                        "question_id": qid,
                        "knowledge_point_id": kp.id,
                        "knowledge_point_name": kp.name,
                        "domain": kp.domain,
                        "difficulty": difficulty,
                        "discrimination": discrimination,
                        "question_text": f"请回答关于「{kp.name}」的相关问题。（难度 {difficulty:.1f}）",
                        "options": ["选项A", "选项B", "选项C", "选项D"],
                        "correct_answer": 0,
                    })

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
        is_correct = _bernoulli(p_correct, rng)

        # 答题时间: 答对通常快一些, 高难度题耗时更长
        base_time = 30 + difficulty * 15
        if is_correct:
            time_spent = int(base_time * rng.uniform(0.7, 1.0))
        else:
            time_spent = int(base_time * rng.uniform(1.0, 1.8))

        # 提示使用: 能力低或难度高时更可能用提示
        hint_prob = max(0.05, 0.3 - theta * 0.15 + max(0, difficulty - theta) * 0.2)
        hint_used = _bernoulli(hint_prob, rng)

        # 错题标注错误模式
        error_pattern = None
        if not is_correct and rng.random() < 0.6:
            error_pattern = rng.choice(_ERROR_PATTERNS)

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
        ml_level="刚接触，跟着B站教程跑过demo",
        dl_level="完全不了解",
        math_level="高数学过但忘了很多",
        learning_goal="入门AI，能看懂简单的ML代码",
        weekly_hours=5,
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
        ml_level="了解基础，做过sklearn项目",
        dl_level="知道CNN/RNN名字，没实际写过",
        math_level="微积分和线代还行，概率论偏弱",
        learning_goal="系统掌握深度学习，能独立完成CV方向项目",
        weekly_hours=10,
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
        ml_level="熟练掌握，有过Kaggle竞赛经验",
        dl_level="熟悉CNN/RNN/Transformer，独立完成过项目",
        math_level="数学基础扎实，能看懂论文公式推导",
        learning_goal="深入LLM前沿，准备发表一篇NLP方向论文",
        weekly_hours=20,
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
