from __future__ import annotations

import numpy as np


def black_litterman(cov: np.ndarray, benchmark_weights: np.ndarray, factor_view: np.ndarray, confidence: float, tau: float = 0.05, risk_aversion: float = 2.5) -> np.ndarray:
    """将逐股因子观点与市场均衡收益融合，P 使用单位阵。"""
    n = len(benchmark_weights)
    pi = risk_aversion * cov @ benchmark_weights
    prior_cov = tau * cov + np.eye(n) * 1e-10
    confidence = float(np.clip(confidence, 0.05, 0.95))
    omega = np.diag(np.maximum(np.diag(prior_cov) * (1 - confidence) / confidence, 1e-10))
    inv_prior = np.linalg.pinv(prior_cov)
    inv_omega = np.linalg.pinv(omega)
    posterior_cov = np.linalg.pinv(inv_prior + inv_omega)
    return posterior_cov @ (inv_prior @ pi + inv_omega @ factor_view)

