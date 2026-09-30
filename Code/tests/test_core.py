import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a500.black_litterman import black_litterman
from a500.optimizer import optimize_portfolio
from a500.pipeline import load_config


def test_black_litterman_shape_and_finiteness():
    cov = np.eye(3) * 0.0004
    result = black_litterman(cov, np.array([0.4, 0.3, 0.3]), np.array([0.01, -0.01, 0.005]), 0.5)
    assert result.shape == (3,)
    assert np.isfinite(result).all()


def test_optimizer_constraints():
    cfg = load_config(Path(__file__).parents[1] / "config.json")
    assets = pd.Index(["A", "B", "C", "D"])
    benchmark = pd.Series([0.25] * 4, index=assets)
    mu = pd.Series([0.02, 0.01, -0.01, -0.02], index=assets)
    cov = pd.DataFrame(np.eye(4) * 0.0001, index=assets, columns=assets)
    industries = pd.Series(["X", "X", "Y", "Y"], index=assets)
    result = optimize_portfolio(mu, cov, benchmark, benchmark, industries, pd.Series(True, index=assets), cfg)
    assert result.status == "OPTIMAL_APPROX"
    assert abs(result.weights.sum() - 1) < 1e-6
    assert result.weights.min() >= 0
    assert result.expected_te <= cfg["tracking_error_limit"] + 2e-5
    assert result.one_way_turnover <= cfg["weekly_one_way_turnover_limit"] + 2e-5

