"""自适应测试引擎 — 「广覆盖知识点优先」 + IRT 能力估计 + 按kp掌握度诊断

出题逻辑 (v4.0 — 覆盖优先):
  设计目标:
    1) 题目覆盖面要广: 尽量覆盖所有 knowledge_point_id (共 30 个 kp), 每个至少 1 题
    2) 每知识点题具代表性: 每 kp 先出 1 道匹配当前 θ 估计的代表性难度题,
       覆盖完再循环补代表性 kp 的第 2 题
    3) 结束时可评价「每个知识点的掌握程度」: 输出 kp 维度正确率 + IRT θ(题数够时)
    4) 总题数可控: 典型 25~40 题

  两阶段选题:
    Phase 1 — 全覆盖阶段 (covered_kp_count < TARGET_KP_COVERAGE 且 answered < MAX_QUESTIONS):
        候选池 = ∪{未覆盖的 kp_id} 对应全部未答题
        在候选池中挑 |difficulty - current_θ| 最小的一题 (匹配当前能力代表性题)
    Phase 2 — 补足代表性阶段:
        优先给「仅被覆盖 1 次的 kp」继续出第 2 道代表性题,
        其次在全部 kp 范围内按 Fisher 信息量选题 (IRT 标准做法)

  停止条件 (三者任一即触发结束):
    (a) 已覆盖 kp 数 ≥ MIN_KP_COVERAGE(25)  AND  已答题数 ≥ MIN_QUESTIONS(25)
    (b) 已答题数 ≥ MAX_QUESTIONS(40)           [硬上限, 防疲劳]
    (c) 题库耗尽 / 当前候选池已空

  注: 仍保留「5 大领域 / 难度档」等元信息以便前端展示,
      但不再按领域逐个递进, 而是跨领域自由跳以最大 kp 覆盖。
"""

from __future__ import annotations
import math
import warnings
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from core import irt


# adaptivetesting 1.2.1 currently imports warnings.deprecated, which is only
# available in Python 3.13+. Keep the compatibility shim local to this module
# so the package can be used on the project's Python 3.12 runtime.
if not hasattr(warnings, "deprecated"):
    def _deprecated(_message="", **_kwargs):
        return lambda func: func
    warnings.deprecated = _deprecated  # type: ignore[attr-defined]

try:
    import adaptivetesting as _cat
except Exception:  # pragma: no cover - optional fallback for minimal installs
    _cat = None


# ============================================================
# 常量: 领域 / 难度档 / 覆盖 & 题数阈值
# ============================================================

# 5 大领域 (仅用于展示/分组, 不再控制顺序)
DOMAINS = ["数学基础", "机器学习基础", "深度学习", "优化算法", "实践应用"]

# 难度档 (仅用于展示, 不再控制逐档递进)
DIFFICULTY_TIERS = [
    {"label": "低难度",   "low": -3.0, "high": -0.2},
    {"label": "中等难度", "low": -0.2, "high": 0.8},
    {"label": "高难度",   "low": 0.8,  "high": 3.0},
]

# —— v4.0 新覆盖策略阈值 ——
TARGET_KP_COVERAGE = 30          # 理想情况下希望覆盖的 kp 数 (共 30 个)
MIN_KP_COVERAGE    = 25          # 停止条件 (a): 至少覆盖 25 个 kp
MIN_QUESTIONS      = 25          # 停止条件 (a): 至少答 25 题
MAX_QUESTIONS      = 40          # 停止条件 (b): 绝对上限 40 题
KP_MIN_ANSWERS     = 1           # Phase1: 每 kp 至少答 1 题才算 "covered"
KP_REPRESENTATIVE_MAX = 2        # Phase2: 每 kp 最多出 2 道代表性题 (覆盖更广)

# IRT 能力估计: 用于选题时的当前 θ
IRT_PRIOR_STD = 1.0


# ============================================================
# 会话数据模型
# ============================================================

@dataclass
class AdaptiveSession:
    session_id: str
    learner_id: str
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    domains: List[str] = field(default_factory=lambda: list(DOMAINS))
    question_count: int = 0
    # 题库分桶
    bank_grouped: Dict[str, List[dict]] = field(default_factory=dict)  # by domain (保留)
    bank_by_kp: Dict[str, List[dict]] = field(default_factory=dict)     # by kp_id (新增核心)
    # 答题
    answers: List[dict] = field(default_factory=list)
    answered_qids: set = field(default_factory=set)
    # kp 覆盖统计
    kp_answer_count: Dict[str, int] = field(default_factory=dict)       # kp_id -> 回答次数
    covered_kp_ids: set = field(default_factory=set)                    # kp_answer_count ≥ KP_MIN_ANSWERS
    all_kp_ids: List[str] = field(default_factory=list)                 # 范围内所有 kp_id (已排序)
    # 当前 IRT θ (每答 1 题更新 1 次, 用于选题匹配代表性难度)
    current_theta: float = 0.0
    standard_error: Optional[float] = None
    estimator_method: str = "adaptivetesting-EAP"
    item_calibration_status: str = "provisional"
    selection_reason: str = ""
    # 会话终态
    finished: bool = False
    stop_reason: str = ""
    final_theta: Optional[float] = None
    # P1-2: IRT 先验 θ (用于最终能力估计的正则化)
    prior_theta: float = 0.0
    # 兼容字段 (前端可能仍依赖展示)
    current_domain: Optional[str] = None
    current_tier_label: Optional[str] = None
    domain_results: List[dict] = field(default_factory=list)
    # 会话配置 (保留兼容)
    knowledge_point_ids: Optional[List[str]] = None
    max_questions: int = MAX_QUESTIONS
    min_questions: int = MIN_QUESTIONS
    min_kp_coverage: int = MIN_KP_COVERAGE
    standard_error_threshold: Optional[float] = None
    # 当前待答题目 (用于服务端校验提交的题目是否匹配)
    current_question_id: Optional[str] = None


# 内存存储
_sessions: Dict[str, AdaptiveSession] = {}


# ============================================================
# 工具: 难度档标签 / IRT 辅助
# ============================================================

def _tier_label_for_question(q: dict) -> str:
    if q.get("difficulty_level") in ("低难度", "中等难度", "高难度"):
        return q["difficulty_level"]
    b = q.get("difficulty", 0.0)
    if b < -0.2:
        return "低难度"
    elif b <= 0.8:
        return "中等难度"
    return "高难度"


def public_question(question: dict) -> dict:
    """返回学生端题目，不泄露服务端判分和讲解字段。"""
    private_fields = {
        "correct_answer",
        "correct_option",
        "explanation",
        "solution",
        "rationale",
        "answer_analysis",
    }
    return {key: value for key, value in question.items() if key not in private_fields}


def _group_bank_by_kp(
    test_bank: List[dict],
    domains: List[str],
    knowledge_point_ids: Optional[List[str]] = None,
    domain_filter_active: bool = False,
) -> Tuple[Dict[str, List[dict]], List[str]]:
    """按 kp_id 分组题库, 同时返回范围内 kp_id 列表 (按领域+kp名稳定排序)"""
    domain_set = set(domains)
    kp_set = set(knowledge_point_ids) if knowledge_point_ids else None

    grouped: Dict[str, List[dict]] = {}
    meta = {}  # kp_id -> (domain_order, kp_name) 用于排序
    for q in test_bank:
        question_domain = q.get("domain")
        if domain_filter_active and question_domain not in domain_set:
            continue
        kp = q.get("knowledge_point_id")
        if not kp:
            continue
        if kp_set is not None and kp not in kp_set:
            continue
        grouped.setdefault(kp, []).append(q)
        if kp not in meta:
            try:
                dorder = DOMAINS.index(question_domain)
            except ValueError:
                dorder = 99
            meta[kp] = (dorder, q.get("knowledge_point_name", ""), kp)

    # 稳定排序: 领域顺序 -> kp_name -> kp_id
    sorted_kps = sorted(meta.keys(), key=lambda k: meta[k])
    return grouped, sorted_kps


def _group_bank_by_domain(
    test_bank: List[dict],
    domains: List[str],
    knowledge_point_ids: Optional[List[str]] = None,
    domain_filter_active: bool = False,
) -> Dict[str, List[dict]]:
    """按领域分组 (保留, 供兼容展示)"""
    grouped: Dict[str, List[dict]] = {d: [] for d in domains}
    kp_set = set(knowledge_point_ids) if knowledge_point_ids else None
    for q in test_bank:
        question_domain = q.get("domain")
        if domain_filter_active and question_domain not in grouped:
            continue
        if kp_set is not None and q.get("knowledge_point_id") not in kp_set:
            continue
        if question_domain in grouped:
            grouped[question_domain].append(q)
    return grouped


def _cat_item(question: dict):
    """Convert a project question into adaptivetesting's dichotomous item."""
    item = _cat.TestItem()
    item.id = question.get("question_id")
    item.a = float(question.get("discrimination", 1.0))
    item.b = float(question.get("difficulty", 0.0))
    item.c = float(question.get("guessing", question.get("c", 0.0)))
    item.d = float(question.get("upper_asymptote", question.get("d", 1.0)))
    item.additional_properties["category"] = [question.get("knowledge_point_id", "")]
    return item


def _cat_estimate(answers: List[dict], prior_theta: float) -> Tuple[float, float, str]:
    """Estimate theta and posterior standard error with the selected CAT library."""
    responses = [
        (
            answer.get("discrimination", 1.0),
            answer.get("difficulty", 0.0),
            bool(answer.get("is_correct", False)),
        )
        for answer in answers
    ]
    theta, standard_error, method = irt.estimate_eap_theta(
        responses, prior_theta=prior_theta, prior_std=IRT_PRIOR_STD
    )
    if method not in {"adaptivetesting-EAP", "grid-EAP"} or standard_error is None:
        raise ValueError("adaptivetesting EAP 不可用")
    if not math.isfinite(theta) or not math.isfinite(standard_error):
        raise ValueError("adaptivetesting 返回了非有限能力估计")
    return theta, standard_error, method


def _update_irt_theta(session: AdaptiveSession):
    """基于答题记录用 adaptivetesting EAP 更新 theta 和标准误。"""
    if not session.answers:
        session.current_theta = float(session.prior_theta)
        session.standard_error = None
        return
    try:
        theta, standard_error, method = _cat_estimate(session.answers, session.prior_theta)
        session.current_theta = float(theta)
        session.standard_error = float(standard_error)
        session.estimator_method = method
        return
    except Exception:
        # Keep the service usable if the optional dependency is unavailable or
        # an unusual item record cannot be represented by the library.
        session.estimator_method = "project-IRT-MLE-fallback"
    responses = [
        (
            a.get("discrimination", 1.0),
            a.get("difficulty", 0.0),
            bool(a.get("is_correct", False)),
        )
        for a in session.answers
    ]
    try:
        theta = irt.estimate_theta(responses, prior_theta=session.prior_theta)
    except Exception:
        theta = session.prior_theta
    session.current_theta = float(theta)
    session.standard_error = None


# ============================================================
# 核心: 两阶段选题
# ============================================================

def _candidate_questions_by_kp(session: AdaptiveSession, kp_ids: List[str]) -> List[dict]:
    """从指定 kp_id 集合中, 返回所有未答过的题"""
    cands = []
    for kp in kp_ids:
        for q in session.bank_by_kp.get(kp, []):
            if q["question_id"] not in session.answered_qids:
                cands.append(q)
    return cands


def _pick_nearest_difficulty(cands: List[dict], theta: float) -> Optional[dict]:
    """在候选集中挑 |difficulty - theta| 最小的题; 并列时按区分度从高到低"""
    if not cands:
        return None

    def key(q):
        return (abs(q.get("difficulty", 0.0) - theta),
                -q.get("discrimination", 1.0))

    cands_sorted = sorted(cands, key=key)
    return cands_sorted[0]


def _pick_max_fisher(cands: List[dict], theta: float) -> Optional[dict]:
    """Phase2 标准 IRT: 挑在当前 θ 处 Fisher 信息量最大的题
    Fisher I = a^2 * P(1-P), P = 1/(1+exp(-a(θ-b)))
    """
    if not cands:
        return None

    if _cat is not None:
        try:
            items = [_cat_item(q) for q in cands]
            selected = _cat.maximum_information_criterion(items, float(theta))
            selected_id = selected.id
            return next(q for q in cands if q.get("question_id") == selected_id)
        except Exception:
            pass

    def info(q):
        a = float(q.get("discrimination", 1.0))
        b = float(q.get("difficulty", 0.0))
        z = a * (theta - b)
        # 数值稳定的 P / 1-P
        if z >= 0:
            ez = np.exp(-z)
            P = 1.0 / (1.0 + ez)
        else:
            ez = np.exp(z)
            P = ez / (1.0 + ez)
        return a * a * P * (1.0 - P)

    cands_sorted = sorted(cands, key=lambda q: -info(q))
    return cands_sorted[0]


def _select_question(session: AdaptiveSession) -> Optional[dict]:
    """两阶段选题 (覆盖优先 → 代表性补充)

    返回下一题 dict, 无法选题 (耗尽/已停) 返回 None
    """
    if session.finished:
        return None

    # Phase1: 仍存在未覆盖的 kp → 优先从未覆盖 kp 选题
    uncovered_kps = [kp for kp in session.all_kp_ids
                     if session.kp_answer_count.get(kp, 0) < KP_MIN_ANSWERS]
    if uncovered_kps:
        cands = _candidate_questions_by_kp(session, uncovered_kps)
        q = _pick_nearest_difficulty(cands, session.current_theta)
        if q is not None:
            session.selection_reason = "优先覆盖尚未测评的知识点"
            return q
        # 若这些未覆盖 kp 都已无题可出 (理论上只要每 kp≥2 不会触发), 则降级到 Phase2

    # Phase2: 先给 "只答过 1 次" 的 kp 再补 1 道, 保证代表性; 再统一 Fisher
    under_kps = [kp for kp in session.all_kp_ids
                 if 0 < session.kp_answer_count.get(kp, 0) < KP_REPRESENTATIVE_MAX]
    cands = _candidate_questions_by_kp(session, under_kps)
    if cands:
        q = _pick_nearest_difficulty(cands, session.current_theta)
        if q is not None:
            session.selection_reason = "补充只有一条作答证据的知识点"
            return q

    # 最后: 全题库未答范围 Fisher 信息量最大 (纯 IRT 精修)
    remaining = []
    for kp in session.all_kp_ids:
        for q in session.bank_by_kp.get(kp, []):
            if q["question_id"] not in session.answered_qids:
                remaining.append(q)
    q = _pick_max_fisher(remaining, session.current_theta)
    if q is not None:
        session.selection_reason = "选择在当前能力附近信息量最高的题目，以降低标准误"
    return q


# ============================================================
# 停止条件判定
# ============================================================

def _check_stop_condition(session: AdaptiveSession) -> Optional[str]:
    """若满足停止条件, 返回停止原因字符串; 否则返回 None"""
    n = session.question_count
    covered = len(session.covered_kp_ids)

    # 条件 (b) 硬上限
    if n >= session.max_questions:
        return f"达到总题数上限 {session.max_questions} 题 (已覆盖 {covered}/{len(session.all_kp_ids)} kp)"

    # 条件 (a) 覆盖 + 题数达标；若配置了标准误，再优先给出收敛原因。
    if covered >= min(session.min_kp_coverage, len(session.all_kp_ids)) and n >= session.min_questions:
        if (
            session.standard_error_threshold is not None
            and session.standard_error is not None
            and session.standard_error <= session.standard_error_threshold
        ):
            return (
                f"标准误 {session.standard_error:.4f} ≤ {session.standard_error_threshold:.4f}, "
                f"且已覆盖 {covered} 个知识点并完成 {n} 题"
            )
        return (
            f"已覆盖 {covered} 个知识点 ≥ {min(session.min_kp_coverage, len(session.all_kp_ids))}, "
            f"且答题 {n} 题 ≥ {session.min_questions}"
        )

    # 题库完全耗尽 (已无任何未答题)
    if _select_question(session) is None:
        return f"题库未答题耗尽 (已覆盖 {covered}/{len(session.all_kp_ids)} kp, 共 {n} 题)"

    return None


# ============================================================
# 结果: 全局 θ + 按 kp 掌握度
# ============================================================

def _estimate_final_theta(
    answers: List[dict],
    prior_theta: float = 0.0,
) -> tuple:
    try:
        theta, standard_error, method = _cat_estimate(answers, prior_theta)
        return round(theta, 4), {
            "n_responses": len(answers),
            "prior_weight": "bayesian",
            "method": method,
            "standard_error": round(standard_error, 4),
        }
    except Exception:
        pass

    responses = [
        (
            a.get("discrimination", 1.0),
            a.get("difficulty", 0.0),
            bool(a.get("is_correct", False)),
        )
        for a in answers
    ]
    n = len(responses)
    try:
        theta = irt.estimate_theta(responses, prior_theta=prior_theta)
    except Exception:
        theta = prior_theta

    if n >= 10:
        prior_weight = "none"
    elif n >= 5:
        prior_weight = "low"
    else:
        prior_weight = "high"

    info = {
        "n_responses": n,
        "prior_weight": prior_weight,
        "method": "IRT-MLE",
        "standard_error": None,
    }
    return round(float(theta), 4), info


def _estimate_kp_mastery(session: AdaptiveSession) -> List[dict]:
    """为每个在范围内的 kp 产出掌握度报告: 正确率 + 若题数≥2 则附加 IRT θ

    输出列表每项: {
        "kp_id": str,
        "kp_name": str,
        "domain": str,
        "test_count": int,
        "correct": int,
        "correct_rate": float (0-1),
        "mastery": float (0-1, 映射: 正确率 → 掌握度),
        "theta": float|None (IRT θ, test_count ≥ 2 时),
        "status_label": str (未覆盖/薄弱/部分掌握/熟练 之一)
    }
    """
    result = []
    # kp_id → (kp_name, domain, [answers])
    per_kp: Dict[str, dict] = {}
    for a in session.answers:
        kp = a.get("kp_id")
        if not kp:
            continue
        if kp not in per_kp:
            per_kp[kp] = {"kp_name": a.get("knowledge_point_name", ""),
                          "domain": a.get("domain", ""),
                          "records": []}
        per_kp[kp]["records"].append(a)

    # 题目元信息 (用于 kp_name / domain 兜底)
    for kp_id in session.all_kp_ids:
        entry = per_kp.get(kp_id, {"kp_name": "", "domain": "", "records": []})
        bank_qs = session.bank_by_kp.get(kp_id, [])
        if not entry["kp_name"] and bank_qs:
            entry["kp_name"] = bank_qs[0].get("knowledge_point_name", "")
        if not entry["domain"] and bank_qs:
            entry["domain"] = bank_qs[0].get("domain", "")

        records = entry["records"]
        test_count = len(records)
        correct = sum(1 for r in records if r.get("is_correct"))
        correct_rate = (correct / test_count) if test_count > 0 else 0.0

        # θ: 仅当该 kp ≥2 题时才单独估计 (否则不稳定)
        theta_kp = None
        if test_count >= 2:
            responses = [
                (r.get("discrimination", 1.0),
                 r.get("difficulty", 0.0),
                 bool(r.get("is_correct", False)))
                for r in records
            ]
            try:
                theta_kp = round(float(irt.estimate_theta(
                    responses, prior_theta=session.prior_theta)), 4)
            except Exception:
                theta_kp = None

        # mastery 映射: 正确率 0~1 映射到 0~1 的掌握度 (平滑)
        if test_count == 0:
            mastery = 0.0
        else:
            # 用 Laplace 平滑一点避免小样本极端
            mastery = (correct + 0.5) / (test_count + 1.0)

        # 文字标签
        if test_count == 0:
            status_label = "未覆盖"
        elif mastery < 0.35:
            status_label = "薄弱"
        elif mastery < 0.65:
            status_label = "部分掌握"
        else:
            status_label = "熟练"

        result.append({
            "kp_id": kp_id,
            "kp_name": entry["kp_name"],
            "domain": entry["domain"],
            "test_count": test_count,
            "correct": correct,
            "correct_rate": round(correct_rate, 4),
            "mastery": round(mastery, 4),
            "theta": theta_kp,
            "status_label": status_label,
        })
    return result


def _domain_results_from_answers(session: AdaptiveSession) -> List[dict]:
    """用正确率为每个 domain 打一个 level 标签 (保留给前端展示)"""
    per_domain: Dict[str, dict] = {}
    for a in session.answers:
        dom = a.get("domain")
        if not dom:
            continue
        d = per_domain.setdefault(dom, {"correct": 0, "wrong": 0})
        if a.get("is_correct"):
            d["correct"] += 1
        else:
            d["wrong"] += 1

    out = []
    for dom in session.domains:
        d = per_domain.get(dom, {"correct": 0, "wrong": 0})
        total = d["correct"] + d["wrong"]
        rate = (d["correct"] / total) if total > 0 else 0.0
        if total == 0:
            level, reason = "", "该领域未出题"
        elif rate >= 0.7:
            level, reason = "高难度", f"正确率 {rate*100:.0f}%"
        elif rate >= 0.4:
            level, reason = "中等难度", f"正确率 {rate*100:.0f}%"
        else:
            level, reason = "低难度", f"正确率 {rate*100:.0f}%"
        out.append({
            "domain": dom,
            "level": level,
            "reason": reason,
            "correct": d["correct"],
            "wrong": d["wrong"],
        })
    return out


# ============================================================
# API: 启动 / 答题 / 状态 / 结果
# ============================================================

def start_session(
    learner_id: str,
    prior_theta: float,
    test_bank: List[dict],
    config: Optional[dict] = None,
) -> dict:
    """启动一次自适应测试会话 (v4.0 广覆盖优先)"""
    import uuid

    config = config or build_config()
    domains = config.get("domains")
    if domains is None:
        domains = list(DOMAINS)
    knowledge_point_ids = config.get("knowledge_point_ids")
    domain_filter_active = config.get("domain_filter_active", False)

    sid = f"sess_{uuid.uuid4().hex[:8]}"
    bank_by_kp, all_kp_ids = _group_bank_by_kp(
        test_bank, domains, knowledge_point_ids, domain_filter_active
    )

    session = AdaptiveSession(
        session_id=sid,
        learner_id=learner_id,
        domains=list(domains),
        prior_theta=float(prior_theta),
        current_theta=float(prior_theta),
        knowledge_point_ids=knowledge_point_ids,
        bank_grouped=_group_bank_by_domain(
            test_bank, domains, knowledge_point_ids, domain_filter_active
        ),
        bank_by_kp=bank_by_kp,
        all_kp_ids=all_kp_ids,
        max_questions=config["max_questions"],
        min_questions=config["min_questions"],
        min_kp_coverage=config["min_kp_coverage"],
        standard_error_threshold=config.get("standard_error_threshold"),
    )
    _sessions[sid] = session

    bank_size = sum(len(v) for v in session.bank_by_kp.values())
    if not domains or bank_size == 0 or not session.all_kp_ids:
        session.finished = True
        session.stop_reason = "无可用题目 (领域/知识点过滤后题库为空)"
        return {
            "session_id": sid,
            "finished": True,
            "stop_reason": session.stop_reason,
            "question_count": 0,
            "current_domain": None,
            "domain_index": 0,
            "domain_total": len(domains),
            "current_tier": None,
            "consecutive_correct": 0,
            "consecutive_wrong": 0,
            "next_question": None,
            "bank_size": 0,
            "total_kp": 0,
            "covered_kp": 0,
            "kp_coverage_report": [],
            "error": "题库为空: 请检查 domains / knowledge_point_ids 配置",
        }

    # 初始化: 选第一道题 (匹配先验 θ 的未覆盖 kp 代表题)
    q = _select_question(session)
    session.current_domain = q.get("domain") if q else (session.domains[0] if session.domains else None)
    session.current_tier_label = _tier_label_for_question(q) if q else None
    session.current_question_id = q["question_id"] if q else None

    return {
        "session_id": sid,
        "finished": False,
        "question_count": 0,
        "current_domain": session.current_domain,
        "domain_index": 0,
        "domain_total": len(session.domains),
        "current_tier": session.current_tier_label,
        "consecutive_correct": 0,
        "consecutive_wrong": 0,
        "next_question": public_question(q) if q else None,
        "bank_size": bank_size,
        "total_kp": len(session.all_kp_ids),
        "covered_kp": 0,
        "current_theta": round(session.current_theta, 4),
        "coverage_target": (
            f"Phase1 覆盖 {min(session.min_kp_coverage, len(session.all_kp_ids))}/"
            f"{len(session.all_kp_ids)} kp, 上限 {session.max_questions} 题"
        ),
        "standard_error": None,
        "estimator_method": session.estimator_method,
        "item_calibration_status": session.item_calibration_status,
        "selection_reason": session.selection_reason,
    }


def submit_answer(
    session_id: str,
    question_id: str,
    selected_answer: Optional[int],
    time_spent: int,
    test_bank: List[dict],
) -> dict:
    """提交答案 (v4.0): 更新 kp 覆盖计数 + IRT θ + 判定停止"""
    if isinstance(time_spent, bool) or not isinstance(time_spent, int) or time_spent < 0:
        return {"error": "time_spent 必须是非负整数"}
    if isinstance(selected_answer, bool) or not isinstance(selected_answer, int):
        return {"error": "selected_answer 必须是整数选项下标"}

    session = _sessions.get(session_id)
    if not session:
        return {"error": "会话不存在"}
    if session.finished:
        return {"error": "会话已结束", "finished": True, "stop_reason": session.stop_reason}

    if session.current_question_id != question_id:
        return {"error": "提交的题目不是当前会话要求回答的题目"}

    # 查题目 (优先 session.bank_by_kp, 再全局 test_bank)
    q = None
    for kp_qs in session.bank_by_kp.values():
        hit = next((x for x in kp_qs if x["question_id"] == question_id), None)
        if hit:
            q = hit
            break
    if q is None:
        q = next((x for x in test_bank if x["question_id"] == question_id), None)
    if not q:
        return {"error": "题目不存在"}

    if selected_answer < 0 or selected_answer >= len(q.get("options", [])):
        return {"error": "选项无效"}
    if "correct_answer" not in q:
        return {"error": "必须提交题目选项，且该题必须包含服务端答案"}
    is_correct = selected_answer == q["correct_answer"]

    kp_id = q.get("knowledge_point_id", "")
    domain = q.get("domain", "")
    tier = _tier_label_for_question(q)

    session.question_count += 1
    session.answered_qids.add(question_id)
    session.answers.append({
        "question_id": question_id,
        "kp_id": kp_id,
        "knowledge_point_name": q.get("knowledge_point_name", ""),
        "difficulty": q.get("difficulty", 0.0),
        "discrimination": q.get("discrimination", 1.0),
        "is_correct": is_correct,
        "time_spent": time_spent,
        "domain": domain,
        "tier": tier,
    })

    # 更新 kp 覆盖计数
    session.kp_answer_count[kp_id] = session.kp_answer_count.get(kp_id, 0) + 1
    if session.kp_answer_count[kp_id] >= KP_MIN_ANSWERS:
        session.covered_kp_ids.add(kp_id)

    # 更新 IRT θ
    _update_irt_theta(session)

    # 当前题目所属领域 → 展示
    session.current_domain = domain
    session.current_tier_label = tier

    # 检查停止条件
    stop_reason = _check_stop_condition(session)
    if stop_reason is not None:
        session.finished = True
        session.stop_reason = stop_reason
        session.current_question_id = None
        session.domain_results = _domain_results_from_answers(session)
        final_theta, theta_info = _estimate_final_theta(
            session.answers, prior_theta=session.prior_theta
        )
        session.final_theta = final_theta
        kp_mastery = _estimate_kp_mastery(session)
        return {
            "session_id": session_id,
            "finished": True,
            "stop_reason": session.stop_reason,
            "question_count": session.question_count,
            "domain_results": session.domain_results,
            "final_theta": final_theta,
            "theta_info": theta_info,
            "standard_error": session.standard_error,
            "estimator_method": session.estimator_method,
            "item_calibration_status": session.item_calibration_status,
            "selection_reason": session.selection_reason,
            "answers": session.answers,
            "last_correct": is_correct,
            "total_kp": len(session.all_kp_ids),
            "covered_kp": len(session.covered_kp_ids),
            "kp_mastery": kp_mastery,
            "kp_coverage_report": _estimate_kp_mastery(session),
        }

    # 未停止 → 下一题
    next_q = _select_question(session)
    if next_q is None:
        # 题库耗尽
        session.finished = True
        session.stop_reason = (f"题库未答题耗尽 (已覆盖 {len(session.covered_kp_ids)}/"
                               f"{len(session.all_kp_ids)} kp, 共 {session.question_count} 题)")
        session.current_question_id = None
        session.domain_results = _domain_results_from_answers(session)
        final_theta, theta_info = _estimate_final_theta(
            session.answers, prior_theta=session.prior_theta
        )
        session.final_theta = final_theta
        kp_mastery = _estimate_kp_mastery(session)
        return {
            "session_id": session_id,
            "finished": True,
            "stop_reason": session.stop_reason,
            "question_count": session.question_count,
            "domain_results": session.domain_results,
            "final_theta": final_theta,
            "theta_info": theta_info,
            "standard_error": session.standard_error,
            "estimator_method": session.estimator_method,
            "item_calibration_status": session.item_calibration_status,
            "selection_reason": session.selection_reason,
            "answers": session.answers,
            "last_correct": is_correct,
            "total_kp": len(session.all_kp_ids),
            "covered_kp": len(session.covered_kp_ids),
            "kp_mastery": kp_mastery,
            "kp_coverage_report": kp_mastery,
        }

    session.current_domain = next_q.get("domain")
    session.current_tier_label = _tier_label_for_question(next_q)
    session.current_question_id = next_q["question_id"]

    # 兼容前端: 模拟连续对错 (用近 3 题内统计, 仅用于展示)
    recent = session.answers[-3:]
    consec_correct = 0
    for r in reversed(recent):
        if r.get("is_correct"):
            consec_correct += 1
        else:
            break
    consec_wrong = 0
    for r in reversed(recent):
        if not r.get("is_correct"):
            consec_wrong += 1
        else:
            break

    return {
        "session_id": session_id,
        "finished": False,
        "question_count": session.question_count,
        "current_domain": session.current_domain,
        "domain_index": min(
            DOMAINS.index(session.current_domain) if session.current_domain in DOMAINS else 0,
            len(session.domains) - 1,
        ),
        "domain_total": len(session.domains),
        "current_tier": session.current_tier_label,
        "consecutive_correct": consec_correct,
        "consecutive_wrong": consec_wrong,
        "next_question": public_question(next_q),
        "last_correct": is_correct,
        "total_kp": len(session.all_kp_ids),
        "covered_kp": len(session.covered_kp_ids),
        "current_theta": round(session.current_theta, 4),
        "standard_error": session.standard_error,
        "estimator_method": session.estimator_method,
        "item_calibration_status": session.item_calibration_status,
        "selection_reason": session.selection_reason,
    }


def get_session(session_id: str) -> Optional[dict]:
    s = _sessions.get(session_id)
    if not s:
        return None
    if s.finished:
        if s.final_theta is None:
            final_theta, theta_info = _estimate_final_theta(
                s.answers, prior_theta=s.prior_theta
            )
            s.final_theta = final_theta
        else:
            final_theta = s.final_theta
            _, theta_info = _estimate_final_theta(s.answers, prior_theta=s.prior_theta)
        kp_mastery = _estimate_kp_mastery(s)
    else:
        final_theta, theta_info = None, None
        kp_mastery = []
    return {
        "session_id": s.session_id,
        "learner_id": s.learner_id,
        "finished": s.finished,
        "stop_reason": s.stop_reason,
        "current_question_id": s.current_question_id,
        "question_count": s.question_count,
        "current_domain": s.current_domain,
        "domain_index": min(
            DOMAINS.index(s.current_domain) if s.current_domain in DOMAINS else 0,
            len(s.domains) - 1,
        ),
        "domain_total": len(s.domains),
        "current_tier": s.current_tier_label,
        "domain_results": s.domain_results or _domain_results_from_answers(s),
        "final_theta": final_theta,
        "theta_info": theta_info,
        "answers": s.answers,
        "total_kp": len(s.all_kp_ids),
        "covered_kp": len(s.covered_kp_ids),
        "kp_mastery": kp_mastery,
        "kp_coverage_report": kp_mastery,
        "current_theta": round(s.current_theta, 4),
        "standard_error": s.standard_error,
        "estimator_method": s.estimator_method,
        "item_calibration_status": s.item_calibration_status,
        "selection_reason": s.selection_reason,
    }


# ============================================================
# 兼容接口 (main.py 依赖)
# ============================================================

def build_config(data: Optional[dict] = None) -> dict:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("adaptive test config 必须是对象")

    def require_finite_number(key: str, default: float) -> float:
        value = data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} 必须是有限数值")
        return float(value)

    raw_domains = data.get("domains")
    if raw_domains is not None and (
        not isinstance(raw_domains, list)
        or any(not isinstance(domain, str) or not domain for domain in raw_domains)
    ):
        raise ValueError("domains 必须是非空字符串数组")
    if raw_domains and any(domain not in DOMAINS for domain in raw_domains):
        raise ValueError("domains 包含不支持的领域")
    domains = list(raw_domains) if raw_domains else list(DOMAINS)

    kp_ids = data.get("knowledge_point_ids")
    if kp_ids is not None and (
        not isinstance(kp_ids, list)
        or any(not isinstance(kp_id, str) or not kp_id for kp_id in kp_ids)
    ):
        raise ValueError("knowledge_point_ids 必须是非空字符串数组")
    knowledge_point_ids = list(kp_ids) if kp_ids else None

    raw_stages = data.get("difficulty_stages")
    if raw_stages is not None:
        if not isinstance(raw_stages, list) or not raw_stages or any(
            not isinstance(stage, dict) for stage in raw_stages
        ):
            raise ValueError("difficulty_stages 必须是非空对象数组")
        for stage in raw_stages:
            low = stage.get("low", -3.0)
            high = stage.get("high", 3.0)
            promote_accuracy = stage.get("promote_accuracy", 0.70)
            min_stage_questions = stage.get("min_questions", 2)
            if (
                any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for value in (low, high, promote_accuracy)
                )
                or low > high
                or not 0 <= promote_accuracy <= 1
                or isinstance(min_stage_questions, bool)
                or not isinstance(min_stage_questions, int)
                or min_stage_questions < 1
            ):
                raise ValueError("难度阶段范围、晋升正确率或最少题数无效")

    max_questions = require_finite_number("max_questions", MAX_QUESTIONS)
    min_questions = require_finite_number("min_questions", MIN_QUESTIONS)
    min_kp_coverage = require_finite_number("min_kp_coverage", MIN_KP_COVERAGE)
    if (
        not max_questions.is_integer()
        or not min_questions.is_integer()
        or not min_kp_coverage.is_integer()
        or min_questions < 1
        or max_questions < min_questions
        or min_kp_coverage < 1
    ):
        raise ValueError("题数和覆盖数必须为正整数，且 min_questions <= max_questions")

    convergence_threshold = require_finite_number("convergence_threshold", 0.15)
    if convergence_threshold < 0:
        raise ValueError("停止条件不能为负数")
    standard_error_threshold = data.get("standard_error_threshold")
    if standard_error_threshold is not None:
        if (
            isinstance(standard_error_threshold, bool)
            or not isinstance(standard_error_threshold, (int, float))
            or not math.isfinite(standard_error_threshold)
            or standard_error_threshold < 0
        ):
            raise ValueError("standard_error_threshold 必须是非负有限数值")

    return {
        "domains": domains,
        "domain_filter_active": bool(raw_domains),
        "knowledge_point_ids": knowledge_point_ids,
        "max_questions_per_domain": 20,        # 保留旧键, v4 未使用
        "stop_consecutive_wrong": 3,           # 保留旧键
        "promote_consecutive_correct": 2,      # 保留旧键
        "difficulty_tiers": [t["label"] for t in DIFFICULTY_TIERS],
        # v4 新参数 (作为参考, 无需前端传入)
        "min_kp_coverage": int(min_kp_coverage),
        "target_kp_coverage": TARGET_KP_COVERAGE,
        "min_questions": int(min_questions),
        "max_questions": int(max_questions),
        "convergence_threshold": convergence_threshold,
        "standard_error_threshold": (
            float(standard_error_threshold)
            if standard_error_threshold is not None else None
        ),
    }


def default_config_payload() -> dict:
    return {
        "domains": list(DOMAINS),
        "difficulty_tiers": [t["label"] for t in DIFFICULTY_TIERS],
        "promote_consecutive_correct": 2,
        "stop_consecutive_wrong": 3,
        "max_questions_per_domain": 20,
        # v4 策略阈值
        "min_kp_coverage": MIN_KP_COVERAGE,
        "target_kp_coverage": TARGET_KP_COVERAGE,
        "min_questions": MIN_QUESTIONS,
        "max_questions": MAX_QUESTIONS,
        "standard_error_threshold": None,
    }
