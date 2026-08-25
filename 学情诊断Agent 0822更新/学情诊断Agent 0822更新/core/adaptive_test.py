"""自适应测试引擎 — 按领域分类答题 + 先易后难 + 困难定级

出题逻辑 (v3.0):
  1. 按 5 大领域分类，逐领域测试:
       数学基础 → 机器学习基础 → 深度学习 → 优化算法 → 实践应用
  2. 每个领域内按难度先易后难:
       低难度 → 中等难度 → 高难度
  3. 连续答对 N 题 → 晋升下一难度 (难度递进)
  4. 连续答错 M 题 → 该领域定级为「当前难度」，进入下一领域 (困难定级)
  5. 通过全部难度 → 该领域定级为「高难度」

默认配置 (系统内置, 不展示给用户):
  - 晋升: 连续答对 2 题
  - 定级: 连续答错 3 题
  - 每领域最大题数: 20 (安全上限)

Session 生命周期:
  start → answer → answer → ... → 领域逐个完成 → finish
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

from core import irt


# ============================================================
# 常量: 领域 / 难度档 / 默认配置
# ============================================================

# 5 大领域 (测试顺序, 从基础到应用)
DOMAINS = ["数学基础", "机器学习基础", "深度学习", "优化算法", "实践应用"]

# 难度档 (先易后难)
DIFFICULTY_TIERS = [
    {"label": "低难度",   "low": -3.0, "high": -0.2},
    {"label": "中等难度", "low": -0.2, "high": 0.8},
    {"label": "高难度",   "low": 0.8,  "high": 3.0},
]

# 默认配置 (系统内置)
PROMOTE_CONSECUTIVE_CORRECT = 2   # 连续答对 N 题 → 晋升下一难度
STOP_CONSECUTIVE_WRONG = 3        # 连续答错 M 题 → 定级当前难度
MAX_QUESTIONS_PER_DOMAIN = 20     # 每个领域最大题数 (安全上限)

# 难度档 → θ 映射 (用于估算全局能力)
TIER_THETA = {"低难度": -0.6, "中等难度": 0.3, "高难度": 1.2}


# ============================================================
# 会话数据模型
# ============================================================

@dataclass
class DomainProgress:
    """单个领域的测试进度"""
    domain: str
    tier_index: int = 0                  # 当前难度档索引 (0/1/2)
    consecutive_correct: int = 0         # 当前档连续答对数
    consecutive_wrong: int = 0           # 当前档连续答错数
    correct: int = 0                     # 该领域累计答对数
    wrong: int = 0                       # 该领域累计答错数
    finished: bool = False
    level: str = ""                      # 定级结果: 低难度/中等难度/高难度
    reason: str = ""                     # 定级原因


@dataclass
class AdaptiveSession:
    session_id: str
    learner_id: str
    domains: List[str] = field(default_factory=lambda: list(DOMAINS))
    domain_index: int = 0
    progress: Optional[DomainProgress] = None
    domain_results: List[dict] = field(default_factory=list)
    question_count: int = 0
    bank_grouped: Dict[str, List[dict]] = field(default_factory=dict)
    answers: List[dict] = field(default_factory=list)
    finished: bool = False
    stop_reason: str = ""
    prior_theta: float = 0.0
    stop_consecutive_wrong: int = STOP_CONSECUTIVE_WRONG
    max_questions_per_domain: int = MAX_QUESTIONS_PER_DOMAIN
    knowledge_point_ids: Optional[set] = None


# 内存存储
_sessions: Dict[str, AdaptiveSession] = {}


# ============================================================
# 题库按领域分组
# ============================================================

def _group_bank_by_domain(test_bank: List[dict], domains: List[str]) -> Dict[str, List[dict]]:
    """按领域分组题库"""
    grouped: Dict[str, List[dict]] = {}
    for domain in domains:
        grouped[domain] = [q for q in test_bank if q.get("domain") == domain]
    return grouped


def _tier_label_for_question(q: dict) -> str:
    """判定题目所属难度档 (优先用 difficulty_level 字段)"""
    if q.get("difficulty_level") in ("低难度", "中等难度", "高难度"):
        return q["difficulty_level"]
    b = q.get("difficulty", 0.0)
    if b < -0.2:
        return "低难度"
    elif b <= 0.8:
        return "中等难度"
    return "高难度"


def _tier_index_by_label(label: str) -> int:
    for i, t in enumerate(DIFFICULTY_TIERS):
        if t["label"] == label:
            return i
    return 0


# ============================================================
# 选题: 在当前领域的当前难度档内随机选未答题
# ============================================================

def _select_question(session: AdaptiveSession) -> Optional[dict]:
    """在当前领域 + 当前难度档内选一道未答过的题

    当前档无剩余题时, 顺延到下一个有题的难度档。
    """
    if not session.progress:
        return None
    domain = session.progress.domain
    pool = session.bank_grouped.get(domain, [])
    if session.knowledge_point_ids is not None:
        pool = [q for q in pool if q.get("knowledge_point_id") in session.knowledge_point_ids]
    answered_ids = {a["question_id"] for a in session.answers}

    tier_label = DIFFICULTY_TIERS[session.progress.tier_index]["label"]
    in_tier = [q for q in pool
               if q["question_id"] not in answered_ids
               and _tier_label_for_question(q) == tier_label]

    # 当前档无题 → 顺延到下一个有题的档
    idx = session.progress.tier_index
    while not in_tier and idx < len(DIFFICULTY_TIERS) - 1:
        idx += 1
        tier_label = DIFFICULTY_TIERS[idx]["label"]
        in_tier = [q for q in pool
                   if q["question_id"] not in answered_ids
                   and _tier_label_for_question(q) == tier_label]
        if in_tier:
            session.progress.tier_index = idx

    if not in_tier:
        # 该领域题目耗尽
        return None

    rng = np.random.default_rng()
    return in_tier[rng.integers(0, len(in_tier))]


# ============================================================
# 领域定级与切换
# ============================================================

def _finish_domain(session: AdaptiveSession, level: str, reason: str):
    """定级当前领域并记录结果"""
    p = session.progress
    p.finished = True
    p.level = level
    p.reason = reason
    session.domain_results.append({
        "domain": p.domain,
        "level": level,
        "reason": reason,
        "correct": p.correct,
        "wrong": p.wrong,
    })


def _advance_to_next_domain(session: AdaptiveSession) -> bool:
    """进入下一领域, 返回是否还有剩余领域"""
    session.domain_index += 1
    if session.domain_index >= len(session.domains):
        session.finished = True
        session.stop_reason = "全部领域测试完成"
        return False
    domain = session.domains[session.domain_index]
    session.progress = DomainProgress(domain=domain)
    return True


# ============================================================
# 结果序列化
# ============================================================

def _current_tier_label(session: AdaptiveSession) -> Optional[str]:
    if session.progress:
        return DIFFICULTY_TIERS[session.progress.tier_index]["label"]
    return None


def _estimate_final_theta(answers: List[dict], prior_theta: float = 0.0) -> float:
    """使用本次会话的真实 2PL 题目参数和作答结果估计 theta。"""
    responses = [(a["discrimination"], a["difficulty"], a["is_correct"]) for a in answers]
    return round(irt.estimate_theta(responses, prior_theta=prior_theta), 4) if responses else round(prior_theta, 4)


# ============================================================
# API: 启动 / 答题 / 状态
# ============================================================

def start_session(
    learner_id: str,
    prior_theta: float,
    test_bank: List[dict],
    config: Optional[dict] = None,
) -> dict:
    """启动一次自适应测试会话 — 从第一个领域「数学基础」的低难度题开始"""
    import uuid

    sid = f"sess_{uuid.uuid4().hex[:8]}"
    effective = build_config(config)
    session = AdaptiveSession(
        session_id=sid,
        learner_id=learner_id,
        domains=effective["domains"],
        bank_grouped=_group_bank_by_domain(test_bank, effective["domains"]),
        prior_theta=prior_theta,
        stop_consecutive_wrong=effective["stop_consecutive_wrong"],
        max_questions_per_domain=effective["max_questions_per_domain"],
        knowledge_point_ids=set(effective["knowledge_point_ids"]) if effective["knowledge_point_ids"] else None,
    )
    if not any(session.bank_grouped.values()):
        raise ValueError("请求范围内没有可用题目")
    session.progress = DomainProgress(domain=session.domains[0])
    _sessions[sid] = session

    q = _select_question(session)
    result = {
        "session_id": sid,
        "finished": False,
        "question_count": 0,
        "current_domain": session.progress.domain,
        "domain_index": 0,
        "domain_total": len(session.domains),
        "current_tier": _current_tier_label(session),
        "consecutive_correct": 0,
        "consecutive_wrong": 0,
        "next_question": q,
        "bank_size": sum(len(v) for v in session.bank_grouped.values()),
    }
    return result


def submit_answer(
    session_id: str,
    question_id: str,
    is_correct: bool,
    time_spent: int,
    test_bank: List[dict],
) -> dict:
    """提交答案 — 更新晋升/定级逻辑, 返回下一题或领域切换或完成"""
    session = _sessions.get(session_id)
    if not session:
        return {"error": "会话不存在"}
    if session.finished:
        return {"error": "会话已结束", "finished": True, "stop_reason": session.stop_reason}

    # 找到这道题
    all_qs = [q for q_list in session.bank_grouped.values() for q in q_list]
    q = next((x for x in all_qs if x["question_id"] == question_id), None)
    if q is None:
        q = next((x for x in test_bank if x["question_id"] == question_id), None)
    if not q:
        return {"error": "题目不存在"}

    p = session.progress
    session.question_count += 1

    # 记录答题
    session.answers.append({
        "question_id": question_id,
        "kp_id": q.get("knowledge_point_id", ""),
        "difficulty": q.get("difficulty", 0.0),
        "discrimination": q.get("discrimination", 1.0),
        "is_correct": is_correct,
        "time_spent": time_spent,
        "domain": p.domain,
        "tier": _current_tier_label(session),
    })

    if is_correct:
        p.correct += 1
        p.consecutive_correct += 1
        p.consecutive_wrong = 0

        # 晋升: 连续答对达标
        if p.consecutive_correct >= PROMOTE_CONSECUTIVE_CORRECT:
            if p.tier_index >= len(DIFFICULTY_TIERS) - 1:
                # 已通过最高难度
                _finish_domain(session, DIFFICULTY_TIERS[-1]["label"], "通过全部难度档")
            else:
                p.tier_index += 1
                p.consecutive_correct = 0
                p.consecutive_wrong = 0
                # 顺延到有题的档
                next_q = _select_question(session)
                if next_q is None:
                    _finish_domain(session, DIFFICULTY_TIERS[p.tier_index]["label"], "题目耗尽")
    else:
        p.wrong += 1
        p.consecutive_wrong += 1
        p.consecutive_correct = 0

        # 定级: 连续答错达标
        if p.consecutive_wrong >= session.stop_consecutive_wrong:
            _finish_domain(session, DIFFICULTY_TIERS[p.tier_index]["label"], f"连续答错 {session.stop_consecutive_wrong} 题")

    # 每领域最大题数保护
    if not p.finished and (p.correct + p.wrong) >= session.max_questions_per_domain:
        _finish_domain(session, DIFFICULTY_TIERS[p.tier_index]["label"], f"达到领域最大题数 {session.max_questions_per_domain}")

    # 若当前领域已定级 → 切换下一领域
    if p.finished and not session.finished:
        last_domain_result = session.domain_results[-1]
        if not _advance_to_next_domain(session):
            # 全部领域完成
            final_theta = _estimate_final_theta(session.answers, session.prior_theta)
            return {
                "session_id": session_id,
                "finished": True,
                "stop_reason": session.stop_reason,
                "question_count": session.question_count,
                "domain_results": session.domain_results,
                "final_theta": final_theta,
                "answers": session.answers,
            }
        # 进入下一领域, 选该领域第一题
        q = _select_question(session)
        return {
            "session_id": session_id,
            "finished": False,
            "question_count": session.question_count,
            "current_domain": session.progress.domain,
            "domain_index": session.domain_index,
            "domain_total": len(session.domains),
            "current_tier": _current_tier_label(session),
            "consecutive_correct": 0,
            "consecutive_wrong": 0,
            "domain_finished": last_domain_result,
            "next_question": q,
            "last_correct": is_correct,
        }

    # 领域内继续
    q = _select_question(session)
    if q is None and not session.finished:
        _finish_domain(session, DIFFICULTY_TIERS[p.tier_index]["label"], "题目耗尽")
        last_domain_result = session.domain_results[-1]
        if not _advance_to_next_domain(session):
            final_theta = _estimate_final_theta(session.answers, session.prior_theta)
            return {
                "session_id": session_id,
                "finished": True,
                "stop_reason": session.stop_reason,
                "question_count": session.question_count,
                "domain_results": session.domain_results,
                "final_theta": final_theta,
                "answers": session.answers,
            }
        q = _select_question(session)
        return {
            "session_id": session_id,
            "finished": False,
            "question_count": session.question_count,
            "current_domain": session.progress.domain,
            "domain_index": session.domain_index,
            "domain_total": len(session.domains),
            "current_tier": _current_tier_label(session),
            "consecutive_correct": 0,
            "consecutive_wrong": 0,
            "domain_finished": last_domain_result,
            "next_question": q,
            "last_correct": is_correct,
        }

    return {
        "session_id": session_id,
        "finished": False,
        "question_count": session.question_count,
        "current_domain": session.progress.domain,
        "domain_index": session.domain_index,
        "domain_total": len(session.domains),
        "current_tier": _current_tier_label(session),
        "consecutive_correct": p.consecutive_correct,
        "consecutive_wrong": p.consecutive_wrong,
        "next_question": q,
        "last_correct": is_correct,
    }


def get_session(session_id: str) -> Optional[dict]:
    """查看会话状态"""
    s = _sessions.get(session_id)
    if not s:
        return None
    return {
        "session_id": s.session_id,
        "learner_id": s.learner_id,
        "finished": s.finished,
        "stop_reason": s.stop_reason,
        "question_count": s.question_count,
        "current_domain": s.progress.domain if s.progress else None,
        "domain_index": s.domain_index,
        "domain_total": len(s.domains),
        "current_tier": _current_tier_label(s),
        "domain_results": s.domain_results,
        "final_theta": _estimate_final_theta(s.answers, s.prior_theta) if s.finished else None,
        "answers": s.answers,
    }


# ============================================================
# 兼容接口 (main.py 依赖)
# ============================================================

def build_config(data: Optional[dict] = None) -> dict:
    """构建并校验最小可用自适应测试配置。"""
    data = data or {}
    domains = data.get("domains", list(DOMAINS))
    invalid_domains = [d for d in domains if d not in DOMAINS]
    if not domains or invalid_domains:
        raise ValueError(f"非法或空领域范围: {invalid_domains}")
    kp_ids = data.get("knowledge_point_ids") or []
    max_per_domain = data.get("max_questions_per_domain", MAX_QUESTIONS_PER_DOMAIN)
    stop_wrong = data.get("stop_consecutive_wrong", STOP_CONSECUTIVE_WRONG)
    if not 1 <= max_per_domain <= MAX_QUESTIONS_PER_DOMAIN:
        raise ValueError("max_questions_per_domain 必须在1到20之间")
    if not 1 <= stop_wrong <= 10:
        raise ValueError("stop_consecutive_wrong 必须在1到10之间")
    return {
        "domains": list(domains),
        "knowledge_point_ids": list(kp_ids),
        "difficulty_tiers": [t["label"] for t in DIFFICULTY_TIERS],
        "promote_consecutive_correct": PROMOTE_CONSECUTIVE_CORRECT,
        "stop_consecutive_wrong": stop_wrong,
        "max_questions_per_domain": max_per_domain,
    }


def default_config_payload() -> dict:
    """返回默认配置 (供内部参考, 不展示给用户)"""
    return {
        "domains": list(DOMAINS),
        "difficulty_tiers": [t["label"] for t in DIFFICULTY_TIERS],
        "promote_consecutive_correct": PROMOTE_CONSECUTIVE_CORRECT,
        "stop_consecutive_wrong": STOP_CONSECUTIVE_WRONG,
        "max_questions_per_domain": MAX_QUESTIONS_PER_DOMAIN,
    }
