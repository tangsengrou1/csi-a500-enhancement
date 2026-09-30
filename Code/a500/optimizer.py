from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class OptimizationResult:
    weights: pd.Series
    status: str
    expected_te: float
    one_way_turnover: float
    max_industry_deviation: float
    max_stock_deviation: float
    iterations: int


def _bounded_simplex(v: np.ndarray, lower: np.ndarray, upper: np.ndarray, target: float = 1.0) -> np.ndarray:
    lo, hi = -10.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        w = np.clip(v - mid, lower, upper)
        if w.sum() > target:
            lo = mid
        else:
            hi = mid
    return np.clip(v - (lo + hi) / 2, lower, upper)


def _project_industries(w: np.ndarray, wb: np.ndarray, industries: np.ndarray, limit: float, lower: np.ndarray, upper: np.ndarray) -> np.ndarray:
    out = w.copy()
    for industry in np.unique(industries):
        mask = industries == industry
        target = wb[mask].sum()
        current = out[mask].sum()
        capped = np.clip(current, max(0.0, target - limit), min(1.0, target + limit))
        if current > 0:
            out[mask] *= capped / current
        elif capped > 0:
            out[mask] = capped / mask.sum()
    return _bounded_simplex(out, lower, upper)


def optimize_portfolio(expected_returns: pd.Series, covariance: pd.DataFrame, benchmark: pd.Series, previous: pd.Series, industries: pd.Series, tradable: pd.Series, config: dict) -> OptimizationResult:
    assets = expected_returns.index
    mu = expected_returns.to_numpy(float)
    cov = covariance.reindex(index=assets, columns=assets).fillna(0).to_numpy(float)
    cov = (cov + cov.T) / 2 + np.eye(len(assets)) * 1e-8
    wb = benchmark.reindex(assets).fillna(0).to_numpy(float)
    wb = wb / wb.sum()
    prev = previous.reindex(assets).fillna(0).to_numpy(float)
    prev = prev / prev.sum() if prev.sum() else wb.copy()
    active_limit = config["stock_active_limit"]
    lower = np.maximum(0, wb - active_limit)
    upper = np.minimum(1, wb + active_limit)
    frozen = ~tradable.reindex(assets).fillna(False).to_numpy(bool)
    lower[frozen] = prev[frozen]
    upper[frozen] = prev[frozen]
    if lower.sum() > 1 + 1e-9 or upper.sum() < 1 - 1e-9:
        raise ValueError("个股或不可交易约束导致组合无可行解")

    w = _bounded_simplex(prev.copy(), lower, upper)
    step = 0.05
    risk_aversion = config["risk_aversion"]
    industry_values = industries.reindex(assets).fillna("UNKNOWN").to_numpy()
    max_iter = config["optimizer_iterations"]
    for iteration in range(1, max_iter + 1):
        old = w.copy()
        active = w - wb
        grad = -mu + 2 * risk_aversion * cov @ active + config["turnover_penalty"] * np.sign(w - prev)
        w = _bounded_simplex(w - step * grad, lower, upper)
        w = _project_industries(w, wb, industry_values, config["industry_active_limit"], lower, upper)
        turnover = 0.5 * np.abs(w - prev).sum()
        if turnover > config["weekly_one_way_turnover_limit"]:
            w = prev + (w - prev) * config["weekly_one_way_turnover_limit"] / turnover
        active = w - wb
        te = float(np.sqrt(max(active @ cov @ active, 0)) * np.sqrt(config["annualization_days"]))
        if te > config["tracking_error_limit"]:
            w = wb + active * config["tracking_error_limit"] / te
        w = _bounded_simplex(w, lower, upper)
        if np.max(np.abs(w - old)) < config["optimizer_tolerance"]:
            break

    # 数值投影可能在行业边界留下极小误差。没有冻结仓位时，沿基准方向收缩主动权重，
    # 同时单调降低跟踪误差、行业偏离和个股偏离。
    if not frozen.any():
        active = w - wb
        industry_devs = [abs(active[industry_values == x].sum()) for x in np.unique(industry_values)]
        scale_candidates = [1.0]
        if max(industry_devs, default=0) > 0:
            scale_candidates.append(config["industry_active_limit"] / max(industry_devs))
        if np.abs(active).max() > 0:
            scale_candidates.append(config["stock_active_limit"] / np.abs(active).max())
        te_now = float(np.sqrt(max(active @ cov @ active, 0)) * np.sqrt(config["annualization_days"]))
        if te_now > 0:
            scale_candidates.append(config["tracking_error_limit"] / te_now)
        alpha = min(scale_candidates) * (1 - 1e-10)
        if alpha < 1:
            w = wb + alpha * active
    turnover_now = 0.5 * np.abs(w - prev).sum()
    if turnover_now > config["weekly_one_way_turnover_limit"]:
        w = prev + (w - prev) * config["weekly_one_way_turnover_limit"] / turnover_now

    active = w - wb
    expected_te = float(np.sqrt(max(active @ cov @ active, 0)) * np.sqrt(config["annualization_days"]))
    turnover = float(0.5 * np.abs(w - prev).sum())
    industry_dev = max(abs(w[industry_values == x].sum() - wb[industry_values == x].sum()) for x in np.unique(industry_values))
    stock_dev = float(np.abs(active).max())
    tol = 2e-5
    feasible = expected_te <= config["tracking_error_limit"] + tol and turnover <= config["weekly_one_way_turnover_limit"] + tol and industry_dev <= config["industry_active_limit"] + tol and stock_dev <= config["stock_active_limit"] + tol and w.min() >= -tol and abs(w.sum() - 1) <= tol
    status = "OPTIMAL_APPROX" if feasible else "FAILED_CONSTRAINT_CHECK"
    return OptimizationResult(pd.Series(w, index=assets, name="weight"), status, expected_te, turnover, float(industry_dev), stock_dev, iteration)
