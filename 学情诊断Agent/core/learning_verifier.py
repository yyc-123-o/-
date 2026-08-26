"""学习成果检验 — 对比两次画像，生成学习成果检验报告 (第二流程)

核心: 对比 baseline 画像 P0 与 学习后画像 P1，度量学习效果

六维对比:
  1. 全局能力 θ
  2. 总正确率
  3. 能力等级
  4. 各领域掌握度
  5. 各知识点掌握度 (显著提升/提升/不变/下降)
  6. 知识盲区 (消除/持续/新增) + 错误模式

输出: LearningOutcomeReport
"""

from __future__ import annotations
from typing import Dict, List, Optional
from datetime import datetime

from models.schemas import (
    LearnerProfile,
    LearningOutcomeReport,
    KpChange, DomainChange, GapChange, ErrorPatternChange,
)


# ============================================================
# 阈值常量
# ============================================================

MASTERY_THRESHOLD = 0.6          # 掌握阈值 (mastery ≥ 0.6 视为已掌握)
SIGNIFICANT_IMPROVEMENT = 0.3    # 知识点显著提升
IMPROVEMENT = 0.1                # 知识点提升
DECLINE = -0.1                   # 知识点下降

# 综合判定阈值
VERDICT_SIGNIFICANT_THETA = 0.5
VERDICT_GENERAL_THETA = 0.2
VERDICT_DECLINE_THETA = -0.2
VERDICT_SIGNIFICANT_RESOLVE = 0.5
VERDICT_GENERAL_RESOLVE = 0.3


# ============================================================
# 辅助函数
# ============================================================

def _mastery(profile: LearnerProfile, kp_id: str) -> Optional[float]:
    """获取某知识点掌握度 (未测评返回 None)"""
    pt = profile.knowledge_mastery.points.get(kp_id)
    if pt is None:
        return None
    return pt.mastery


def _classify_kp_change(delta: float) -> str:
    """知识点提升分类"""
    if delta >= SIGNIFICANT_IMPROVEMENT:
        return "显著提升"
    elif delta >= IMPROVEMENT:
        return "提升"
    elif delta >= DECLINE:
        return "不变"
    else:
        return "下降"


# ============================================================
# 各维度对比
# ============================================================

def _compare_theta(baseline: LearnerProfile, post: LearnerProfile) -> dict:
    b = baseline.knowledge_mastery.global_theta
    p = post.knowledge_mastery.global_theta
    return {"before": round(b, 4), "after": round(p, 4), "delta": round(p - b, 4)}


def _compare_accuracy(baseline: LearnerProfile, post: LearnerProfile) -> dict:
    b = baseline.knowledge_mastery.overall_accuracy
    p = post.knowledge_mastery.overall_accuracy
    return {"before": round(b, 3), "after": round(p, 3), "delta": round(p - b, 3)}


def _compare_ability_level(baseline: LearnerProfile, post: LearnerProfile) -> dict:
    return {
        "before": baseline.ability_level.overall,
        "after": post.ability_level.overall,
    }


def _compare_domains(baseline: LearnerProfile, post: LearnerProfile) -> List[DomainChange]:
    changes = []
    for domain, item in baseline.knowledge_mastery.domain_summary.items():
        post_item = post.knowledge_mastery.domain_summary.get(domain)
        after = post_item.mean_mastery if post_item else 0.0
        delta = after - item.mean_mastery
        changes.append(DomainChange(
            domain=domain,
            before=round(item.mean_mastery, 3),
            after=round(after, 3),
            delta=round(delta, 3),
        ))
    # 按提升幅度降序
    changes.sort(key=lambda x: x.delta, reverse=True)
    return changes


def _compare_kps(baseline: LearnerProfile, post: LearnerProfile) -> List[KpChange]:
    changes = []
    for kp_id, pt in baseline.knowledge_mastery.points.items():
        before = pt.mastery
        after_pt = post.knowledge_mastery.points.get(kp_id)
        after = after_pt.mastery if after_pt else None

        # 任一侧未测评则跳过（无法对比）
        if before is None or after is None:
            continue

        delta = after - before
        changes.append(KpChange(
            kp_id=kp_id,
            name=pt.name,
            domain=pt.domain,
            before=round(before, 3),
            after=round(after, 3),
            delta=round(delta, 3),
            category=_classify_kp_change(delta),
        ))
    # 按提升幅度降序
    changes.sort(key=lambda x: x.delta, reverse=True)
    return changes


def _compare_gaps(baseline: LearnerProfile, post: LearnerProfile):
    """盲区变化: 返回 (resolved, remaining, new)"""
    resolved, remaining, new = [], [], []

    for kp_id, pt in baseline.knowledge_mastery.points.items():
        before = pt.mastery
        after_pt = post.knowledge_mastery.points.get(kp_id)
        after = after_pt.mastery if after_pt else None
        if before is None or after is None:
            continue

        if before < MASTERY_THRESHOLD and after >= MASTERY_THRESHOLD:
            resolved.append(GapChange(kp_id=kp_id, name=pt.name, domain=pt.domain,
                                      before=round(before, 3), after=round(after, 3)))
        elif before < MASTERY_THRESHOLD and after < MASTERY_THRESHOLD:
            remaining.append(GapChange(kp_id=kp_id, name=pt.name, domain=pt.domain,
                                       before=round(before, 3), after=round(after, 3)))
        elif before >= MASTERY_THRESHOLD and after < MASTERY_THRESHOLD:
            new.append(GapChange(kp_id=kp_id, name=pt.name, domain=pt.domain,
                                 before=round(before, 3), after=round(after, 3)))

    return resolved, remaining, new


def _compare_error_patterns(baseline: LearnerProfile, post: LearnerProfile) -> List[ErrorPatternChange]:
    b_items = {e.category: e.ratio for e in baseline.error_patterns.items}
    p_items = {e.category: e.ratio for e in post.error_patterns.items}

    changes = []
    for category in b_items:
        before = b_items.get(category, 0.0)
        after = p_items.get(category, 0.0)
        changes.append(ErrorPatternChange(
            category=category,
            before_ratio=round(before, 3),
            after_ratio=round(after, 3),
            delta=round(after - before, 3),
        ))
    return changes


# ============================================================
# 综合判定与建议
# ============================================================

def _judge_verdict(theta_delta: float, resolved: int, total_gaps: int) -> str:
    """综合判定学习成果"""
    resolution_rate = (resolved / total_gaps) if total_gaps > 0 else 1.0

    if theta_delta >= VERDICT_SIGNIFICANT_THETA and resolution_rate >= VERDICT_SIGNIFICANT_RESOLVE:
        return "显著提升"
    elif theta_delta >= VERDICT_GENERAL_THETA and resolution_rate >= VERDICT_GENERAL_RESOLVE:
        return "一般提升"
    elif theta_delta < VERDICT_DECLINE_THETA:
        return "退步"
    else:
        return "无明显提升"


def _recommendation(verdict: str, chapter_id: str) -> str:
    if verdict in ("显著提升", "一般提升"):
        return f"学习效果达标，建议进入下一章节（{chapter_id} 已掌握，可进阶）"
    elif verdict == "退步":
        return f"学习效果不理想，建议回溯复习 {chapter_id} 的薄弱知识点，并重新生成针对性补充资源"
    else:
        return f"提升不明显，建议在 {chapter_id} 上巩固练习后再复测"


# ============================================================
# 主入口: 对比两次画像
# ============================================================

def compare_profiles(
    baseline: LearnerProfile,
    post: LearnerProfile,
    learner_id: str,
    chapter_id: str = "ch03_cnn",
) -> LearningOutcomeReport:
    """对比 baseline 画像与学习后画像，生成学习成果检验报告"""
    import uuid

    theta = _compare_theta(baseline, post)
    accuracy = _compare_accuracy(baseline, post)
    ability_level = _compare_ability_level(baseline, post)
    domain_changes = _compare_domains(baseline, post)
    kp_changes = _compare_kps(baseline, post)
    gaps_resolved, gaps_remaining, gaps_new = _compare_gaps(baseline, post)
    error_pattern_changes = _compare_error_patterns(baseline, post)

    total_gaps = len(gaps_resolved) + len(gaps_remaining)
    verdict = _judge_verdict(theta["delta"], len(gaps_resolved), total_gaps)
    recommendation = _recommendation(verdict, chapter_id)

    return LearningOutcomeReport(
        report_id=f"OUTCOME-{uuid.uuid4().hex[:8]}",
        learner_id=learner_id,
        chapter_id=chapter_id,
        baseline_profile_id=baseline.profile_id,
        post_profile_id=post.profile_id,
        overall_verdict=verdict,
        theta=theta,
        accuracy=accuracy,
        ability_level=ability_level,
        domain_changes=domain_changes,
        kp_changes=kp_changes,
        gaps_resolved=gaps_resolved,
        gaps_remaining=gaps_remaining,
        gaps_new=gaps_new,
        error_pattern_changes=error_pattern_changes,
        recommendation=recommendation,
    )
