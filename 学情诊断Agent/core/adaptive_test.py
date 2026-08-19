"""自适应测试引擎 — IRT-based 难度递进 + 停止规则

协议 (比赛方案 Step 1):
  1. 从题库中选中等难度题 (b ≈ learner θ)
  2. 用户答题 → 更新 θ 估计
  3. 下一题难度靠近当前 θ
  4. 错多了就停 (连续错 ≥3 或 θ 收敛)

Session 生命周期:
  start → answer → answer → ... → finish (返回最终 θ + 停止原因)
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from core import irt


# ============================================================
# 会话数据模型
# ============================================================

@dataclass
class AdaptiveSession:
    session_id: str
    learner_id: str
    started_at: str
    prior_theta: float = 0.0
    current_theta: float = 0.0
    answers: List[dict] = field(default_factory=list)
    finished: bool = False
    stop_reason: str = ""
    final_theta: Optional[float] = None


# 内存存储
_sessions: Dict[str, AdaptiveSession] = {}


# ============================================================
# 停止规则
# ============================================================

MAX_QUESTIONS = 30
CONSECUTIVE_WRONG_STOP = 3
CONVERGENCE_THRESHOLD = 0.15  # θ 变化 < 此值且已答 ≥8 题


def _should_stop(session: AdaptiveSession) -> Tuple[bool, str]:
    """检查停止条件"""
    answers = session.answers
    n = len(answers)

    if n >= MAX_QUESTIONS:
        return True, f"已达最大题数 {MAX_QUESTIONS}"

    # 连续错
    if n >= CONSECUTIVE_WRONG_STOP:
        last_n = answers[-CONSECUTIVE_WRONG_STOP:]
        if all(not a["is_correct"] for a in last_n):
            return True, f"连续错 {CONSECUTIVE_WRONG_STOP} 题"

    # θ 收敛
    if n >= 8:
        recent_thetas = [a["theta_after"] for a in answers[-4:]]
        theta_range = max(recent_thetas) - min(recent_thetas)
        if theta_range < CONVERGENCE_THRESHOLD:
            return True, f"θ 已收敛 (波动 {theta_range:.3f} < {CONVERGENCE_THRESHOLD})"

    return False, ""


# ============================================================
# 选题策略
# ============================================================

def _select_next_question(
    theta: float,
    test_bank: List[dict],
    answered_ids: set,
) -> Optional[dict]:
    """根据当前 θ 选题 — 选难度最接近 θ 的未答题"""
    candidates = [q for q in test_bank if q["question_id"] not in answered_ids]
    if not candidates:
        return None

    # 按 |b - θ| 排序，取最近的
    candidates.sort(key=lambda q: abs(q["difficulty"] - theta))
    # 加一点随机性：在前 3 个中随机选
    pool = candidates[:min(3, len(candidates))]
    return pool[np.random.default_rng().integers(0, len(pool))]


# ============================================================
# API: 启动 / 答题 / 状态
# ============================================================

def start_session(
    learner_id: str,
    prior_theta: float,
    test_bank: List[dict],
) -> dict:
    """启动一次自适应测试会话，返回第一道题"""
    import uuid
    sid = f"sess_{uuid.uuid4().hex[:8]}"
    session = AdaptiveSession(
        session_id=sid,
        learner_id=learner_id,
        started_at=datetime.now().isoformat(),
        prior_theta=prior_theta,
        current_theta=prior_theta,
    )
    _sessions[sid] = session

    # 选第一道题
    q = _select_next_question(prior_theta, test_bank, set())
    return {
        "session_id": sid,
        "current_theta": prior_theta,
        "question_count": 0,
        "next_question": q,
        "finished": False,
    }


def submit_answer(
    session_id: str,
    question_id: str,
    is_correct: bool,
    time_spent: int,
    test_bank: List[dict],
) -> dict:
    """提交答案，更新 θ，返回下一题或停止"""
    session = _sessions.get(session_id)
    if not session:
        return {"error": "会话不存在"}
    if session.finished:
        return {"error": "会话已结束", "finished": True, "stop_reason": session.stop_reason}

    # 找到这道题
    q = next((q for q in test_bank if q["question_id"] == question_id), None)
    if not q:
        return {"error": "题目不存在"}

    # 更新 θ
    responses = [(q["discrimination"], q["difficulty"], is_correct)]
    new_theta = irt.estimate_theta(responses, prior_theta=session.current_theta)

    # 记录答题
    session.answers.append({
        "question_id": question_id,
        "kp_id": q["knowledge_point_id"],
        "difficulty": q["difficulty"],
        "discrimination": q["discrimination"],
        "is_correct": is_correct,
        "time_spent": time_spent,
        "theta_before": session.current_theta,
        "theta_after": new_theta,
    })
    session.current_theta = new_theta

    # 检查停止
    should_stop, reason = _should_stop(session)
    answered_ids = {a["question_id"] for a in session.answers}

    if should_stop:
        session.finished = True
        session.stop_reason = reason
        session.final_theta = new_theta
        return {
            "session_id": session_id,
            "current_theta": round(new_theta, 4),
            "question_count": len(session.answers),
            "finished": True,
            "stop_reason": reason,
            "final_theta": round(new_theta, 4),
            "answers": session.answers,
        }

    # 选下一题
    next_q = _select_next_question(new_theta, test_bank, answered_ids)
    if not next_q:
        session.finished = True
        session.stop_reason = "题库耗尽"
        session.final_theta = new_theta
        return {
            "session_id": session_id,
            "current_theta": round(new_theta, 4),
            "question_count": len(session.answers),
            "finished": True,
            "stop_reason": "题库耗尽",
            "final_theta": round(new_theta, 4),
            "answers": session.answers,
        }

    return {
        "session_id": session_id,
        "current_theta": round(new_theta, 4),
        "question_count": len(session.answers),
        "next_question": next_q,
        "finished": False,
    }


def get_session(session_id: str) -> Optional[dict]:
    """获取会话状态"""
    s = _sessions.get(session_id)
    if not s:
        return None
    return {
        "session_id": s.session_id,
        "learner_id": s.learner_id,
        "started_at": s.started_at,
        "current_theta": round(s.current_theta, 4),
        "question_count": len(s.answers),
        "finished": s.finished,
        "stop_reason": s.stop_reason,
        "final_theta": round(s.final_theta, 4) if s.final_theta else None,
        "answers": s.answers,
    }
