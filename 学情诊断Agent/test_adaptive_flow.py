"""验证新的自适应测试引擎（按领域分类 + 先易后难 + 困难定级）"""
from core import adaptive_test
from models.knowledge_graph import KG
from generators.mock_generator import generate_test_bank
import numpy as np

rng = np.random.default_rng(7)
bank = generate_test_bank(KG, np.random.default_rng(42))

# 模拟三个不同水平的学习者
for name, correct_prob in [("初学", 0.35), ("中级", 0.65), ("高级", 0.85)]:
    r = adaptive_test.start_session(name, 0.0, bank)
    sid = r["session_id"]
    switches = 0
    for i in range(80):
        q = r.get("next_question")
        if r.get("finished"):
            break
        if not q:
            break
        is_correct = rng.random() < correct_prob
        r = adaptive_test.submit_answer(sid, q["question_id"], is_correct, 45, bank)
        if r.get("domain_finished"):
            switches += 1

    print(f"\n=== {name}（正确率 {correct_prob}）===")
    print(f"总题数: {r.get('question_count')} | 完成: {r.get('finished')}")
    if r.get("finished"):
        print(f"综合θ: {r.get('final_theta')}")
        for dr in r.get("domain_results", []):
            print(f"  {dr['domain']}: {dr['level']}（对{dr['correct']}/错{dr['wrong']}，{dr['reason']}）")
    else:
        print("  未完成（可能题目不足）")
        print("  当前领域:", r.get("current_domain"))
