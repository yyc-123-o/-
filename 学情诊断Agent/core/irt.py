"""IRT 2PL 模型 — 项目反应理论 (Two-Parameter Logistic Model)

核心公式: P(θ) = 1 / (1 + exp(-a * (θ - b)))
  θ: 学习者能力参数
  a: 题目区分度 (discrimination)
  b: 题目难度 (difficulty)
"""

from __future__ import annotations
import math
import warnings
import numpy as np
from scipy.optimize import minimize_scalar
from typing import List, Optional, Tuple


# adaptivetesting 1.2.1 imports ``warnings.deprecated``, introduced in
# Python 3.13. The project currently runs on Python 3.12.
if not hasattr(warnings, "deprecated"):
    def _deprecated(_message="", **_kwargs):
        return lambda func: func
    warnings.deprecated = _deprecated  # type: ignore[attr-defined]

try:
    import adaptivetesting as _cat
except Exception:  # pragma: no cover - optional dependency fallback
    _cat = None


# 学历 -> 能力先验 θ
EDUCATION_PRIOR_THETA = {
    "专科": -0.5,
    "本科": 0.0,
    "硕士": 0.5,
    "博士": 1.0,
}


def _clamp_theta(theta: float, lo: float = -4.0, hi: float = 4.0) -> float:
    """限制θ到合理范围"""
    return max(lo, min(hi, theta))


def probability(theta: float, a: float, b: float) -> float:
    """计算答对概率 P(correct | θ)

    P(θ) = 1 / (1 + exp(-a * (θ - b)))
    """
    z = a * (theta - b)
    # 防止数值溢出
    if z > 35:
        return 1.0 - 1e-10
    if z < -35:
        return 1e-10
    return 1.0 / (1.0 + np.exp(-z))


def neg_log_likelihood(
    theta: float,
    responses: List[Tuple[float, float, bool]],
) -> float:
    """负对数似然函数 (要最小化)

    responses: [(a, b, is_correct), ...]
    """
    ll = 0.0
    for a, b, correct in responses:
        p = probability(theta, a, b)
        p = np.clip(p, 1e-10, 1.0 - 1e-10)
        if correct:
            ll += np.log(p)
        else:
            ll += np.log(1.0 - p)
    return -ll


def estimate_theta(
    responses: List[Tuple[float, float, bool]],
    prior_theta: float = 0.0,
) -> float:
    """用MLE估计学习者能力参数 θ

    Args:
        responses: [(a, b, is_correct), ...] 答题记录
        prior_theta: 学历先验θ, 用于数据稀疏时的正则化

    Returns:
        估计的θ值, 范围 [-4, 4]
    """
    if not responses:
        return _clamp_theta(prior_theta)

    # 全对/全错的边界情况
    all_correct = all(r[2] for r in responses)
    all_wrong = all(not r[2] for r in responses)

    if all_correct and len(responses) >= 2:
        # 能力很高，取上限附近的值
        return 3.5
    if all_wrong and len(responses) >= 2:
        return -3.5

    # MLE: 最小化负对数似然
    # 加入弱正则项 (向先验靠拢), 防止过拟合
    def objective(theta: float) -> float:
        nll = neg_log_likelihood(theta, responses)
        # 弱L2正则: 向先验θ收缩, lambda=0.5
        reg = 0.5 * (theta - prior_theta) ** 2
        return nll + reg

    result = minimize_scalar(
        objective,
        bounds=(-4.0, 4.0),
        method="bounded",
    )
    return _clamp_theta(result.x)


def estimate_eap_theta(
    responses: List[Tuple[float, float, bool]],
    prior_theta: float = 0.0,
    prior_std: float = 1.0,
    use_library: bool = True,
) -> Tuple[float, Optional[float], str]:
    """Estimate ability with the same Bayesian EAP model used by CAT.

    Returns theta, posterior standard error and the method that produced the
    result. MLE remains a controlled fallback only when the optional CAT
    dependency is unavailable.
    """
    if not responses:
        return _clamp_theta(prior_theta), None, "prior-only"

    if use_library and _cat is not None:
        try:
            items = []
            pattern = []
            for index, (a, b, correct) in enumerate(responses):
                item = _cat.TestItem()
                item.id = f"response-{index}"
                item.a = float(a)
                item.b = float(b)
                item.c = 0.0
                item.d = 1.0
                items.append(item)
                pattern.append(1 if correct else 0)
            estimator = _cat.ExpectedAPosteriori(
                pattern,
                items,
                _cat.NormalPrior(float(prior_theta), float(prior_std)),
                optimization_interval=(-4, 4),
            )
            theta = float(estimator.get_estimation())
            standard_error = float(estimator.get_standard_error(theta))
            if math.isfinite(theta) and math.isfinite(standard_error):
                return _clamp_theta(theta), standard_error, "adaptivetesting-EAP"
        except Exception:
            # Fall through to the existing deterministic implementation.
            pass

    # For per-knowledge-point estimates, many small posteriors must be built
    # together. A fixed quadrature grid is mathematically the same EAP
    # integral, but avoids repeatedly invoking the third-party optimiser.
    theta_grid = np.linspace(-4.0, 4.0, 321)
    log_posterior = -0.5 * ((theta_grid - prior_theta) / prior_std) ** 2
    for a, b, correct in responses:
        p = np.array([probability(float(theta), float(a), float(b)) for theta in theta_grid])
        log_posterior += np.log(np.clip(p if correct else 1.0 - p, 1e-12, 1.0))
    log_posterior -= float(np.max(log_posterior))
    weights = np.exp(log_posterior)
    weights /= float(np.sum(weights))
    theta = float(np.sum(theta_grid * weights))
    variance = float(np.sum(((theta_grid - theta) ** 2) * weights))
    return _clamp_theta(theta), math.sqrt(max(variance, 0.0)), "grid-EAP"


def mastery_from_theta(theta: float, difficulty: float) -> float:
    """根据能力θ和知识点难度计算掌握度

    mastery = P(θ | a=1.0, b=difficulty)
    """
    return probability(theta, 1.0, difficulty)


def education_prior_theta(education_level: str) -> float:
    """根据学历层次获取先验θ"""
    return EDUCATION_PRIOR_THETA.get(education_level, 0.0)
