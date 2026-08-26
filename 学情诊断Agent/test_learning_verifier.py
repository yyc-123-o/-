"""验证学习成果检验 Agent（第二流程）：baseline → 学习 → 复诊 → 对比报告"""
from models.knowledge_graph import KG
from models.schemas import TestRecord
from core.profile_builder import build_profile
from core import learning_verifier
from generators.mock_generator import generate_all_mock_data
import numpy as np

rng = np.random.default_rng(42)
learners, bank = generate_all_mock_data()
learner = learners[1]  # 李文博（中级）

# 1. 第一流程：初始诊断 → baseline 画像
baseline = build_profile(learner, KG, current_chapter_id="ch03_cnn")
print(f"1. Baseline 诊断: θ={baseline.knowledge_mastery.global_theta:.3f}, "
      f"CNN mastery={baseline.knowledge_mastery.points['kp_012'].mastery:.3f}")

# 2. 模拟学习后：追加 CNN 相关答题记录（高正确率，表示学懂了）
new_records = []
for kp_id in ["kp_012", "kp_015", "kp_028", "kp_029", "kp_019"]:
    kp = KG.get(kp_id)
    for i in range(3):  # 每知识点答3题，基本全对
        difficulty = kp.difficulty + rng.uniform(-0.3, 0.3)
        new_records.append(TestRecord(
            knowledge_point_id=kp_id,
            question_id=f"q_learn_{kp_id}_{i}",
            difficulty=difficulty,
            discrimination=1.0,
            is_correct=rng.random() < 0.85,  # 85% 正确率
            time_spent=40,
        ))
learner.test_records.extend(new_records)

# 3. 第二流程：复诊 → post 画像
post = build_profile(learner, KG, current_chapter_id="ch03_cnn")
print(f"3. 复诊画像: θ={post.knowledge_mastery.global_theta:.3f}, "
      f"CNN mastery={post.knowledge_mastery.points['kp_012'].mastery:.3f}")

# 4. 对比 → 学习成果检验报告
report = learning_verifier.compare_profiles(baseline, post, learner.id, "ch03_cnn")
print(f"\n=== 学习成果检验报告 ===")
print(f"综合判定: {report.overall_verdict}")
print(f"θ: {report.theta['before']:.3f} → {report.theta['after']:.3f} (Δ={report.theta['delta']:+.3f})")
print(f"正确率: {report.accuracy['before']:.3f} → {report.accuracy['after']:.3f} (Δ={report.accuracy['delta']:+.3f})")
print(f"能力等级: {report.ability_level['before']} → {report.ability_level['after']}")
print(f"盲区消除: {len(report.gaps_resolved)} 个")
for g in report.gaps_resolved[:3]:
    print(f"  ✓ {g.name}: {g.before:.2f} → {g.after:.2f}")
print(f"盲区持续: {len(report.gaps_remaining)} 个 | 新增盲区: {len(report.gaps_new)} 个")
print(f"\n知识点提升 TOP3:")
for k in report.kp_changes[:3]:
    print(f"  {k.name}: {k.before:.2f} → {k.after:.2f} ({k.delta:+.2f}, {k.category})")
print(f"\n建议: {report.recommendation}")
print("\n=== 学习成果检验 SUCCESS ===")
