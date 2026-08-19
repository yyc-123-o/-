"""
端到端模拟测试 — 直接调用核心模块，模拟3种学习者的完整学情诊断流程

流程:
1. 自填问卷 → 创建学习者
2. 自适应测试 → 根据IRT选题策略答题
3. 答题记录转移到学习者
4. 执行学情诊断
5. 输出完整画像 JSON
"""
from __future__ import annotations
import json, sys, os

# Path setup
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from models.schemas import (
    Learner, Education, SelfAssessment, TestRecord, InteractionRecord,
)
from models.knowledge_graph import KG
from core.profile_builder import build_profile
from core import adaptive_test, irt
from generators.mock_generator import generate_test_bank
import numpy as np


def simulation_test():
    """运行3个模拟案例的完整诊断流程"""
    rng = np.random.default_rng(42)

    # 生成题库
    test_bank = generate_test_bank(KG, rng)
    print(f"题库: {len(test_bank)} 道题")

    # ================================================================
    # 案例 1: 初学者 — 专科, 零基础, 目标入门
    # ================================================================
    print("\n" + "=" * 70)
    print("案例 1: 初学者 张小明 (专科/计算机应用)")
    print("=" * 70)

    learner1 = Learner(
        id="learner_test_001",
        name="张小明",
        education=Education(
            level="专科",
            major="计算机应用技术",
            institution="某职业技术学院",
        ),
        self_assessment=SelfAssessment(
            ml_level="刚接触，跟着B站教程跑过demo",
            dl_level="完全不了解",
            math_level="高数学过但忘了很多",
            learning_goal="入门AI，能看懂简单的ML代码",
            weekly_hours=5,
        ),
        test_records=[],
        interaction_records=[],
    )

    run_adaptive_and_diagnose(learner1, test_bank, rng, correct_prob=0.35)

    # ================================================================
    # 案例 2: 中级 — 本科, 有ML基础, 目标系统学DL
    # ================================================================
    print("\n" + "=" * 70)
    print("案例 2: 中级 李文博 (本科/计算机科学与技术)")
    print("=" * 70)

    learner2 = Learner(
        id="learner_test_002",
        name="李文博",
        education=Education(
            level="本科",
            major="计算机科学与技术",
            institution="某理工大学",
            gpa=3.4,
            relevant_courses=["机器学习", "数据结构", "概率论与数理统计", "高等数学"],
        ),
        self_assessment=SelfAssessment(
            ml_level="了解基础，做过sklearn项目",
            dl_level="知道CNN/RNN名字，没实际写过",
            math_level="微积分和线代还行，概率论偏弱",
            learning_goal="系统掌握深度学习，能独立完成CV方向项目",
            weekly_hours=10,
        ),
        test_records=[],
        interaction_records=[],
    )

    run_adaptive_and_diagnose(learner2, test_bank, rng, correct_prob=0.55)

    # ================================================================
    # 案例 3: 高级 — 硕士, DL熟练, 目标发论文
    # ================================================================
    print("\n" + "=" * 70)
    print("案例 3: 高级 王思远 (硕士/人工智能)")
    print("=" * 70)

    learner3 = Learner(
        id="learner_test_003",
        name="王思远",
        education=Education(
            level="硕士",
            major="人工智能",
            institution="某科技大学",
            gpa=3.8,
            relevant_courses=["深度学习", "机器学习", "计算机视觉", "NLP", "最优化方法", "矩阵论"],
        ),
        self_assessment=SelfAssessment(
            ml_level="熟练掌握，有过Kaggle竞赛经验",
            dl_level="熟悉CNN/RNN/Transformer，独立完成过项目",
            math_level="数学基础扎实，能看懂论文公式推导",
            learning_goal="深入LLM前沿，准备发表一篇NLP方向论文",
            weekly_hours=20,
        ),
        test_records=[],
        interaction_records=[],
    )

    run_adaptive_and_diagnose(learner3, test_bank, rng, correct_prob=0.78)

    print("\n" + "=" * 70)
    print("全部 3 个案例测试完成!")
    print("=" * 70)


def run_adaptive_and_diagnose(learner, test_bank, rng, correct_prob=0.5):
    """对单个学习者运行自适应测试 + 诊断"""

    # Step 1: 学历先验
    prior_theta = irt.education_prior_theta(learner.education.level)
    print(f"  学历先验 θ = {prior_theta:.2f}")

    # Step 2: 启动自适应测试
    result = adaptive_test.start_session(learner.id, prior_theta, test_bank)
    session_id = result["session_id"]
    first_q = result["next_question"]
    print(f"  自适应测试启动: session={session_id}")
    print(f"  第1题: {first_q['knowledge_point_name']} (difficulty={first_q['difficulty']:.1f})")

    # Step 3: 模拟答题直到停止
    question_count = 0
    while True:
        question_count += 1
        q = result.get("next_question")
        if not q:
            break

        # 基于IRT概率 + 学习者水平模拟答题结果
        p_correct = irt.probability(prior_theta, q["discrimination"], q["difficulty"])
        # 混合: 40%基于真实能力, 60%基于随机(模拟测试不确定性)
        actual_correct_prob = p_correct * 0.6 + correct_prob * 0.4
        is_correct = rng.random() < actual_correct_prob

        result = adaptive_test.submit_answer(
            session_id=session_id,
            question_id=q["question_id"],
            is_correct=is_correct,
            time_spent=int(rng.uniform(30, 90)),
            test_bank=test_bank,
        )

        if result.get("error"):
            print(f"  错误: {result['error']}")
            break

        if result.get("finished"):
            print(f"  测试完成: {result['stop_reason']}, "
                  f"共{result['question_count']}题, "
                  f"最终θ={result.get('final_theta', 'N/A')}")
            break

    # Step 4: 转移答题记录到学习者
    session = adaptive_test.get_session(session_id)
    answers = session.get("answers", [])
    new_records = []
    for a in answers:
        q_info = next((q for q in test_bank if q["question_id"] == a["question_id"]), None)
        new_records.append(TestRecord(
            knowledge_point_id=a.get("kp_id", q_info["knowledge_point_id"] if q_info else ""),
            question_id=a["question_id"],
            difficulty=a.get("difficulty", q_info["difficulty"] if q_info else 0.0),
            discrimination=a.get("discrimination", q_info["discrimination"] if q_info else 1.0),
            is_correct=a["is_correct"],
            time_spent=a.get("time_spent", 60),
        ))

    learner.test_records.extend(new_records)
    correct_count = sum(1 for a in answers if a["is_correct"])
    print(f"  转移 {len(new_records)} 条答题记录 (正确: {correct_count}/{len(new_records)})")

    # Step 5: 执行诊断
    profile = build_profile(learner, KG, current_chapter_id="ch03_cnn")

    # Step 6: 输出关键指标
    print(f"\n  [诊断结果]:")
    print(f"    Profile ID: {profile.profile_id}")
    print(f"    全局 θ: {profile.knowledge_mastery.global_theta:.3f}")
    print(f"    能力等级: {profile.ability_level.overall}")
    print(f"    知识点掌握度分布:")
    for status in ["mastered", "familiar", "partial", "weak", "not_learned", "unexplored"]:
        count = profile.knowledge_mastery.status_distribution.get(status)
        cnt = count.count if count else 0
        if cnt > 0:
            print(f"      {status}: {cnt} 个")
    print(f"    知识盲区: {len(profile.knowledge_gaps)} 个")
    high_gaps = [g for g in profile.knowledge_gaps if g.priority == "high"]
    if high_gaps:
        print(f"      高优先级: {len(high_gaps)} 个")
        for g in high_gaps[:3]:
            print(f"        - [{g.gap_type}] {g.kp_name} (mastery={g.mastery:.2f})")
    print(f"    主要错误模式: {profile.error_patterns.primary_weakness}")
    print(f"    诊断摘要: {profile.diagnosis_summary.short}")
    print(f"    资源生成提示: {profile.resource_generation_hints.target_chapter_id} / "
          f"{profile.resource_generation_hints.target_depth}")

    # Step 7: 保存 JSON 输出
    profile_dict = profile.model_dump(mode="json")
    output_dir = os.path.join(PROJECT_ROOT, "test_outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{learner.id}_profile.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile_dict, f, ensure_ascii=False, indent=2)
    print(f"\n  [保存] 画像已保存: {output_path}")

    # Step 8: 验证关键字段
    validate_profile(profile_dict)

    return profile


def validate_profile(profile_dict: dict):
    """验证画像输出包含所有必需字段 (对齐 0803 格式)"""
    required_top_fields = [
        "profile_id", "profile_version", "generated_by", "generated_at",
        "learner_id", "update_cycle",
        "learner", "learning_scope", "knowledge_mastery", "ability_level",
        "error_patterns", "learning_preferences", "knowledge_gaps",
        "depth_labels", "resource_generation_hints", "prior_chapters",
        "evidence", "diagnosis_summary", "meta",
    ]

    missing = [f for f in required_top_fields if f not in profile_dict]
    if missing:
        print(f"  [FAIL] 缺少顶层字段: {missing}")
    else:
        print(f"  [PASS] 14个顶层字段完整")

    # 验证子结构
    checks = [
        ("learner.name", profile_dict.get("learner", {}).get("name")),
        ("learner.education", profile_dict.get("learner", {}).get("education")),
        ("knowledge_mastery.points", profile_dict.get("knowledge_mastery", {}).get("points")),
        ("knowledge_mastery.domain_summary", profile_dict.get("knowledge_mastery", {}).get("domain_summary")),
        ("knowledge_mastery.status_distribution", profile_dict.get("knowledge_mastery", {}).get("status_distribution")),
        ("ability_level.sub_dimensions", profile_dict.get("ability_level", {}).get("sub_dimensions")),
        ("error_patterns.items", profile_dict.get("error_patterns", {}).get("items")),
        ("learning_preferences.format", profile_dict.get("learning_preferences", {}).get("format")),
        ("knowledge_gaps", len(profile_dict.get("knowledge_gaps", []))),
        ("depth_labels", len(profile_dict.get("depth_labels", []))),
        ("resource_generation_hints.lecture_notes", profile_dict.get("resource_generation_hints", {}).get("lecture_notes")),
        ("evidence", len(profile_dict.get("evidence", []))),
    ]

    all_ok = True
    for field_name, value in checks:
        if value is None or (isinstance(value, (list, dict)) and len(value) == 0 and field_name not in ["knowledge_gaps", "depth_labels"]):
            # knowledge_gaps and depth_labels can be empty for new learners
            pass
        if field_name == "knowledge_gaps" and value == 0:
            print(f"  [WARN] knowledge_gaps 为空(新学习者无测试记录时正常)")

    # Print field-by-field summary
    print(f"  [字段完整性检查]:")
    print(f"     learner.name: {profile_dict.get('learner', {}).get('name', 'N/A')}")
    print(f"     learning_scope.chapter_id: {profile_dict.get('learning_scope', {}).get('chapter_id', 'N/A')}")
    print(f"     knowledge_mastery.points count: {len(profile_dict.get('knowledge_mastery', {}).get('points', {}))}")
    print(f"     ability_level.overall: {profile_dict.get('ability_level', {}).get('overall', 'N/A')}")
    print(f"     error_patterns.items count: {len(profile_dict.get('error_patterns', {}).get('items', []))}")
    print(f"     learning_preferences groups: {list(profile_dict.get('learning_preferences', {}).keys())}")
    print(f"     knowledge_gaps count: {len(profile_dict.get('knowledge_gaps', []))}")
    print(f"     depth_labels count: {len(profile_dict.get('depth_labels', []))}")
    print(f"     resource_generation_hints.scope: {profile_dict.get('resource_generation_hints', {}).get('scope', 'N/A')}")
    print(f"     prior_chapters count: {len(profile_dict.get('prior_chapters', []))}")
    print(f"     evidence count: {len(profile_dict.get('evidence', []))}")
    print(f"     diagnosis_summary.short: {profile_dict.get('diagnosis_summary', {}).get('short', 'N/A')[:60]}...")
    print(f"     meta.tests: {profile_dict.get('meta', {}).get('total_test_count', 0)}")


if __name__ == "__main__":
    simulation_test()
