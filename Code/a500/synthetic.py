from __future__ import annotations

import numpy as np
import pandas as pd

from .io import DataBundle


def make_synthetic_bundle(seed: int = 7, n_assets: int = 60, n_days: int = 430) -> DataBundle:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_days)
    codes = [f"{i:06d}.SZ" for i in range(1, n_assets + 1)]
    industries = np.array([f"行业{i % 8 + 1}" for i in range(n_assets)])
    market = rng.normal(0.00025, 0.009, n_days)
    loadings = rng.uniform(0.7, 1.2, n_assets)
    residual = rng.normal(0, 0.012, (n_days, n_assets))
    returns = market[:, None] * loadings + residual
    adj = 100 * np.cumprod(1 + returns, axis=0)
    prices = pd.DataFrame({
        "date": np.repeat(dates, n_assets), "wind_code": np.tile(codes, n_days),
        "close": adj.ravel(), "adj_close": adj.ravel(), "amount": rng.uniform(1e8, 2e9, n_days * n_assets),
        "trade_status": "交易", "limit_status": "正常", "listing_date": pd.Timestamp("2020-01-01")
    })
    rebalance = dates.to_series().groupby(dates.to_period("W-FRI")).max().to_numpy()
    raw_w = rng.uniform(0.5, 1.5, n_assets); raw_w /= raw_w.sum()
    constituents = pd.DataFrame({"date": np.repeat(rebalance, n_assets), "wind_code": np.tile(codes, len(rebalance)), "weight": np.tile(raw_w, len(rebalance))})
    industry = pd.DataFrame({"effective_date": np.repeat(rebalance, n_assets), "wind_code": np.tile(codes, len(rebalance)), "industry": np.tile(industries, len(rebalance))})
    valuation = pd.DataFrame({"date": np.repeat(rebalance, n_assets), "wind_code": np.tile(codes, len(rebalance)), "pe_ttm": rng.uniform(8, 45, len(rebalance)*n_assets), "pb_lf": rng.uniform(0.8, 8, len(rebalance)*n_assets), "ps_ttm": rng.uniform(0.5, 10, len(rebalance)*n_assets), "dividend_yield": rng.uniform(0, 0.05, len(rebalance)*n_assets)})
    quarters = pd.date_range("2023-12-31", dates[-1], freq="QE")
    fundamentals = pd.DataFrame({"announce_date": np.repeat(quarters + pd.Timedelta(days=35), n_assets), "report_period": np.repeat(quarters, n_assets), "wind_code": np.tile(codes, len(quarters)), "roe": rng.normal(0.10, 0.05, len(quarters)*n_assets), "gross_margin": rng.uniform(0.1, 0.6, len(quarters)*n_assets), "ocf_to_profit": rng.uniform(0.3, 1.8, len(quarters)*n_assets), "debt_to_assets": rng.uniform(0.1, 0.8, len(quarters)*n_assets)})
    bench_ret = returns @ raw_w
    benchmark = pd.DataFrame({"date": dates, "price_close": 1000*np.cumprod(1+bench_ret), "total_return_close": 1000*np.cumprod(1+bench_ret+0.00005)})
    risk_free = pd.DataFrame({"date": dates, "annual_rate": 0.018})
    return DataBundle(prices, benchmark, constituents, industry, valuation, fundamentals, risk_free)

