"""自适应测试引擎 — IRT-based 能力定位 + 难度梯度递进 + 可配置停止规则

策略 (v2.2 混合):
  1. 题库按「领域/知识点」分类过滤 (可选)
  2. 从当前难度档 (易→中→难) 中选难度最接近当前 θ 的题 (IRT 定位)
  3. 当前档正确率达到阈值 → 晋升下一档 (难度递增体验)
  4. 错多了就停 / θ 收敛 / 达最大题数 / 通过全部难度档

Session 生命周期:
  start → answer → answer → ... → finish (返回最终 θ + 停止原因)

配置 (AdaptiveConfig):
  - domains / knowledge_point_ids    分类测试过滤
  - difficulty_stages                难度梯度 (label/low/high/promote_accuracy/min_questions)
  - max_questions / min_questions    题数上下界
  - consecutive_wrong_stop           连续答错停止
  - convergence_threshold            θ 收敛阈值
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from core import irt


# ============================================================
# 配置数据模型
# ============================================================

@dataclass
class DifficultyStage:
    """单个难度档"""
    label: str                     # 中文标签: 易/中/难
    low: float                     # 该档难度下限 (IRT b)
    high: float                    # 该档难度上限 (IRT b)
    promote_accuracy: float = 0.70 # 晋升到下一档所需正确率
    min_questions: int = 2         # 晋升前本档最少答题数


def _default_stages() -> List[DifficultyStage]:
    return [
        DifficultyStage(label="易", low=-3.0, high=-0.2, promote_accuracy=0.70, min_questions=2),
        DifficultyStage(label="中", low=-0.2, high=0.8, promote_accuracy=0.65, min_questions=2),
        DifficultyStage(label="难", low=0.8, high=3.0, promote_accuracy=0.60, min_questions=1),
    ]


@dataclass
class AdaptiveConfig:
    """自适应测试配置 — 全部可配置, 默认行为与旧版等价"""
    domains: Optional[List[str]] = None
    knowledge_point_ids: Optional[List[str]] = None
    difficulty_stages: List[DifficultyStage] = field(default_factory=_default_stages)
    max_questions: int = 30
    min_questions: int = 8
    consecutive_wrong_stop: int = 3
    convergence_threshold: float = 0.15


def build_config(data: Optional[dict] = None) -> AdaptiveConfig:
    """从 dict 构建配置 — 供 API 层使用, 容忍部分字段缺失"""
    data = data or {}
    stages = None
    raw_stages = data.get("difficulty_stages")
    if raw_stages:
        stages = [
            DifficultyStage(
                label=s.get("label", f"档{i + 1}"),
                low=float(s.get("low", -3.0)),
                high=float(s.get("high", 3.0)),
                promote_accuracy=float(s.get("promote_accuracy", 0.70)),
                min_questions=int(s.get("min_questions", 2)),
            )
            for i, s in enumerate(raw_stages)
        ]
    cfg = AdaptiveConfig(
        domains=data.get("domains") or None,
        knowledge_point_ids=data.get("knowledge_point_ids") or None,
        max_questions=int(data.get("max_questions", 30)),
        min_questions=int(data.get("min_questions", 8)),
        consecutive_wrong_stop=int(data.get("consecutive_wrong_stop", 3)),
        convergence_threshold=float(data.get("convergence_threshold", 0.15)),
    )
    if stages:
        cfg.difficulty_stages = stages
    if cfg.max_questions < 1 or cfg.min_questions < 1 or cfg.min_questions > cfg.max_questions:
        raise ValueError("max_questions 和 min_questions 必须为正数，且 min_questions <= max_questions")
    if cfg.consecutive_wrong_stop < 0 or cfg.convergence_threshold < 0:
        raise ValueError("停止条件不能为负数")
    if not cfg.difficulty_stages:
        raise ValueError("至少需要一个难度阶段")
    for stage in cfg.difficulty_stages:
        if stage.low > stage.high or not 0 <= stage.promote_accuracy <= 1 or stage.min_questions < 1:
            raise ValueError("难度阶段范围、晋升正确率或最少题数无效")
    return cfg


def default_config_payload() -> dict:
    """返回默认配置的可序列化表示 (供前端渲染)"""
    cfg = AdaptiveConfig()
    return {
        "difficulty_stages": [
            {"label": s.label, "low": s.low, "high": s.high,
             "promote_accuracy": s.promote_accuracy, "min_questions": s.min_questions}
            for s in cfg.difficulty_stages
        ],
        "max_questions": cfg.max_questions,
        "min_questions": cfg.min_questions,
        "consecutive_wrong_stop": cfg.consecutive_wrong_stop,
        "convergence_threshold": cfg.convergence_threshold,
    }


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
    # v2.2 新增
    config: AdaptiveConfig = field(default_factory=AdaptiveConfig)
    bank: List[dict] = field(default_factory=list)
    current_stage: int = 0
    stage_answers: List[bool] = field(default_factory=list)
    current_question_id: Optional[str] = None


# 内存存储
_sessions: Dict[str, AdaptiveSession] = {}


# ============================================================
# 题库过滤
# ============================================================

def _filter_bank(test_bank: List[dict], config: AdaptiveConfig) -> List[dict]:
    """按领域/知识点过滤题库 (分类测试)"""
    bank = list(test_bank)
    if config.domains:
        ds = set(config.domains)
        bank = [q for q in bank if q.get("domain") in ds]
    if config.knowledge_point_ids:
        kps = set(config.knowledge_point_ids)
        bank = [q for q in bank if q.get("knowledge_point_id") in kps]
    return bank


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


# ============================================================
# 选题策略 (IRT 定位 + 难度梯度约束)
# ============================================================

def _select_next_question(session: AdaptiveSession, bank: List[dict]) -> Optional[dict]:
    """在当前难度档的 b 范围内, 选难度最接近当前 θ 的未答题

    - 当前档题目耗尽时, 自动推进到下一个仍有剩余题目的档
    - 优先在本档内选, 本档彻底无题则回退到全库最近 θ
    """
    answered_ids = {a["question_id"] for a in session.answers}
    remaining = [q for q in bank if q["question_id"] not in answered_ids]
    if not remaining:
        return None

    stages = session.config.difficulty_stages
    # 当前档无剩余题时, 推进到下一个有题的档
    while session.current_stage < len(stages) - 1:
        stage = stages[session.current_stage]
        if any(stage.low <= q["difficulty"] <= stage.high for q in remaining):
            break
        session.current_stage += 1
        session.stage_answers = []

    stage = stages[session.current_stage]
    in_stage = [q for q in remaining if stage.low <= q["difficulty"] <= stage.high]
    pool = in_stage if in_stage else remaining

    pool.sort(key=lambda q: abs(q["difficulty"] - session.current_theta))
    top = pool[:min(3, len(pool))]
    rng = np.random.default_rng()
    return top[rng.integers(0, len(top))]


# ============================================================
# 难度梯度推进
# ============================================================

def _advance_stage(session: AdaptiveSession) -> bool:
    """当前档达到晋升条件则进入下一档, 返回是否晋升"""
    stages = session.config.difficulty_stages
    idx = session.current_stage
    stage = stages[idx]
    if len(session.stage_answers) >= stage.min_questions:
        acc = sum(session.stage_answers) / len(session.stage_answers)
        if acc >= stage.promote_accuracy and idx < len(stages) - 1:
            session.current_stage += 1
            session.stage_answers = []
            return True
    return False


def _last_stage_completed(session: AdaptiveSession) -> bool:
    """最后一档是否也已达到通过条件 (作为完成信号)"""
    stages = session.config.difficulty_stages
    idx = session.current_stage
    if idx != len(stages) - 1:
        return False
    stage = stages[idx]
    if len(session.stage_answers) >= stage.min_questions:
        acc = sum(session.stage_answers) / len(session.stage_answers)
        return acc >= stage.promote_accuracy
    return False


# ============================================================
# 停止规则
# ============================================================

def _should_stop(session: AdaptiveSession) -> Tuple[bool, str]:
    """检查停止条件 (使用配置值)"""
    cfg = session.config
    answers = session.answers
    n = len(answers)

    if n >= cfg.max_questions:
        return True, f"已达最大题数 {cfg.max_questions}"

    # 连续错
    if cfg.consecutive_wrong_stop and n >= cfg.consecutive_wrong_stop:
        last_n = answers[-cfg.consecutive_wrong_stop:]
        if all(not a["is_correct"] for a in last_n):
            return True, f"连续错 {cfg.consecutive_wrong_stop} 题"

    # θ 收敛
    if n >= cfg.min_questions:
        recent_thetas = [a["theta_after"] for a in answers[-4:]]
        theta_range = max(recent_thetas) - min(recent_thetas)
        if theta_range < cfg.convergence_threshold:
            return True, f"θ 已收敛 (波动 {theta_range:.3f} < {cfg.convergence_threshold})"

    # 通过全部难度档
    if n >= cfg.min_questions and _last_stage_completed(session):
        return True, "已通过全部难度档"

    return False, ""


# ============================================================
# 会话状态序列化
# ============================================================

def _stage_meta(session: AdaptiveSession) -> dict:
    """当前难度档的展示元信息"""
    stages = session.config.difficulty_stages
    idx = min(session.current_stage, len(stages) - 1)
    stage = stages[idx]
    return {
        "current_stage": idx,
        "current_stage_label": stage.label,
        "difficulty_range": [stage.low, stage.high],
        "stages": [{"label": s.label, "low": s.low, "high": s.high} for s in stages],
        "stage_progress": {
            "answered": len(session.stage_answers),
            "min_questions": stage.min_questions,
            "accuracy": round(sum(session.stage_answers) / len(session.stage_answers), 3)
            if session.stage_answers else None,
            "promote_accuracy": stage.promote_accuracy,
        },
    }


# ============================================================
# API: 启动 / 答题 / 状态
# ============================================================

def start_session(
    learner_id: str,
    prior_theta: float,
    test_bank: List[dict],
    config: Optional[AdaptiveConfig] = None,
) -> dict:
    """启动一次自适应测试会话, 返回第一道题"""
    import uuid
    cfg = config if config is not None else AdaptiveConfig()
    bank = _filter_bank(test_bank, cfg)

    sid = f"sess_{uuid.uuid4().hex[:8]}"
    session = AdaptiveSession(
        session_id=sid,
        learner_id=learner_id,
        started_at=datetime.now().isoformat(),
        prior_theta=prior_theta,
        current_theta=prior_theta,
        config=cfg,
        bank=bank,
    )
    _sessions[sid] = session

    # 选第一道题
    q = _select_next_question(session, bank)
    session.current_question_id = q["question_id"] if q else None
    result = {
        "session_id": sid,
        "current_theta": prior_theta,
        "question_count": 0,
        "next_question": public_question(q) if q else None,
        "finished": False,
        "bank_size": len(bank),
        "category": {"domains": cfg.domains, "knowledge_point_ids": cfg.knowledge_point_ids},
    }
    result.update(_stage_meta(session))
    return result


def submit_answer(
    session_id: str,
    question_id: str,
    selected_answer: Optional[int],
    time_spent: int,
    test_bank: List[dict],
) -> dict:
    """提交答案, 更新 θ 与难度档, 返回下一题或停止"""
    session = _sessions.get(session_id)
    if not session:
        return {"error": "会话不存在"}
    if session.finished:
        return {"error": "会话已结束", "finished": True, "stop_reason": session.stop_reason}

    bank = session.bank if session.bank else test_bank

    if session.current_question_id != question_id:
        return {"error": "提交的题目不是当前会话要求回答的题目"}

    # 找到这道题
    q = next((x for x in bank if x["question_id"] == question_id), None)
    if q is None:
        q = next((x for x in test_bank if x["question_id"] == question_id), None)
    if not q:
        return {"error": "题目不存在"}

    if isinstance(selected_answer, bool) or not isinstance(selected_answer, int):
        return {"error": "selected_answer 必须是整数选项下标"}
    if selected_answer < 0 or selected_answer >= len(q.get("options", [])):
        return {"error": "选项无效"}
    if "correct_answer" not in q:
        return {"error": "必须提交题目选项，且该题必须包含服务端答案"}
    is_correct = selected_answer == q["correct_answer"]

    # 使用会话全部作答记录估计 θ；难度档只负责选题和解释，不替代 IRT。
    responses = [
        (answer["discrimination"], answer["difficulty"], answer["is_correct"])
        for answer in session.answers
    ]
    responses.append((q["discrimination"], q["difficulty"], is_correct))
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
        "stage": session.current_stage,
    })
    session.current_theta = new_theta
    session.stage_answers.append(bool(is_correct))

    # 难度梯度推进
    _advance_stage(session)

    # 检查停止
    should_stop, reason = _should_stop(session)

    if should_stop:
        session.finished = True
        session.current_question_id = None
        session.stop_reason = reason
        session.final_theta = new_theta
        result = {
            "session_id": session_id,
            "current_theta": round(new_theta, 4),
            "question_count": len(session.answers),
            "finished": True,
            "stop_reason": reason,
            "final_theta": round(new_theta, 4),
            "answers": session.answers,
            "last_correct": is_correct,
        }
        result.update(_stage_meta(session))
        return result

    # 选下一题
    next_q = _select_next_question(session, bank)
    if not next_q:
        session.finished = True
        session.current_question_id = None
        session.stop_reason = "题库耗尽"
        session.final_theta = new_theta
        result = {
            "session_id": session_id,
            "current_theta": round(new_theta, 4),
            "question_count": len(session.answers),
            "finished": True,
            "stop_reason": "题库耗尽",
            "final_theta": round(new_theta, 4),
            "answers": session.answers,
            "last_correct": is_correct,
        }
        result.update(_stage_meta(session))
        return result

    session.current_question_id = next_q["question_id"]
    result = {
        "session_id": session_id,
        "current_theta": round(new_theta, 4),
        "question_count": len(session.answers),
        "next_question": public_question(next_q),
        "finished": False,
        "last_correct": is_correct,
    }
    result.update(_stage_meta(session))
    return result


def get_session(session_id: str) -> Optional[dict]:
    """获取会话状态"""
    s = _sessions.get(session_id)
    if not s:
        return None
    result = {
        "session_id": s.session_id,
        "learner_id": s.learner_id,
        "started_at": s.started_at,
        "current_theta": round(s.current_theta, 4),
        "question_count": len(s.answers),
        "finished": s.finished,
        "stop_reason": s.stop_reason,
        "final_theta": round(s.final_theta, 4) if s.final_theta else None,
        "current_question_id": s.current_question_id,
        "answers": s.answers,
    }
    result.update(_stage_meta(s))
    return result
