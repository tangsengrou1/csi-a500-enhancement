import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a500.factor_evaluation import (
    evaluate_factors,
    one_way_turnover,
    rank_ic_metrics,
    spearman_correlation,
    scores_to_weights,
    standardize_market_data,
)
from a500.factor_registry import make_basic_registry


def make_market(seed: int = 11, n_assets: int = 40, n_days: int = 150):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-02", periods=n_days)
    codes = [f"{i:06d}.SZ" for i in range(1, n_assets + 1)]
    returns = rng.normal(0.0003, 0.012, (n_days, n_assets))
    close = 100 * np.cumprod(1 + returns, axis=0)
    rows = n_days * n_assets
    market = pd.DataFrame({
        "trade_dt": np.repeat(dates, n_assets),
        "securityID": np.tile(codes, n_days),
        "close": close.ravel(),
        "volume": rng.uniform(1e6, 1e8, rows),
        "turn": rng.uniform(0.1, 5.0, rows),
    })
    weekly = dates.to_series().groupby(dates.to_period("W-FRI")).max().to_numpy()
    constituents = pd.DataFrame({
        "date": np.repeat(weekly, n_assets),
        "wind_code": np.tile(codes, len(weekly)),
        "weight": 1 / n_assets,
    })
    return market, constituents


def base_config():
    return {
        "rebalance_frequency": "W-FRI",
        "price_field": "close",
        "position_mapping": "top_quantile_equal_weight",
        "top_fraction": 0.20,
        "minimum_stocks": 10,
        "ic_minimum_stocks": 10,
        "correlation_minimum_stocks": 10,
        "periods_per_year": 52,
        "winsorize_lower": 0.01,
        "winsorize_upper": 0.99,
        "transaction_cost_bps": 20,
        "risk_free_annual": 0.02,
        "drop_weekends": True,
        "allow_development_universe": False,
    }


def test_aliases_and_duplicate_guard():
    market, _ = make_market(n_assets=12, n_days=5)
    standardized = standardize_market_data(market)
    assert {"date", "wind_code", "volume", "turnover"}.issubset(standardized.columns)
    duplicate = pd.concat([market, market.iloc[[0]]], ignore_index=True)
    try:
        standardize_market_data(duplicate)
        raise AssertionError("重复键应触发异常")
    except ValueError as exc:
        assert "重复" in str(exc)


def test_position_mapping_and_turnover():
    scores = pd.Series(range(20), index=[f"S{i}" for i in range(20)])
    weights = scores_to_weights(scores, base_config())
    assert len(weights) == 4
    assert abs(weights.sum() - 1) < 1e-12
    assert one_way_turnover(weights, pd.Series(dtype=float)) == 1.0
    assert one_way_turnover(weights, weights) == 0.0


def test_all_position_mapping_options():
    scores = pd.Series(np.linspace(-2, 2, 20), index=[f"S{i}" for i in range(20)])
    modes = [
        "top_quantile_equal_weight",
        "top_quantile_rank_weighted",
        "rank_weighted_long_only",
        "score_proportional_long_only",
        "softmax_long_only",
        "linear_rank_tilt",
    ]
    for mode in modes:
        config = base_config()
        config["position_mapping"] = mode
        weights = scores_to_weights(scores, config)
        assert not weights.empty
        assert abs(weights.sum() - 1) < 1e-12
        assert (weights >= 0).all()
        assert weights.loc["S19"] >= weights.iloc[0]

    top_config = base_config()
    top_config["position_mapping"] = "top_quantile_rank_weighted"
    assert len(scores_to_weights(scores, top_config)) == 4


def test_position_mapping_parameter_validation():
    scores = pd.Series(range(20), index=[f"S{i}" for i in range(20)])
    invalid_cases = [
        ("top_quantile_equal_weight", "top_fraction", 0),
        ("rank_weighted_long_only", "rank_exponent", 0),
        ("score_proportional_long_only", "score_floor", 0),
        ("softmax_long_only", "softmax_temperature", 0),
        ("linear_rank_tilt", "rank_tilt_strength", -1),
    ]
    for mode, parameter, value in invalid_cases:
        config = base_config()
        config["position_mapping"] = mode
        config[parameter] = value
        try:
            scores_to_weights(scores, config)
            raise AssertionError(f"{parameter} 非法时应触发异常")
        except ValueError:
            pass


def test_all_position_mappings_run_end_to_end():
    market, constituents = make_market(n_assets=25, n_days=80)
    for mode in [
        "top_quantile_equal_weight",
        "top_quantile_rank_weighted",
        "rank_weighted_long_only",
        "score_proportional_long_only",
        "softmax_long_only",
        "linear_rank_tilt",
    ]:
        config = base_config()
        config["position_mapping"] = mode
        result = evaluate_factors(
            market, constituents, make_basic_registry(), ["momentum_20"], config,
        )
        assert result.summary.iloc[0]["periods"] > 0
        assert (result.weights["weight"] >= 0).all()
        assert (result.weights.groupby("execution_date")["weight"].sum() - 1).abs().max() < 1e-10


def test_weekly_factor_evaluation_outputs_and_timing():
    market, constituents = make_market()
    result = evaluate_factors(
        market,
        constituents,
        make_basic_registry(),
        ["momentum_20", "reversal_5", "low_volatility_20"],
        base_config(),
    )
    assert set(result.summary["factor_id"]) == {
        "momentum_20", "reversal_5", "low_volatility_20",
    }
    assert (result.summary["periods"] > 0).all()
    assert result.summary[["cumulative_return", "annual_volatility", "max_drawdown"]].notna().all().all()
    assert (result.weights.groupby(["factor_id", "execution_date"])["weight"].sum() - 1).abs().max() < 1e-10
    ok = result.diagnostics[result.diagnostics["status"] == "OK"]
    assert (pd.to_datetime(ok["execution_date"]) > pd.to_datetime(ok["signal_date"])).all()
    assert (pd.to_datetime(ok["exit_date"]) > pd.to_datetime(ok["execution_date"])).all()
    assert set(ok["universe_type"]) == {"HISTORICAL_CONSTITUENTS"}
    assert {"rank_ic_mean", "rank_icir", "rank_icir_annualized"}.issubset(result.summary.columns)
    assert result.rank_ic["rank_ic"].dropna().between(-1, 1).all()
    assert set(result.factor_correlation_summary[["factor_a", "factor_b"]].stack()).issubset(
        {"momentum_20", "reversal_5", "low_volatility_20"},
    )
    assert result.factor_correlation_matrix.shape == (3, 3)
    assert np.allclose(np.diag(result.factor_correlation_matrix), 1.0)


def test_rank_ic_detects_predictive_ordering():
    scores = pd.Series(range(20), index=[f"S{i}" for i in range(20)])
    forward_returns = scores * 0.01
    assert spearman_correlation(scores, forward_returns) == 1.0
    assert spearman_correlation(scores, -forward_returns) == -1.0
    metrics = rank_ic_metrics(pd.Series([0.1, 0.2, 0.3]), periods_per_year=52)
    assert np.isclose(metrics["rank_ic_mean"], 0.2)
    assert np.isclose(metrics["rank_icir"], 2.0)
    assert np.isclose(metrics["rank_icir_annualized"], 2.0 * np.sqrt(52))


def test_formal_run_requires_constituents():
    market, _ = make_market(n_assets=20, n_days=80)
    try:
        evaluate_factors(market, None, make_basic_registry(), ["momentum_20"], base_config())
        raise AssertionError("正式评价缺少历史成分股时应失败")
    except ValueError as exc:
        assert "历史成分股" in str(exc)
