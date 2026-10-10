from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .factor_registry import FactorDefinition, FactorRegistry, MarketPanel


MARKET_ALIASES = {
    "securityID": "wind_code",
    "securityid": "wind_code",
    "trade_dt": "date",
    "tradetime": "date",
    "volume": "volume",
    "vol": "volume",
    "amt": "amount",
    "turn": "turnover",
}


@dataclass
class FactorEvaluationResult:
    summary: pd.DataFrame
    weekly_returns: pd.DataFrame
    pnl_curves: pd.DataFrame
    turnover: pd.DataFrame
    weights: pd.DataFrame
    diagnostics: pd.DataFrame

    def save(self, output_dir: str | Path) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        self.summary.to_csv(out / "factor_summary.csv", index=False)
        self.weekly_returns.to_csv(out / "factor_weekly_returns.csv", index=False)
        self.pnl_curves.to_csv(out / "factor_pnl_curves.csv", index=False)
        self.turnover.to_csv(out / "factor_turnover.csv", index=False)
        self.weights.to_csv(out / "factor_weights.csv", index=False)
        self.diagnostics.to_csv(out / "factor_diagnostics.csv", index=False)


def standardize_market_data(market: pd.DataFrame) -> pd.DataFrame:
    out = market.rename(columns={c: MARKET_ALIASES.get(c, c) for c in market.columns}).copy()
    required = {"date", "wind_code", "close"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(f"行情数据缺少字段: {sorted(missing)}")
    out["date"] = pd.to_datetime(out["date"], errors="raise").dt.normalize()
    if out.duplicated(["date", "wind_code"]).any():
        raise ValueError("行情数据存在重复的 date + wind_code")
    out = out.sort_values(["date", "wind_code"]).reset_index(drop=True)
    return out


def build_market_panel(market: pd.DataFrame, price_field: str = "close") -> MarketPanel:
    market = standardize_market_data(market)
    if price_field not in market:
        raise ValueError(f"行情数据缺少价格字段: {price_field}")

    def pivot(field: str) -> pd.DataFrame | None:
        if field not in market:
            return None
        return market.pivot(index="date", columns="wind_code", values=field).sort_index()

    return MarketPanel(
        close=pivot(price_field),
        open=pivot("open"),
        high=pivot("high"),
        low=pivot("low"),
        volume=pivot("volume"),
        amount=pivot("amount"),
        vwap=pivot("vwap"),
        turnover=pivot("turnover"),
    )


def latest_universe_snapshot(constituents: pd.DataFrame, signal_date: pd.Timestamp) -> pd.Index:
    date_col = "date" if "date" in constituents else "effective_date"
    code_col = "wind_code" if "wind_code" in constituents else "securityID"
    eligible_dates = constituents.loc[constituents[date_col] <= signal_date, date_col]
    if eligible_dates.empty:
        return pd.Index([], dtype=object)
    snapshot = constituents[constituents[date_col] == eligible_dates.max()]
    if "is_member" in snapshot:
        snapshot = snapshot[snapshot["is_member"].astype(bool)]
    return pd.Index(snapshot[code_col].dropna().astype(str).unique())


def preprocess_scores(values: pd.Series, direction: int, lower: float, upper: float) -> pd.Series:
    scores = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if scores.empty:
        return scores
    lo, hi = scores.quantile([lower, upper])
    scores = scores.clip(lo, hi) * direction
    return scores


def scores_to_weights(scores: pd.Series, config: dict) -> pd.Series:
    mode = config.get("position_mapping", "top_quantile_equal_weight")
    minimum = int(config.get("minimum_stocks", 10))
    if len(scores) < minimum or scores.nunique() < 2:
        return pd.Series(dtype=float)
    ranks = scores.rank(method="average", pct=True)
    if mode == "top_quantile_equal_weight":
        top_fraction = float(config.get("top_fraction", 0.20))
        selected = ranks[ranks > 1 - top_fraction].index
        if len(selected) < 1:
            return pd.Series(dtype=float)
        return pd.Series(1.0 / len(selected), index=selected)
    if mode == "rank_weighted_long_only":
        exponent = float(config.get("rank_exponent", 1.0))
        raw = ranks.pow(exponent)
        return raw / raw.sum()
    raise ValueError(f"不支持的仓位映射: {mode}")


def one_way_turnover(current: pd.Series, previous: pd.Series) -> float:
    if previous.empty:
        return 1.0 if not current.empty else 0.0
    union = current.index.union(previous.index)
    return float(0.5 * (current.reindex(union, fill_value=0) - previous.reindex(union, fill_value=0)).abs().sum())


def factor_performance_metrics(weekly_returns: pd.Series, turnover: pd.Series, risk_free_annual: float = 0.0) -> dict:
    returns = weekly_returns.dropna()
    if returns.empty:
        return {
            "periods": 0, "cumulative_return": np.nan, "annual_return": np.nan,
            "annual_volatility": np.nan, "max_drawdown": np.nan,
            "sharpe": np.nan, "average_one_way_turnover": np.nan,
        }
    nav = (1 + returns).cumprod()
    drawdown = nav / nav.cummax() - 1
    annual_return = nav.iloc[-1] ** (52 / len(returns)) - 1
    annual_volatility = returns.std(ddof=1) * np.sqrt(52)
    weekly_rf = (1 + risk_free_annual) ** (1 / 52) - 1
    sharpe = (returns.mean() - weekly_rf) / returns.std(ddof=1) * np.sqrt(52) if returns.std(ddof=1) > 0 else np.nan
    return {
        "periods": len(returns),
        "cumulative_return": nav.iloc[-1] - 1,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "max_drawdown": drawdown.min(),
        "sharpe": sharpe,
        "average_one_way_turnover": turnover.reindex(returns.index).mean(),
    }


def _validate_factor_output(values: pd.DataFrame, panel: MarketPanel, definition: FactorDefinition) -> pd.DataFrame:
    if not isinstance(values, pd.DataFrame):
        raise TypeError(f"{definition.factor_id} 必须返回日期×股票的 DataFrame")
    out = values.copy()
    out.index = pd.to_datetime(out.index, errors="raise").normalize()
    out = out.sort_index().reindex(index=panel.close.index, columns=panel.close.columns)
    return out


def evaluate_factors(
    market: pd.DataFrame,
    constituents: pd.DataFrame | None,
    registry: FactorRegistry,
    factor_ids: Iterable[str],
    config: dict,
) -> FactorEvaluationResult:
    market = standardize_market_data(market)
    if config.get("drop_weekends", True):
        market = market[market["date"].dt.dayofweek < 5].copy()
    panel = build_market_panel(market, config.get("price_field", "close"))
    dates = panel.close.index
    weekly_signals = dates.to_series().groupby(dates.to_period(config.get("rebalance_frequency", "W-FRI"))).max()
    weekly_signals = pd.DatetimeIndex(weekly_signals)
    date_positions = pd.Series(np.arange(len(dates)), index=dates)

    if constituents is not None:
        constituents = constituents.copy()
        date_col = "date" if "date" in constituents else "effective_date"
        constituents[date_col] = pd.to_datetime(constituents[date_col], errors="raise").dt.normalize()
    elif not config.get("allow_development_universe", False):
        raise ValueError("未提供历史成分股；正式评价不得自动使用固定股票池")

    summary_rows: list[dict] = []
    return_rows: list[dict] = []
    pnl_rows: list[dict] = []
    turnover_rows: list[dict] = []
    weight_rows: list[dict] = []
    diagnostic_rows: list[dict] = []

    for factor_id in factor_ids:
        definition = registry.get(factor_id)
        for field in definition.required_fields:
            panel.field(field)
        factor_matrix = _validate_factor_output(definition.calculator(panel), panel, definition)
        previous = pd.Series(dtype=float)
        factor_returns: dict[pd.Timestamp, float] = {}
        factor_turnover: dict[pd.Timestamp, float] = {}

        for i, signal_date in enumerate(weekly_signals[:-1]):
            signal_pos = int(date_positions[signal_date])
            if signal_pos + 1 >= len(dates):
                continue
            execution_date = dates[signal_pos + 1]
            next_signal = weekly_signals[i + 1]
            next_signal_pos = int(date_positions[next_signal])
            if next_signal_pos + 1 >= len(dates):
                continue
            exit_date = dates[next_signal_pos + 1]

            if constituents is None:
                universe = panel.close.loc[signal_date].dropna().index
                universe_label = "DEVELOPMENT_AVAILABLE_STOCKS"
            else:
                universe = latest_universe_snapshot(constituents, signal_date)
                universe_label = "HISTORICAL_CONSTITUENTS"
            universe = universe.intersection(panel.close.columns)
            raw_scores = factor_matrix.loc[signal_date].reindex(universe)
            scores = preprocess_scores(
                raw_scores, definition.direction,
                float(config.get("winsorize_lower", 0.01)),
                float(config.get("winsorize_upper", 0.99)),
            )
            entry_prices = panel.close.loc[execution_date].reindex(scores.index)
            exit_prices = panel.close.loc[exit_date].reindex(scores.index)
            valid = entry_prices.gt(0) & exit_prices.gt(0)
            scores = scores[valid]
            coverage = float(scores.notna().sum() / len(universe)) if len(universe) else 0.0
            weights = scores_to_weights(scores, config)
            if weights.empty:
                diagnostic_rows.append({
                    "factor_id": factor_id, "signal_date": signal_date,
                    "status": "SKIP_INSUFFICIENT_SCORES", "universe_size": len(universe),
                    "valid_scores": len(scores), "coverage": coverage,
                    "universe_type": universe_label,
                })
                continue

            stock_returns = exit_prices.reindex(weights.index) / entry_prices.reindex(weights.index) - 1
            gross_return = float((weights * stock_returns).sum())
            turnover = one_way_turnover(weights, previous)
            cost = turnover * float(config.get("transaction_cost_bps", 0)) / 10000
            net_return = gross_return - cost
            factor_returns[execution_date] = net_return
            factor_turnover[execution_date] = turnover
            for code, weight in weights.items():
                weight_rows.append({
                    "factor_id": factor_id, "signal_date": signal_date,
                    "execution_date": execution_date, "exit_date": exit_date,
                    "wind_code": code, "factor_value": float(raw_scores.get(code, np.nan)),
                    "processed_score": float(scores[code]), "weight": float(weight),
                })
            diagnostic_rows.append({
                "factor_id": factor_id, "signal_date": signal_date,
                "execution_date": execution_date, "exit_date": exit_date,
                "status": "OK", "universe_size": len(universe),
                "valid_scores": len(scores), "selected_stocks": len(weights),
                "coverage": coverage, "gross_return": gross_return,
                "transaction_cost": cost, "net_return": net_return,
                "one_way_turnover": turnover, "universe_type": universe_label,
            })
            previous = weights

        returns = pd.Series(factor_returns, dtype=float).sort_index()
        turnovers = pd.Series(factor_turnover, dtype=float).sort_index()
        metrics = factor_performance_metrics(returns, turnovers, float(config.get("risk_free_annual", 0.0)))
        summary_rows.append({
            "factor_id": factor_id, "library": definition.library,
            "category": definition.category, "direction": definition.direction,
            **metrics,
        })
        nav = (1 + returns).cumprod()
        return_rows.extend({"date": d, "factor_id": factor_id, "weekly_return": v} for d, v in returns.items())
        pnl_rows.extend({"date": d, "factor_id": factor_id, "pnl_curve": v} for d, v in nav.items())
        turnover_rows.extend({"date": d, "factor_id": factor_id, "one_way_turnover": v} for d, v in turnovers.items())

    return FactorEvaluationResult(
        summary=pd.DataFrame(summary_rows),
        weekly_returns=pd.DataFrame(return_rows),
        pnl_curves=pd.DataFrame(pnl_rows),
        turnover=pd.DataFrame(turnover_rows),
        weights=pd.DataFrame(weight_rows),
        diagnostics=pd.DataFrame(diagnostic_rows),
    )
