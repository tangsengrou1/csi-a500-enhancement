# -*- coding: utf-8 -*-
"""50/50融合分数版；原始实现来源及哈希见run_manifest.json。"""
from pathlib import Path
import time

import numpy as np
import pandas as pd
import cvxpy as cp
from portfolio_basic import load_close, process_returns, bl_posterior

SOLVER_OPTIONS = {}  # 运行入口按预测源设置；融合使用高精度求解。

# ---------------- 参数 ----------------
N_TOP = 30
SMOOTH_K = 4         # 选股信号平滑窗口（与 v2 一致）
COV_DAYS = 40        # 协方差窗口：过去 40 个交易日日收益率
WEEK_DAYS = 5
DELTA = 2.5          # 风险厌恶系数（锁定设计）
TAU = 0.05           # BL 观点不确定性系数（锁定设计）
CAP_BL = 0.1         # BL+约束组合个股权重上限（与 MV+约束组合一致）
LAMBDA_IND = 0.5     # 行业中性软约束惩罚系数（与 v2 一致）
LAMBDA_TURN = 0.002  # 换手惩罚系数（与 v2 一致）
INDCON_START = "2024-09-23"   # 行业数据起始日，此前不加行业惩罚
BACKTEST_START = "2024-01-02"

from paths import RAW
ROOT = Path(__file__).resolve().parent
DATA_PARQUET = RAW / "processed_data.parquet"
IND_PARQUET = RAW / "a500_constituents_sw2021l1.parquet"
PRED_PARQUET = ROOT / "predictions_fusion.parquet"
OUT_PARQUET = ROOT / "portfolio_weights_v3_fusion.parquet"
OUT_INDDEV = ROOT / "industry_deviation_v3_fusion.parquet"




def load_industry():
    """返回 (bench, tick_ind)：
    bench: 日期 × 31 申万一级行业的基准权重（每期加总=1）
    tick_ind: 日期 × 股票代码的行业映射（沿时间向前填充）"""
    ind = pd.read_parquet(IND_PARQUET)
    ind = ind.rename(columns={"DATE": "trade_dt", "TICKER": "securityID",
                              "WEIGHT": "w", "SW2021_L1": "industry"})
    ind["trade_dt"] = pd.to_datetime(ind["trade_dt"]).dt.normalize()
    ind = ind[ind["industry"].notna()].copy()
    ind["w"] = ind["w"] / 100.0
    bench = ind.groupby(["trade_dt", "industry"])["w"].sum().unstack(fill_value=0.0)
    bench = bench.div(bench.sum(axis=1), axis=0)
    tick_ind = ind.pivot_table(index="trade_dt", columns="securityID",
                               values="industry", aggfunc="first").sort_index().ffill().bfill()
    return bench, tick_ind




def solve_week(alpha, Sig, H=None, b=None, w_prev=None):
    """max αᵀw − (δ/2)wᵀΣw − λ_ind‖Hᵀw−b‖² − λ_turn‖w−w_prev‖₁  s.t. w≥0, Σw=1, w≤0.1。"""
    n = len(alpha)
    w = cp.Variable(n)
    pen = LAMBDA_IND * cp.sum_squares(H.T @ w - b) if H is not None else 0.0
    if w_prev is not None:
        pen = pen + LAMBDA_TURN * cp.norm1(w - w_prev)
    obj = cp.Maximize(alpha @ w - 0.5 * DELTA * cp.quad_form(w, Sig) - pen)
    cons = [cp.sum(w) == 1, w >= 0, w <= CAP_BL]
    prob = cp.Problem(obj, cons)
    prob.solve(solver=cp.OSQP, **SOLVER_OPTIONS)
    if prob.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
        print(f"    [警告] OSQP 状态 {prob.status}，用等权替代")
        return np.full(n, 1.0 / n)
    return w.value


def main():
    print("加载数据 ...")
    px = load_close()
    stocks = px.columns.tolist()
    close = px.to_numpy()
    px_dates = px.index
    bench, tick_ind = load_industry()

    pred = pd.read_parquet(PRED_PARQUET)
    stack_wide = pred.pivot(index="pred_week", columns="securityID", values="stacking")
    stack_wide = stack_wide.reindex(columns=stocks)
    smooth = stack_wide.rolling(SMOOTH_K, min_periods=1).mean()   # 平滑选股信号（无前视）
    feat_dt = pred.groupby("pred_week")["feature_dt"].first()

    n_days = px.shape[0]
    n_weeks = n_days // WEEK_DAYS + (1 if n_days % WEEK_DAYS else 0)
    start_day = int(px_dates.searchsorted(pd.Timestamp(BACKTEST_START)))
    first_week = start_day // WEEK_DAYS + 1
    weeks = [T for T in range(first_week, n_weeks + 1) if T in smooth.index]
    last_week = weeks[-1]
    print(f"回测周: {weeks[0]} ~ {last_week}（共 {len(weeks)} 周，{px_dates[start_day].date()} 起）")

    dev_week = list(range(2, first_week))
    sigma_cs = np.mean([np.nanstd(close[5 * w - 1] / close[5 * w - 6] - 1) for w in dev_week])
    print(f"研发期截面周收益标准差均值 sigma_cs = {sigma_cs:.4f}")

    t_start = time.time()
    rows, dev_rows = [], []
    n_indcon, n_dropped = 0, 0
    prev_top, prev_w = None, None
    for T in weeks:
        feat = (T - 1) * WEEK_DAYS - 1            # 第 T-1 周最后一天（预测信息截止日）
        reb_dt = px_dates[feat]

        s = smooth.loc[T].dropna().sort_values(ascending=False)
        top = s.index[:N_TOP].tolist()
        if len(top) < N_TOP:
            print(f"    [警告] 第 {T} 周有效预测不足 {N_TOP} 只，实际 {len(top)} 只")
        q = s.loc[top].to_numpy() * sigma_cs     # 观点：平滑分数 -> 预期收益口径（周频）

        ids = [stocks.index(t) for t in top]
        closes = close[feat - COV_DAYS:feat + 1][:, ids]   # (41, m) 过去 40 个交易日
        ret = closes[1:] / closes[:-1] - 1                 # (40, m) 日收益（未处理，锁定 BL 口径）

        # 行业中性：取调仓日（含）之前最近一期的行业快照，仅 2024-09-23 起生效
        pos = bench.index.searchsorted(reb_dt, side="right") - 1
        active = pos >= 0 and bench.index[pos] >= pd.Timestamp(INDCON_START)
        H, b = None, None
        if active:
            ind_map = tick_ind.iloc[pos]
            ind_lab = [ind_map.get(t, None) for t in top]
            valid = [x is not None and pd.notna(x) for x in ind_lab]
            if not all(valid):
                print(f"    [警告] 第 {T} 周 {sum(not v for v in valid)} 只无行业信息，剔除")
                n_dropped += sum(not v for v in valid)
                top = [t for t, v in zip(top, valid) if v]
                q = q[np.array(valid)]
                ret = ret[:, np.array(valid)]
                ind_lab = [x for x, v in zip(ind_lab, valid) if v]
            if top:
                b = bench.iloc[pos].to_numpy()
                onehot = pd.get_dummies(pd.Series(ind_lab)).reindex(columns=bench.columns, fill_value=0)
                H = onehot.to_numpy(dtype=float)

        Sig = np.cov(ret, rowvar=False) * WEEK_DAYS + np.eye(len(top)) * 1e-8   # 未处理日收益

        # 换手惩罚的 w_prev：上周权重按持有期（feat-5 → feat）漂移后对齐到本期候选池
        w_prev = None
        if prev_top is not None:
            prev_ids = np.array([stocks.index(t) for t in prev_top])
            r_held_i = close[feat, prev_ids] / close[feat - WEEK_DAYS, prev_ids] - 1.0
            r_held_port = float(prev_w @ r_held_i)
            wmap = dict(zip(prev_top, prev_w * (1.0 + r_held_i) / (1.0 + r_held_port)))
            w_prev = np.array([wmap.get(t, 0.0) for t in top])

        w_eq = np.full(len(top), 1.0 / len(top))
        mu_post = bl_posterior(Sig, q, w_eq)          # BL 后验收益
        w_opt = solve_week(mu_post, Sig, H, b, w_prev)
        prev_top, prev_w = top, w_opt

        rows.append(pd.DataFrame({
            "week": T, "feature_dt": feat_dt.loc[T], "securityID": top,
            "blc_w": w_opt, "indcon": int(active),
        }))
        if active and H is not None:
            n_indcon += 1
            port_w = H.T @ w_opt
            dev_rows.append(pd.DataFrame({
                "week": T, "industry": bench.columns,
                "port_w": port_w, "bench_w": b, "dev": port_w - b,
            }))

        if T % 10 == 0 or T == last_week:
            el = time.time() - t_start
            print(f"第 {T}/{last_week} 周完成 | 累计 {el:.0f}s")

    out = pd.concat(rows, ignore_index=True)
    out.to_parquet(OUT_PARQUET, index=False)
    print(f"\n输出: {OUT_PARQUET}  形状: {out.shape}")

    if dev_rows:
        dev = pd.concat(dev_rows, ignore_index=True)
        dev.to_parquet(OUT_INDDEV, index=False)
        print(f"输出: {OUT_INDDEV}  形状: {dev.shape}")
        print(f"行业约束生效周数: {n_indcon} / {out['week'].nunique()}，剔除无行业信息个股 {n_dropped} 次")
        print(f"生效周平均 |行业偏离| = {dev['dev'].abs().mean():.4f}，最大 |偏离| = {dev['dev'].abs().max():.4f}")
    else:
        print("无行业约束生效周（检查 INDCON_START 与数据日期范围）")


if __name__ == "__main__":
    main()
