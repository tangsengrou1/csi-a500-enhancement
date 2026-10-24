# -*- coding: utf-8 -*-
"""50/50融合分数版；原始实现来源及哈希见run_manifest.json。"""
from pathlib import Path
import time

import numpy as np
import pandas as pd
from scipy.optimize import minimize

SOLVER_OPTIONS = {}  # 运行入口按预测源设置；融合使用高精度求解。

# ---------------- 参数 ----------------
N_TOP = 30
COV_DAYS = 40        # 协方差窗口：过去 40 个交易日日收益率
WEEK_DAYS = 5
TAU = 0.05           # BL 主观权重（原文口径）
DELTA = 2.5          # 风险厌恶系数（原文未给出具体值，常见取 2.5，可调）
CAP_MV = 0.1         # MV 组合个股权重上限（原文口径）
EXTREME = 0.2        # |日收益|>0.2 置 0（原文口径）
MAD_K = 3.0          # 中位数去极值倍数（原文未给出具体阈值，可调）
VAAR_Z = 1.645       # 95% VaR 分位数
VAAR_LAMBDA = 0.2    # VaR 惩罚系数（原文口径：夏普 − 0.2×VaR）
BACKTEST_START = "2024-01-02"

from paths import RAW
ROOT = Path(__file__).resolve().parent
DATA_PARQUET = RAW / "processed_data.parquet"
PRED_PARQUET = ROOT / "predictions_fusion.parquet"
OUT_PARQUET = ROOT / "portfolio_weights_v1_fusion.parquet"


def load_close():
    px = pd.read_parquet(DATA_PARQUET, columns=["securityID", "trade_dt", "close"])
    px = px.pivot(index="trade_dt", columns="securityID", values="close").sort_index()
    px.index = pd.to_datetime(px.index)   # trade_dt 在文件里是字符串，必须转成日期
    return px


def process_returns(r):
    """|日收益|>0.2 置 0，再按每只股票 40 日窗口做中位数去极值（MAD 法）。"""
    r = r.copy()
    r[np.abs(r) > EXTREME] = 0.0
    med = np.median(r, axis=0)
    mad = np.median(np.abs(r - med), axis=0)
    mad = np.where(mad == 0, np.median(np.abs(r), axis=0), mad)
    return np.clip(r, med - MAD_K * mad, med + MAD_K * mad)


def bl_posterior(Sig, q, w_eq):
    """He & Litterman (1999)：Π=δΣw_eq，P=I，Ω=τ·diag(PΣPᵀ)。"""
    n = len(q)
    P = np.eye(n)
    Pi = DELTA * Sig @ w_eq
    Om = TAU * np.diag(np.diag(P @ Sig @ P.T))
    M = P @ (TAU * Sig) @ P.T + Om
    return Pi + TAU * Sig @ P.T @ np.linalg.solve(M, q - P @ Pi)


def markowitz(mu, Sig, cap=1.0):
    """max wᵀμ − (δ/2)wᵀΣw  s.t. w≥0, Σw=1, w≤cap。"""
    n = len(mu)
    w0 = np.full(n, 1.0 / n)
    cons = {"type": "eq", "fun": lambda w: w.sum() - 1.0}
    res = minimize(lambda w: -(w @ mu - 0.5 * DELTA * w @ Sig @ w), w0,
                   method="SLSQP", bounds=[(0.0, cap)] * n,
                   constraints=[cons], options={"maxiter": 500, "ftol": 1e-12})
    if not res.success:
        print(f"    [警告] SLSQP 未收敛: {res.message}，用等权替代")
        return np.full(n, 1.0 / n)
    return res.x


def risk_bl(mu, Sig, w0):
    """max 夏普比率 − 0.2×VaR(95%, 周频)  s.t. w≥0, Σw=1, w≤0.1。"""
    n = len(mu)
    def obj(w):
        s2 = w @ Sig @ w
        s = np.sqrt(max(s2, 1e-12))
        return -(w @ mu / s - VAAR_LAMBDA * VAAR_Z * s)
    cons = {"type": "eq", "fun": lambda w: w.sum() - 1.0}
    res = minimize(obj, w0, method="SLSQP", bounds=[(0.0, CAP_MV)] * n,
                   constraints=[cons], options={"maxiter": 500, "ftol": 1e-12})
    if not res.success:
        print(f"    [警告] 风险约束BL SLSQP 未收敛: {res.message}，用等权替代")
        return np.full(n, 1.0 / n)
    return res.x


def main():
    print("加载数据 ...")
    px = load_close()
    stocks = px.columns.tolist()
    close = px.to_numpy()
    px_dates = px.index

    pred = pd.read_parquet(PRED_PARQUET)
    stack_wide = pred.pivot(index="pred_week", columns="securityID", values="stacking")
    stack_wide = stack_wide.reindex(columns=stocks)
    feat_dt = pred.groupby("pred_week")["feature_dt"].first()

    n_days = px.shape[0]
    n_weeks = n_days // WEEK_DAYS + (1 if n_days % WEEK_DAYS else 0)
    start_day = int(px_dates.searchsorted(pd.Timestamp(BACKTEST_START)))
    first_week = start_day // WEEK_DAYS + 1
    weeks = [T for T in range(first_week, n_weeks + 1) if T in stack_wide.index]
    last_week = weeks[-1]
    print(f"回测周: {weeks[0]} ~ {last_week}（共 {len(weeks)} 周，{px_dates[start_day].date()} 起）")

    # 研发期（2020-2023, 第 2~194 周）截面周收益标准差的均值，用于把排名分数映射回预期收益
    dev_week = list(range(2, first_week))
    sigma_cs = np.mean([np.nanstd(close[5 * w - 1] / close[5 * w - 6] - 1) for w in dev_week])
    print(f"研发期截面周收益标准差均值 sigma_cs = {sigma_cs:.4f}")

    t_start = time.time()
    rows = []
    for T in weeks:
        feat = (T - 1) * WEEK_DAYS - 1            # 第 T-1 周最后一天（预测信息截止日）

        s = stack_wide.loc[T].dropna().sort_values(ascending=False)
        top = s.index[:N_TOP].tolist()
        if len(top) < N_TOP:
            print(f"    [警告] 第 {T} 周有效预测不足 {N_TOP} 只，实际 {len(top)} 只")
        q = s.loc[top].to_numpy() * sigma_cs     # 排名分数 -> 预期收益口径（周频）

        ids = [stocks.index(t) for t in top]
        closes = close[feat - COV_DAYS:feat + 1][:, ids]   # (41, m) 过去 40 个交易日
        ret = closes[1:] / closes[:-1] - 1                 # (40, m) 日收益

        r_proc = process_returns(ret)
        Sig_raw = np.cov(ret, rowvar=False) * WEEK_DAYS + np.eye(len(top)) * 1e-10
        Sig_proc = np.cov(r_proc, rowvar=False) * WEEK_DAYS + np.eye(len(top)) * 1e-10

        w_eq = np.full(len(top), 1.0 / len(top))

        mu_bl = bl_posterior(Sig_raw, q, w_eq)
        w_bl = markowitz(mu_bl, Sig_raw, cap=CAP_MV)

        mu_blp = bl_posterior(Sig_proc, q, w_eq)
        w_risk = risk_bl(mu_blp, Sig_proc, w_bl)

        w_mv = markowitz(q, Sig_proc, cap=CAP_MV)

        rows.append(pd.DataFrame({
            "week": T, "feature_dt": feat_dt.loc[T], "securityID": top,
            "bl_w": w_bl, "blrisk_w": w_risk, "mv_w": w_mv, "eq_w": w_eq,
        }))

        if T % 10 == 0 or T == last_week:
            el = time.time() - t_start
            print(f"第 {T}/{last_week} 周完成 | 累计 {el:.0f}s")

    out = pd.concat(rows, ignore_index=True)
    out.to_parquet(OUT_PARQUET, index=False)

    print(f"\n输出: {OUT_PARQUET}  形状: {out.shape}")
    print(f"调仓周数: {out['week'].nunique()}")
    print(f"每期股票数: {out.groupby('week').size().min()} ~ {out.groupby('week').size().max()}")
    print("各组合权重均值（等权应为 1/30 ≈ 0.0333）:",
          {c: round(out[c].mean(), 4) for c in ["bl_w", "blrisk_w", "mv_w", "eq_w"]})


if __name__ == "__main__":
    main()
