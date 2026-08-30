"""知识掌握度计算 — IRT + 交互行为加权 + 稀疏数据降级

对每个知识点:
1. 收集该知识点下所有测试记录 -> IRT MLE估计θ
2. 用θ和知识点基准难度计算基础掌握度
3. 交互行为加权修正
4. 数据稀疏时用学历先验兜底
"""

from __future__ import annotations
import math
from typing import Dict, List, Optional, Tuple
from models.schemas import TestRecord, InteractionRecord
from models.knowledge_graph import KnowledgeGraph
from core import irt


def _interaction_adjustment(
    kp_id: str,
    interactions: List[InteractionRecord],
) -> float:
    """根据交互记录计算掌握度修正值

    - 练习次数多 -> +信心 (小量)
    - 查看提示多 -> -信心
    - 浏览时长极长但练习少 -> 困难信号 (-)
    """
    if not interactions:
        return 0.0

    kp_interactions = [i for i in interactions if i.knowledge_point_id == kp_id]
    if not kp_interactions:
        return 0.0

    practice_count = sum(1 for i in kp_interactions if i.type == "practice")
    view_count = sum(1 for i in kp_interactions if i.type == "view")
    discussion_count = sum(1 for i in kp_interactions if i.type == "discussion")
    total_duration = sum(i.duration for i in kp_interactions)

    adj = 0.0
    # 多练习: 逐步提升信心, 但有上限
    adj += min(practice_count * 0.03, 0.15)
    # 讨论活跃: 少量提升
    adj += min(discussion_count * 0.02, 0.06)
    # 浏览极多但练习少: 困难信号
    if view_count >= 3 and practice_count == 0:
        adj -= 0.05
    # 超长时长(>1800秒)但练习少: 理解困难
    if total_duration > 1800 and practice_count <= 1:
        adj -= 0.08

    return adj


def _confidence_from_posterior(test_count: int, standard_error: Optional[float]) -> float:
    """Derive confidence from posterior uncertainty and evidence volume.

    This deliberately avoids fixed confidence bands by question count. The
    standard error captures item difficulty/discrimination; the sample factor
    prevents one response from being presented as a stable conclusion.
    """
    if test_count <= 0 or standard_error is None or not math.isfinite(standard_error):
        return 0.20
    posterior_precision = 1.0 / (1.0 + standard_error)
    sample_factor = test_count / (test_count + 2.0)
    return round(max(0.0, min(0.95, posterior_precision * sample_factor)), 3)


def compute_kp_mastery(
    kp_id: str,
    kp_difficulty: float,
    test_records: List[TestRecord],
    interactions: List[InteractionRecord],
    prior_theta: float = 0.0,
) -> Tuple[float, float, int, float, Optional[float]]:
    """计算单个知识点掌握度

    Returns:
        (mastery, theta, test_count, confidence, standard_error)
    """
    # 筛选该知识点的测试记录
    kp_tests = [t for t in test_records if t.knowledge_point_id == kp_id]

    standard_error: Optional[float] = None
    if kp_tests:
        responses = [(t.discrimination, t.difficulty, t.is_correct) for t in kp_tests]
        theta, standard_error, _ = irt.estimate_eap_theta(
            responses, prior_theta=prior_theta, use_library=False,
        )
    else:
        # 无测试数据: 纯先验 + 交互修正
        theta = prior_theta

    # 基础掌握度
    mastery = irt.mastery_from_theta(theta, kp_difficulty)

    # 交互行为修正
    adj = _interaction_adjustment(kp_id, interactions)
    mastery = max(0.0, min(1.0, mastery + adj))

    # 置信度
    confidence = _confidence_from_posterior(len(kp_tests), standard_error)

    return mastery, theta, len(kp_tests), confidence, standard_error


def _mastery_status(mastery: float) -> str:
    """掌握度 → 状态标签"""
    if mastery >= 0.75:
        return "mastered"
    elif mastery >= 0.60:
        return "familiar"
    elif mastery >= 0.40:
        return "partial"
    elif mastery >= 0.25:
        return "weak"
    elif mastery >= 0.10:
        return "not_learned"
    else:
        return "unexplored"


def _compute_all_mastery(
    kg: KnowledgeGraph,
    test_records: List[TestRecord],
    interactions: List[InteractionRecord],
    prior_theta: float = 0.0,
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, int], Dict[str, float], Dict[str, str], Dict[str, Optional[float]]]:
    """计算所有知识点掌握度

    Returns:
        (mastery_map, theta_map, test_count_map, confidence_map, status_map)
    """
    mastery_map: Dict[str, float] = {}
    theta_map: Dict[str, float] = {}
    test_count_map: Dict[str, int] = {}
    confidence_map: Dict[str, float] = {}
    status_map: Dict[str, str] = {}
    standard_error_map: Dict[str, Optional[float]] = {}

    for kp in kg.points:
        mastery, theta, tc, conf, standard_error = compute_kp_mastery(
            kp.id, kp.difficulty, test_records, interactions, prior_theta
        )
        mastery_map[kp.id] = round(mastery, 4)
        theta_map[kp.id] = round(theta, 4)
        test_count_map[kp.id] = tc
        confidence_map[kp.id] = conf
        status_map[kp.id] = "unexplored" if tc == 0 else _mastery_status(mastery)
        standard_error_map[kp.id] = round(standard_error, 4) if standard_error is not None else None

    return mastery_map, theta_map, test_count_map, confidence_map, status_map, standard_error_map


def compute_all_mastery(
    kg: KnowledgeGraph,
    test_records: List[TestRecord],
    interactions: List[InteractionRecord],
    prior_theta: float = 0.0,
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, int], Dict[str, float], Dict[str, str]]:
    """Backward-compatible five-map mastery interface."""
    return _compute_all_mastery(kg, test_records, interactions, prior_theta)[:5]


def compute_all_mastery_with_uncertainty(
    kg: KnowledgeGraph,
    test_records: List[TestRecord],
    interactions: List[InteractionRecord],
    prior_theta: float = 0.0,
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, int], Dict[str, float], Dict[str, str], Dict[str, Optional[float]]]:
    """Full mastery output for profiles that need posterior uncertainty."""
    return _compute_all_mastery(kg, test_records, interactions, prior_theta)
