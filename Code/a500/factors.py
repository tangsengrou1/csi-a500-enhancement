from __future__ import annotations

import numpy as np
import pandas as pd


FACTOR_COLUMNS = ["value", "quality", "momentum", "low_vol"]


def winsorize(series: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return series
    return series.clip(valid.quantile(lower), valid.quantile(upper))


def industry_zscore(values: pd.Series, industries: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"x": values, "industry": industries})
    frame["x"] = frame.groupby("industry", observed=True)["x"].transform(winsorize)
    mean = frame.groupby("industry", observed=True)["x"].transform("mean")
    std = frame.groupby("industry", observed=True)["x"].transform("std").replace(0, np.nan)
    z = (frame["x"] - mean) / std
    return z.fillna(0.0).clip(-3.0, 3.0)


def latest_asof(df: pd.DataFrame, date_col: str, signal_date: pd.Timestamp, max_age_days: int | None = None) -> pd.DataFrame:
    eligible = df[df[date_col] <= signal_date].sort_values(date_col)
    out = eligible.groupby("wind_code", as_index=False).tail(1)
    if max_age_days is not None:
        out = out[(signal_date - out[date_col]).dt.days <= max_age_days]
    return out


def build_factor_snapshot(signal_date: pd.Timestamp, universe: pd.Index, prices: pd.DataFrame, valuation: pd.DataFrame, fundamentals: pd.DataFrame, industries: pd.Series, config: dict) -> pd.DataFrame:
    px = prices[prices["wind_code"].isin(universe)].pivot(index="date", columns="wind_code", values="adj_close").sort_index()
    returns = px.pct_change(fill_method=None)
    mom_lb, skip, vol_lb = config["momentum_lookback"], config["momentum_skip"], config["volatility_lookback"]
    available = px.loc[:signal_date]
    momentum = available.shift(skip).pct_change(mom_lb - skip, fill_method=None).iloc[-1]
    low_vol = -returns.loc[:signal_date].tail(vol_lb).std() * np.sqrt(config["annualization_days"])

    val = latest_asof(valuation[valuation["wind_code"].isin(universe)], "date", signal_date).set_index("wind_code")
    fun = latest_asof(fundamentals[fundamentals["wind_code"].isin(universe)], "announce_date", signal_date, config["factor_staleness_days"]).set_index("wind_code")
    raw = pd.DataFrame(index=universe)
    raw["value"] = pd.concat([
        1 / val["pe_ttm"].where(val["pe_ttm"] > 0),
        1 / val["pb_lf"].where(val["pb_lf"] > 0),
        1 / val["ps_ttm"].where(val["ps_ttm"] > 0),
        val["dividend_yield"],
    ], axis=1).mean(axis=1)
    raw["quality"] = pd.concat([fun["roe"], fun["gross_margin"], fun["ocf_to_profit"], -fun["debt_to_assets"]], axis=1).rank(pct=True).mean(axis=1)
    raw["momentum"] = momentum
    raw["low_vol"] = low_vol
    for col in FACTOR_COLUMNS:
        raw[col] = industry_zscore(raw[col], industries.reindex(raw.index).fillna("UNKNOWN"))
    raw["coverage"] = raw[FACTOR_COLUMNS].notna().mean(axis=1)
    return raw.fillna(0.0)


def rank_ic(scores: pd.DataFrame, forward_returns: pd.Series) -> pd.Series:
    # Spearman 相关等价于秩变量的 Pearson 相关，避免额外依赖 scipy。
    ranked_returns = forward_returns.rank(method="average")
    def correlation(x: pd.Series) -> float:
        joined = pd.concat([x.rank(method="average"), ranked_returns], axis=1).dropna()
        if len(joined) < 3 or joined.iloc[:, 0].nunique() < 2 or joined.iloc[:, 1].nunique() < 2:
            return np.nan
        return float(np.corrcoef(joined.iloc[:, 0], joined.iloc[:, 1])[0, 1])
    return scores.apply(correlation)


def rolling_factor_weights(ic_history: pd.DataFrame, lookback: int, minimum: int) -> pd.Series:
    hist = ic_history.tail(lookback)
    if len(hist) < minimum:
        return pd.Series(1 / len(FACTOR_COLUMNS), index=FACTOR_COLUMNS)
    mean = hist.mean()
    std = hist.std().replace(0, np.nan)
    icir = (mean / std).clip(lower=0).fillna(0)
    return icir / icir.sum() if icir.sum() > 0 else pd.Series(1 / len(FACTOR_COLUMNS), index=FACTOR_COLUMNS)
