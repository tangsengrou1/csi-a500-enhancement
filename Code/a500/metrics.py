from __future__ import annotations

import numpy as np
import pandas as pd


def performance_metrics(returns: pd.Series, benchmark: pd.Series, risk_free_annual: float = 0.02, periods: int = 252) -> pd.Series:
    aligned = pd.concat([returns.rename("strategy"), benchmark.rename("benchmark")], axis=1).dropna()
    if aligned.empty:
        raise ValueError("没有可用于评价的收益数据")
    r, b = aligned["strategy"], aligned["benchmark"]
    active = r - b
    nav = (1 + r).cumprod()
    drawdown = nav / nav.cummax() - 1
    years = len(r) / periods
    annual_return = nav.iloc[-1] ** (1 / years) - 1 if years > 0 else np.nan
    annual_benchmark = (1 + b).prod() ** (1 / years) - 1 if years > 0 else np.nan
    vol = r.std() * np.sqrt(periods)
    te = active.std() * np.sqrt(periods)
    return pd.Series({
        "cumulative_return": nav.iloc[-1] - 1,
        "annual_return": annual_return,
        "annual_excess_return": annual_return - annual_benchmark,
        "annual_volatility": vol,
        "sharpe": (annual_return - risk_free_annual) / vol if vol > 0 else np.nan,
        "max_drawdown": drawdown.min(),
        "information_ratio": active.mean() * periods / te if te > 0 else np.nan,
        "realized_tracking_error": te,
        "daily_active_win_rate": (active > 0).mean(),
    })


def rolling_tracking_error(returns: pd.Series, benchmark: pd.Series, window_weeks: int = 20) -> pd.Series:
    active_weekly = (returns - benchmark).add(1).resample("W-FRI").prod().sub(1)
    return active_weekly.rolling(window_weeks).std() * np.sqrt(52)

