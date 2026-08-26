"""题库知识库生成器 — 为题目补充「难度分层」和「解析」分类

每个题目包含以下分类内容:
  1. 涉及的相关知识点 (knowledge_point_id + knowledge_point_name + domain)
  2. 难度分层 (低难度 / 中等难度 / 高难度)
  3. 解析 (explanation)

难度分层规则 (与自适应测试的「易/中/难」三档一致):
  低难度:   b < -0.2       (基础概念 / 定义记忆)
  中等难度: -0.2 <= b <= 0.8 (应用 / 计算)
  高难度:   b > 0.8        (综合分析 / 推导)

运行: python generate_question_bank.py
输出: data/question_bank.json (完整知识库)
"""

from __future__ import annotations
import json
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(PROJECT_ROOT, "data", "real_questions.json")
SUP = os.path.join(PROJECT_ROOT, "data", "supplementary_questions.json")
DST = os.path.join(PROJECT_ROOT, "data", "question_bank.json")

# 难度分层阈值 (与 adaptive_test 的 difficulty_stages 对齐)
LOW_HIGH = -0.2   # 低难度上限
MID_HIGH = 0.8    # 中等难度上限


def classify_difficulty(b: float) -> str:
    """根据 IRT 难度 b 值判定难度分层"""
    if b < LOW_HIGH:
        return "低难度"
    elif b <= MID_HIGH:
        return "中等难度"
    else:
        return "高难度"


# 每个知识点的解析模板 (用于生成 explanation)
_KNOWLEDGE_EXPLANATIONS = {
    "kp_001": "微积分基础",
    "kp_002": "线性代数",
    "kp_003": "概率论",
    "kp_004": "矩阵运算",
    "kp_005": "导数与梯度",
    "kp_006": "监督学习",
    "kp_007": "无监督学习",
    "kp_008": "过拟合与欠拟合",
    "kp_009": "交叉验证",
    "kp_010": "评估指标",
    "kp_011": "神经网络基础",
    "kp_012": "卷积神经网络CNN",
    "kp_013": "循环神经网络RNN/LSTM",
    "kp_014": "Transformer与Attention",
    "kp_015": "激活函数",
    "kp_016": "梯度下降",
    "kp_017": "反向传播",
    "kp_018": "Adam优化器",
    "kp_019": "正则化L1/L2/Dropout",
    "kp_020": "学习率调度",
    "kp_021": "数据预处理",
    "kp_022": "特征工程",
    "kp_023": "模型调参",
    "kp_024": "模型部署",
    "kp_025": "模型评估与AB测试",
    "kp_026": "信息论基础",
    "kp_027": "集成学习",
    "kp_028": "BatchNorm与归一化",
    "kp_029": "损失函数",
    "kp_030": "数据增强",
}


def build_explanation(q: dict) -> str:
    """根据题目生成简洁解析"""
    kp_name = q.get("knowledge_point_name", "")
    correct_idx = q.get("correct_answer", 0)
    options = q.get("options", [])
    correct_opt = options[correct_idx] if 0 <= correct_idx < len(options) else ""
    return f"本题考查「{kp_name}」相关知识，正确答案为「{correct_opt}」。"


def generate():
    with open(SRC, "r", encoding="utf-8") as f:
        questions = json.load(f)

    # 合并补充题目 (补齐各知识点的三档难度)
    if os.path.exists(SUP):
        with open(SUP, "r", encoding="utf-8") as f:
            questions.extend(json.load(f))

    bank = []
    for q in questions:
        b = q.get("difficulty", 0.0)
        level = classify_difficulty(b)
        item = {
            "question_id": q["question_id"],
            "knowledge_point_id": q["knowledge_point_id"],
            "knowledge_point_name": q["knowledge_point_name"],
            "domain": q["domain"],
            "difficulty": b,
            "difficulty_level": level,          # ★ 难度分层
            "discrimination": q.get("discrimination", 1.0),
            "question_text": q["question_text"],
            "options": q["options"],
            "correct_answer": q["correct_answer"],
            "explanation": build_explanation(q),  # ★ 解析
        }
        bank.append(item)

    # 按 domain + knowledge_point_id + difficulty 排序，便于查阅
    bank.sort(key=lambda x: (x["domain"], x["knowledge_point_id"], x["difficulty"]))

    with open(DST, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    # 统计报告
    from collections import Counter
    level_counter = Counter(x["difficulty_level"] for x in bank)
    kp_counter = Counter(x["knowledge_point_id"] for x in bank)
    print(f"知识库已生成: {DST}")
    print(f"题目总数: {len(bank)}")
    print(f"覆盖知识点: {len(kp_counter)} 个")
    print(f"难度分层分布: {dict(level_counter)}")
    print(f"各知识点题数: {dict(sorted(kp_counter.items()))}")


if __name__ == "__main__":
    generate()
