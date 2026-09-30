from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .black_litterman import black_litterman
from .factors import FACTOR_COLUMNS, build_factor_snapshot, rank_ic, rolling_factor_weights
from .io import DataBundle, audit_bundle
from .metrics import performance_metrics, rolling_tracking_error
from .optimizer import optimize_portfolio


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _latest_snapshot(df: pd.DataFrame, date: pd.Timestamp, date_col: str = "date") -> pd.DataFrame:
    dates = df.loc[df[date_col] <= date, date_col]
    if dates.empty:
        return df.iloc[0:0]
    return df[df[date_col] == dates.max()]


def run_backtest(bundle: DataBundle, config: dict, output_dir: str | Path, label: str = "official") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit = audit_bundle(bundle)
    audit.to_csv(out / "data_audit.csv", index=False)
    if (audit["status"] == "FAIL").any():
        raise ValueError("数据审计失败，详见 data_audit.csv")

    price = bundle.prices.pivot(index="date", columns="wind_code", values="adj_close").sort_index()
    stock_returns = price.pct_change(fill_method=None)
    benchmark_level = bundle.benchmark.set_index("date")["total_return_close"].sort_index()
    benchmark_returns = benchmark_level.pct_change(fill_method=None)
    constituent_dates = pd.Index(sorted(bundle.constituents["date"].unique()))
    rebalance_dates = price.index.to_series().groupby(price.index.to_period("W-FRI")).max()
    rebalance_dates = pd.DatetimeIndex(rebalance_dates)
    rebalance_dates = rebalance_dates[rebalance_dates >= constituent_dates.min()]

    previous = pd.Series(dtype=float)
    ic_history = pd.DataFrame(columns=FACTOR_COLUMNS, dtype=float)
    prior_scores = None
    weight_records, diagnostic_records = [], []
    strategy_daily = pd.Series(0.0, index=price.index, name="strategy")
    equal_weight_daily = pd.Series(0.0, index=price.index, name="equal_weight")

    for i, signal_date in enumerate(rebalance_dates[:-1]):
        execution_date = price.index[price.index.get_indexer([signal_date], method="bfill")[0] + 1] if signal_date < price.index[-1] else None
        if execution_date is None:
            continue
        cs = _latest_snapshot(bundle.constituents, signal_date)
        if cs.empty:
            continue
        benchmark = cs.set_index("wind_code")["weight"].astype(float)
        benchmark = benchmark / benchmark.sum()
        universe = benchmark.index.intersection(price.columns)
        if len(universe) < 10:
            continue
        hist = stock_returns.loc[:signal_date, universe].tail(config["covariance_lookback"])
        valid = hist.notna().sum() >= config["minimum_history"]
        universe = universe[valid]
        if len(universe) < 10:
            continue
        benchmark = benchmark.reindex(universe).fillna(0)
        benchmark /= benchmark.sum()
        ind = _latest_snapshot(bundle.industry.rename(columns={"effective_date": "date"}), signal_date).set_index("wind_code")["industry"].reindex(universe).fillna("UNKNOWN")
        factors = build_factor_snapshot(signal_date, universe, bundle.prices, bundle.valuation, bundle.fundamentals, ind, config)
        if prior_scores is not None:
            realized = stock_returns.loc[prior_scores.name:signal_date, prior_scores.index].add(1).prod().sub(1)
            ic_history.loc[signal_date] = rank_ic(prior_scores, realized)
        factor_weights = rolling_factor_weights(ic_history, config["ic_lookback_weeks"], config["min_ic_observations"])
        active_factors = config.get("active_factors", FACTOR_COLUMNS)
        selected_weights = factor_weights.reindex(active_factors).fillna(0)
        selected_weights = selected_weights / selected_weights.sum() if selected_weights.sum() else pd.Series(1 / len(active_factors), index=active_factors)
        composite = factors[active_factors].mul(selected_weights).sum(axis=1)
        prior_scores = factors[FACTOR_COLUMNS].copy()
        prior_scores.name = signal_date
        weekly_scale = hist.std().median() * np.sqrt(5)
        view = composite / max(composite.abs().max(), 1e-12) * weekly_scale
        cov = hist.cov().fillna(0)
        confidence = float(np.clip(ic_history.tail(config["ic_lookback_weeks"]).mean().abs().mean() * 5, 0.05, 0.8)) if not ic_history.empty else 0.05
        posterior = black_litterman(cov.to_numpy(), benchmark.to_numpy(), view.to_numpy(), confidence, config["bl_tau"], config["bl_risk_aversion"]) if config.get("use_black_litterman", True) else view.to_numpy()
        expected = pd.Series(posterior, index=universe)
        px_today = bundle.prices[bundle.prices["date"] == signal_date].set_index("wind_code").reindex(universe)
        tradable = px_today["trade_status"].eq("交易") & px_today["limit_status"].eq("正常")
        result = optimize_portfolio(expected, cov, benchmark, previous, ind, tradable, config)
        if result.status != "OPTIMAL_APPROX":
            raise RuntimeError(
                f"{signal_date.date()} 优化失败: {result.status}; "
                f"TE={result.expected_te:.6f}, turnover={result.one_way_turnover:.6f}, "
                f"industry={result.max_industry_deviation:.6f}, stock={result.max_stock_deviation:.6f}"
            )
        next_signal = rebalance_dates[i + 1]
        holding_dates = stock_returns.index[(stock_returns.index >= execution_date) & (stock_returns.index <= next_signal)]
        gross = stock_returns.loc[holding_dates, universe].fillna(0).mul(result.weights, axis=1).sum(axis=1)
        equal_gross = stock_returns.loc[holding_dates, universe].fillna(0).mean(axis=1)
        cost = result.one_way_turnover * config["transaction_cost_bps"] / 10000
        if len(gross):
            gross.iloc[0] -= cost
            strategy_daily.loc[holding_dates] = gross
            equal_weight_daily.loc[holding_dates] = equal_gross
        for code, weight in result.weights.items():
            weight_records.append({"signal_date": signal_date, "execution_date": execution_date, "wind_code": code, "weight": weight, "benchmark_weight": benchmark[code], "industry": ind[code]})
        diagnostic_records.append({"signal_date": signal_date, "status": result.status, "expected_te": result.expected_te, "one_way_turnover": result.one_way_turnover, "max_industry_deviation": result.max_industry_deviation, "max_stock_deviation": result.max_stock_deviation, "iterations": result.iterations, "confidence": confidence})
        previous = result.weights

    diagnostics = pd.DataFrame(diagnostic_records)
    weights = pd.DataFrame(weight_records)
    if diagnostics.empty:
        raise ValueError("未生成任何有效调仓记录，请检查历史长度和数据覆盖")
    active_dates = strategy_daily.index[strategy_daily.ne(0)]
    strategy = strategy_daily.loc[active_dates.min():]
    benchmark_returns = benchmark_returns.reindex(strategy.index)
    risk_free = bundle.risk_free.set_index("date")["annual_rate"].reindex(strategy.index, method="ffill").mean()
    metrics = performance_metrics(strategy, benchmark_returns, float(risk_free), config["annualization_days"])
    metrics["average_one_way_turnover"] = diagnostics["one_way_turnover"].mean()
    metrics["max_expected_tracking_error"] = diagnostics["expected_te"].max()
    metrics["run_label"] = label
    weights.to_csv(out / "portfolio_weights.csv", index=False)
    diagnostics.to_csv(out / "constraint_diagnostics.csv", index=False)
    ic_history.to_csv(out / "factor_ic.csv")
    pd.concat([strategy, benchmark_returns.rename("benchmark"), equal_weight_daily.reindex(strategy.index)], axis=1).to_csv(out / "daily_returns.csv")
    rolling_tracking_error(strategy, benchmark_returns).rename("rolling_20w_te").to_csv(out / "rolling_tracking_error.csv")
    metrics.rename("value").to_csv(out / "performance_metrics.csv")
