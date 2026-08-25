"""知识盲区分析 — 4种盲区类型 + 置信度 + 典型错例

1. 盲区 (blindspot): mastery < 0.4
2. 薄弱 (weak): 0.4 <= mastery < 0.6
3. 阻塞 (blocked): 前置知识点mastery < 0.5 且当前也低
4. 困难 (difficult): 交互记录反复查看(>=3次)但测试仍不通过

v2.1: 每个盲区输出 confidence + suggested_action + blocks
"""

from __future__ import annotations
from typing import Dict, List
from models.schemas import KnowledgeGap, ErrorPatterns, ErrorPatternItem, TestRecord, InteractionRecord
from models.knowledge_graph import KnowledgeGraph


BLINDSPOT_THRESHOLD = 0.4
WEAK_THRESHOLD = 0.6
BLOCKED_PREREQ_THRESHOLD = 0.5
DIFFICULT_INTERACTION_MIN = 3


def _interaction_count_for_kp(
    kp_id: str,
    interactions: List[InteractionRecord],
) -> int:
    """统计某知识点的交互次数"""
    return sum(1 for i in interactions if i.knowledge_point_id == kp_id)


def _test_pass_rate(
    kp_id: str,
    test_records: List[TestRecord],
) -> float:
    """计算某知识点的测试通过率"""
    kp_tests = [t for t in test_records if t.knowledge_point_id == kp_id]
    if not kp_tests:
        return 0.0
    correct = sum(1 for t in kp_tests if t.is_correct)
    return correct / len(kp_tests)


def _gap_confidence(mastery: float, test_count: int, gap_type: str) -> float:
    """盲区置信度估计"""
    if gap_type == "blindspot":
        if test_count >= 3:
            return 0.85 + min(0.03, (1 - mastery) * 0.02)
        elif test_count >= 1:
            return 0.70 + (1 - mastery) * 0.05
        else:
            return 0.25  # 无直接证据只能建议测评，不能高置信下结论
    elif gap_type == "blocked":
        return 0.86 + min(0.04, test_count * 0.01)
    elif gap_type == "weak":
        return 0.82 + min(0.05, test_count * 0.01)
    elif gap_type == "difficult":
        return 0.81 + min(0.05, (1 - mastery) * 0.03)
    return 0.70


def _generate_suggested_action(
    gap_type: str,
    kp_name: str,
    mastery: float,
    blocked_by: List[str],
    blocks: List[str],
    kg: KnowledgeGraph,
) -> str:
    """生成建议操作"""
    if gap_type == "blindspot":
        if mastery < 0.10:
            return f"远期待学章节，暂不处理"
        return f"当前章节学习目标（首次学习），深度=进阶。若本章正确率<60%则下一章降级"
    elif gap_type == "blocked":
        prereq_names = [kg.get(p).name for p in blocked_by if kg.get(p)]
        if prereq_names:
            return f"前置{', '.join(prereq_names)}未掌握，建议在进入当前模块前安排补充讲义"
        return "前置知识点未掌握，需先巩固基础"
    elif gap_type == "weak":
        if blocks:
            blocked_names = [kg.get(b).name for b in blocks if kg.get(b)]
            return f"后续{'/'.join(blocked_names)}章节前安排快速回顾"
        return "需要巩固提升，安排针对性练习"
    elif gap_type == "difficult":
        return "实操指南中提供完整的代码模板，降低认知负荷"
    return ""


def analyze_gaps(
    kg: KnowledgeGraph,
    mastery_map: Dict[str, float],
    test_records: List[TestRecord],
    interactions: List[InteractionRecord],
    test_count_map: Dict[str, int] | None = None,
) -> List[KnowledgeGap]:
    """分析知识盲区 — 返回 0803 对齐的 KnowledgeGap 列表"""

    if test_count_map is None:
        test_count_map = {}
        for kp in kg.points:
            tc = len([t for t in test_records if t.knowledge_point_id == kp.id])
            test_count_map[kp.id] = tc

    gaps: List[KnowledgeGap] = []

    for kp in kg.points:
        mastery = mastery_map.get(kp.id, 0.0)
        interaction_count = _interaction_count_for_kp(kp.id, interactions)
        pass_rate = _test_pass_rate(kp.id, test_records)
        tc = test_count_map.get(kp.id, 0)

        # 没有测试或交互证据时，不把学历先验误报成已确认盲区。
        if tc == 0 and interaction_count == 0:
            continue

        gap_type = None
        priority = "low"
        description = ""
        blocked_by: List[str] = []
        blocks: List[str] = []

        # 1. 阻塞: 前置知识点未掌握
        prereqs = kg.prerequisites(kp.id)
        weak_prereqs = [p for p in prereqs if mastery_map.get(p, 0.0) < BLOCKED_PREREQ_THRESHOLD]
        if weak_prereqs and mastery < WEAK_THRESHOLD:
            gap_type = "blocked"
            priority = "high"
            prereq_names = [kg.get(p).name for p in weak_prereqs if kg.get(p)]
            description = f"前置知识点未掌握: {', '.join(prereq_names)}, 导致当前知识点学习受阻"
            blocked_by = weak_prereqs

        # 2. 困难: 反复查看但不通过
        elif interaction_count >= DIFFICULT_INTERACTION_MIN and pass_rate < 0.5 and mastery < WEAK_THRESHOLD:
            gap_type = "difficult"
            priority = "medium"
            description = f"交互{interaction_count}次但测试通过率仅{pass_rate:.0%}, 存在理解困难"

        # 3. 盲区: 掌握度极低
        elif mastery < BLINDSPOT_THRESHOLD:
            gap_type = "blindspot"
            priority = "high" if mastery < 0.20 else "medium"
            description = f"掌握度仅{mastery:.0%}, 存在{'严重' if mastery < 0.20 else ''}知识盲区"

        # 4. 薄弱: 掌握度偏低
        elif mastery < WEAK_THRESHOLD:
            gap_type = "weak"
            priority = "medium"
            description = f"掌握度{mastery:.0%}, 需要巩固提升"

        if gap_type:
            # 计算被阻塞的下游知识点
            for other_kp in kg.points:
                if kp.id in kg.prerequisites(other_kp.id) and mastery_map.get(other_kp.id, 0.0) < WEAK_THRESHOLD:
                    if other_kp.id not in blocks:
                        blocks.append(other_kp.id)

            confidence = _gap_confidence(mastery, tc, gap_type)
            suggested_action = _generate_suggested_action(
                gap_type, kp.name, mastery, blocked_by, blocks, kg
            )

            gaps.append(KnowledgeGap(
                kp_id=kp.id,
                kp_name=kp.name,
                domain=kp.domain,
                mastery=round(mastery, 4),
                gap_type=gap_type,
                priority=priority,
                description=description,
                blocked_by=blocked_by,
                blocks=blocks,
                suggested_action=suggested_action,
                confidence=round(confidence, 2),
            ))

    # 排序: 高优先级在前, 同优先级按掌握度升序
    priority_order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: (priority_order[g.priority], g.mastery))

    return gaps


# ============================================================
# 错误模式分类
# ============================================================

# 典型错例模板（按错误类别 + 知识点）
_ERROR_EXAMPLES: Dict[str, Dict[str, List[str]]] = {
    "概念混淆": {
        "kp_027": ["认为Bagging和Boosting的区别仅在于是否并行（忽略了样本权重和串行依赖）"],
        "kp_028": ["混淆BatchNorm和LayerNorm的归一化维度"],
        "kp_016": ["将SGD的随机性等同于随机梯度采样（忽略了mini-batch采样策略差异）"],
        "kp_018": ["混淆Adam的动量项和RMSProp的平方梯度累积"],
        "kp_007": ["将K-Means的'无监督'误解为'不需要任何标签就能做分类'"],
        "kp_012": ["混淆'卷积'与'互相关'操作，认为二者完全等同"],
    },
    "计算错误": {
        "kp_012": ["CNN输出尺寸计算时忽略了padding的翻倍效果"],
        "kp_017": ["手动计算梯度时链式法则漏项"],
        "kp_010": ["混淆矩阵行列含义颠倒（真实/预测放反）"],
    },
    "逻辑跳跃": {
        "kp_008": ["从'模型过拟合'直接跳到'加Dropout'，忽略了检查数据量和正则化强度的中间步骤"],
        "kp_012": ["从'数据是图像'直接跳到'用ResNet'，未分析为什么CNN适合以及ResNet相比VGG的优势"],
        "kp_019": ["从'防止过拟合'直接跳到'加L2正则'，未考虑Dropout或数据增强等其他方案"],
    },
    "忽略条件": {
        "kp_010": ["题目给定'数据严重不平衡'，仍用accuracy作为评估指标"],
        "kp_024": ["题目限定'推理时延<10ms'，仍推荐大型Transformer模型"],
    },
}

_ERROR_DESCRIPTIONS = {
    "概念混淆": "将相似概念混为一谈，尤其在跨领域对比时出错",
    "计算错误": "数学推导或数值计算环节出错",
    "逻辑跳跃": "推理跳过了关键中间步骤，从输入直接跳到结论",
    "忽略条件": "答题时忽略题目约束条件或隐含假设",
}


def classify_error_patterns(
    test_records: List[TestRecord],
    mastery_map: Dict[str, float] | None = None,
) -> ErrorPatterns:
    """从答题记录中自动分类错误模式 (v2.1)

    基于 test_records 中的 error_pattern 字段聚合，
    若未标注则根据知识点ID从模板库推断典型错例。
    """
    wrong_records = [t for t in test_records if not t.is_correct]
    total = len(test_records)
    correct = total - len(wrong_records)

    categories: Dict[str, Dict] = {
        "概念混淆": {"count": 0, "kp_ids": set(), "examples": []},
        "计算错误": {"count": 0, "kp_ids": set(), "examples": []},
        "逻辑跳跃": {"count": 0, "kp_ids": set(), "examples": []},
        "忽略条件": {"count": 0, "kp_ids": set(), "examples": []},
    }

    labeled_wrong = 0
    for t in wrong_records:
        cat = t.error_pattern if t.error_pattern else None
        if cat and cat in categories:
            labeled_wrong += 1
            categories[cat]["count"] += 1
            categories[cat]["kp_ids"].add(t.knowledge_point_id)
        else:
            # 未标注的错题归入"概念混淆"作为默认
            categories["概念混淆"]["count"] += 1
            categories["概念混淆"]["kp_ids"].add(t.knowledge_point_id)

    # 为每类补充典型错例
    for cat_name, cat_data in categories.items():
        for kp_id in list(cat_data["kp_ids"])[:3]:
            if cat_name in _ERROR_EXAMPLES and kp_id in _ERROR_EXAMPLES[cat_name]:
                cat_data["examples"].extend(_ERROR_EXAMPLES[cat_name][kp_id])
        # 如果该类别没有匹配的模板错例，使用通用描述
        if not cat_data["examples"]:
            cat_data["examples"] = [f"涉及知识点 {', '.join(list(cat_data['kp_ids'])[:3])} 的典型{cat_name}问题"]

    items: List[ErrorPatternItem] = []
    total_wrong = len(wrong_records) if wrong_records else 1
    primary = ("概念混淆", 0)
    secondary = ("概念混淆", 0)

    for cat_name in ["概念混淆", "计算错误", "逻辑跳跃", "忽略条件"]:
        cat_data = categories[cat_name]
        ratio = round(cat_data["count"] / total_wrong, 2)
        coverage = labeled_wrong / len(wrong_records) if wrong_records else 0.0
        conf = round(coverage * (0.78 + min(0.12, cat_data["count"] * 0.02)), 2) if cat_data["count"] > 0 else 0.0

        items.append(ErrorPatternItem(
            category=cat_name,
            count=cat_data["count"],
            ratio=ratio,
            confidence=conf,
            description=_ERROR_DESCRIPTIONS.get(cat_name, ""),
            typical_examples=cat_data["examples"][:3],
            involved_kp_ids=list(cat_data["kp_ids"]),
        ))

        if cat_data["count"] > primary[1]:
            secondary = primary
            primary = (cat_name, cat_data["count"])
        elif cat_data["count"] > secondary[1]:
            secondary = (cat_name, cat_data["count"])

    classification_conf = round(labeled_wrong / len(wrong_records), 2) if wrong_records else 0.0

    return ErrorPatterns(
        total_questions=total,
        total_correct=correct,
        total_wrong=len(wrong_records),
        overall_accuracy=round(correct / total, 3) if total > 0 else 0.0,
        primary_weakness=primary[0],
        primary_weakness_ratio=round(primary[1] / total_wrong, 2) if total_wrong > 0 else 0.0,
        classification_confidence=classification_conf,
        confidence_note=f"{len(wrong_records)}道错题由自动分类完成，建议后续引入人工标注交叉验证",
        items=items,
    )
