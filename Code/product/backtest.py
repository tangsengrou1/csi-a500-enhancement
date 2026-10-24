# -*- coding: utf-8 -*-
"""50/50融合分数版；原始实现来源及哈希见run_manifest.json。"""
from pathlib import Path

import numpy as np
import pandas as pd

WEEK_DAYS = 5
RF = 0.0          # 年化无风险利率（夏普计算用）
PASSIVE_W = 0.8   # 产品被动部分比例
TRADE_COST = 0.0015   # 单边交易成本（打包：佣金+印花税+冲击成本），按每周单边换手收取
MGMT_FEE = 0.005      # 年化管理费（指增产品口径，对全部产品净值收取）
FEE_W = (1.0 + MGMT_FEE) ** (1.0 / 52.0) - 1.0   # 周化管理费
PLOT = True       # 是否输出图片

from paths import RAW
ROOT = Path(__file__).resolve().parent
DATA_PARQUET = RAW / "processed_data.parquet"
IDX_DIR = RAW
IDX_TR_FILE = IDX_DIR / "中证A500全收益指数.xlsx"
IDX_PX_FILE = IDX_DIR / "中证A500价格指数每日收盘价.xlsx"
WEIGHTS_PARQUET = ROOT / "portfolio_weights_v1_fusion.parquet"
WEIGHTS_V2_PARQUET = ROOT / "portfolio_weights_v2_fusion.parquet"
WEIGHTS_V3_PARQUET = ROOT / "portfolio_weights_v3_fusion.parquet"

ACTIVE = ["bl", "blrisk", "mv", "eq", "ind", "blc"]
LABEL = {"bl": "BL组合", "blrisk": "风险约束BL", "mv": "MV组合", "eq": "等权组合",
         "ind": "MV+约束组合", "blc": "BL+约束组合"}
COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
MET_COLS = ["累计收益", "年化收益", "年化波动", "最大回撤", "夏普比率",
            "累计超额", "年化超额", "跟踪误差(年化)", "信息比率", "周胜率", "年化换手(单边)"]


def load_prices():
    px = pd.read_parquet(DATA_PARQUET, columns=["securityID", "trade_dt", "close"])
    px = px.pivot(index="trade_dt", columns="securityID", values="close").sort_index()
    px.index = pd.to_datetime(px.index).normalize()
    return px


def load_index(path):
    df = pd.read_excel(path)
    s = pd.to_datetime(df.iloc[:, 0], errors="coerce").dt.normalize()   # Wind 导出带秒数，归一到当天
    v = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    out = pd.Series(v.to_numpy(), index=s).sort_index()
    out = out[out.index.notna() & out.notna()]
    return out[~out.index.duplicated(keep="last")]


def metrics(r):
    n = len(r)
    total = np.prod(1.0 + r) - 1.0
    ann = (1.0 + total) ** (52.0 / n) - 1.0
    vol = r.std() * np.sqrt(52.0)
    sharpe = (r.mean() - RF / 52.0) / r.std() * np.sqrt(52.0)
    nav = np.cumprod(1.0 + r)
    mdd = (nav / np.maximum.accumulate(nav) - 1.0).min()
    return total, ann, vol, mdd, sharpe


def excess_metrics(rp, rb):
    n = len(rp)
    ratio = np.prod(1.0 + rp) / np.prod(1.0 + rb) - 1.0
    ex_ann = (1.0 + ratio) ** (52.0 / n) - 1.0
    ex = rp - rb
    te = ex.std() * np.sqrt(52.0)
    ir = ex.mean() * 52.0 / te if te > 0 else np.nan
    win = (ex > 0).mean()
    return ratio, ex_ann, te, ir, win


def main():
    print("加载数据 ...")
    px = load_prices()
    stocks = px.columns.tolist()
    close = px.to_numpy()
    dates = px.index

    w = pd.read_parquet(WEIGHTS_PARQUET)
    w2 = pd.read_parquet(WEIGHTS_V2_PARQUET)
    w3 = pd.read_parquet(WEIGHTS_V3_PARQUET)
    weeks = sorted(set(w["week"].unique()) | set(w2["week"].unique()) | set(w3["week"].unique()))
    missing = (set(w["securityID"]) | set(w2["securityID"]) | set(w3["securityID"])) - set(stocks)
    if missing:
        print(f"    [警告] 权重文件里有 {len(missing)} 只股票不在价格表里: {sorted(missing)[:5]}")

    idx_tr_raw = load_index(IDX_TR_FILE)
    idx_px_raw = load_index(IDX_PX_FILE)
    last_idx_pos = int(dates.searchsorted(max(idx_tr_raw.index.max(), idx_px_raw.index.max())))
    if last_idx_pos < len(dates) - 1:
        print(f"    [提示] 指数数据止于 {dates[last_idx_pos].date()}，个股多出的 {dates[last_idx_pos + 1].date()} 不参与回测")

    def align(s):
        a = s.reindex(dates)
        nm = a.isna().sum()
        if nm:
            print(f"    [警告] 指数缺 {nm} 个交易日，向前填充")
            a = a.ffill()
        return a.to_numpy()

    idx_tr = align(idx_tr_raw)
    idx_px = align(idx_px_raw)

    first_day = (weeks[0] - 1) * WEEK_DAYS - 1
    last_day = min(len(dates) - 1, weeks[-1] * WEEK_DAYS - 1, last_idx_pos)
    print(f"回测周数: {len(weeks)}（第 {weeks[0]} ~ {weeks[-1]} 周）")
    print(f"回测区间: {dates[first_day].date()} ~ {dates[last_day].date()}")

    # 每个组合一份权重表：列 week, securityID, {k}_w
    wdict = {k: w for k in ACTIVE[:4]}
    wdict["ind"] = w2
    wdict["blc"] = w3

    rows = []
    for T in weeks:
        prev = (T - 1) * WEEK_DAYS - 1
        end = min(len(dates) - 1, T * WEEK_DAYS - 1, last_idx_pos)
        r_i = close[end] / close[prev] - 1.0
        row = {"week": T, "w_date": dates[prev], "end_date": dates[end]}
        for k in ACTIVE:
            g = wdict[k][wdict[k]["week"] == T].set_index("securityID")
            if len(g):
                ids = [stocks.index(s) for s in g.index]
                row[f"r_{k}"] = float((g[f"{k}_w"].to_numpy() * r_i[ids]).sum())
                row[f"{k}_con"] = int(g["indcon"].iloc[0]) if "indcon" in g.columns else np.nan
            else:
                row[f"r_{k}"] = np.nan
                row[f"{k}_con"] = np.nan
        row["r_idx"] = float(idx_tr[end] / idx_tr[prev] - 1.0)
        row["r_idx_price"] = float(idx_px[end] / idx_px[prev] - 1.0)
        for k in ACTIVE:
            row[f"r_prod_{k}"] = PASSIVE_W * row["r_idx"] + (1.0 - PASSIVE_W) * row[f"r_{k}"]
        rows.append(row)
    rdf = pd.DataFrame(rows)

    # 换手率（单边）：调仓时 |w_{T+1} - w_T 按持有期漂移后| 的一半，即只算买入侧；
    # turn_series[k][i] = 第 i 周初调仓产生的单边换手（首周建仓也计一次），供扣交易成本用
    turn = {}
    turn_series = {k: np.zeros(len(rdf)) for k in ACTIVE}
    for k in ACTIVE:
        wk = wdict[k]
        tw = 0.0
        cnt = 0
        g0 = wk[wk["week"] == rdf["week"].iloc[0]].set_index("securityID")[f"{k}_w"]
        if len(g0) and np.isfinite(rdf[f"r_{k}"].iloc[0]):
            turn_series[k][0] = 0.5 * float(g0.abs().sum())
        for i in range(len(rdf) - 1):
            T, Tn = rdf["week"].iloc[i], rdf["week"].iloc[i + 1]
            g1 = wk[wk["week"] == T].set_index("securityID")[f"{k}_w"]
            g2 = wk[wk["week"] == Tn].set_index("securityID")[f"{k}_w"]
            if g1.empty or g2.empty or not np.isfinite(rdf[f"r_{k}"].iloc[i]):
                continue
            univ = g1.index.union(g2.index)
            w1 = g1.reindex(univ).fillna(0.0).to_numpy()
            w2v = g2.reindex(univ).fillna(0.0).to_numpy()
            prev = (T - 1) * WEEK_DAYS - 1
            end = min(len(dates) - 1, T * WEEK_DAYS - 1)
            ids = [stocks.index(s) for s in univ]
            r_i = close[end] / close[prev] - 1.0
            w1h = w1 * (1.0 + r_i[ids]) / (1.0 + rdf[f"r_{k}"].iloc[i])
            t = 0.5 * np.abs(w2v - w1h).sum()
            tw += t
            cnt += 1
            turn_series[k][i + 1] = t
        turn[k] = tw * 52.0 / cnt if cnt else np.nan
    for k in ACTIVE:
        rdf[f"turn_{k}"] = turn_series[k]
        rdf[f"r_net_{k}"] = rdf[f"r_{k}"] - TRADE_COST * rdf[f"turn_{k}"]
        rdf[f"r_prod_net_{k}"] = PASSIVE_W * rdf["r_idx"] + (1.0 - PASSIVE_W) * rdf[f"r_net_{k}"] - FEE_W
    rdf.to_csv(ROOT / "backtest_weekly_fusion.csv", index=False, encoding="utf-8-sig")

    # 业绩指标表
    r_idx = rdf["r_idx"].to_numpy()
    met_rows = []
    idx_m = metrics(r_idx)
    met_rows.append(["中证A500全收益指数", *idx_m, 0.0, 0.0, 0.0, np.nan, np.nan, np.nan])
    for k in ACTIVE:
        r_k = rdf[f"r_net_{k}"].to_numpy()
        m = metrics(r_k)
        em = excess_metrics(r_k, r_idx)
        met_rows.append([f"主动-{LABEL[k]}", *m, *em, turn[k]])
    for k in ACTIVE:
        r_k = rdf[f"r_prod_net_{k}"].to_numpy()
        m = metrics(r_k)
        em = excess_metrics(r_k, r_idx)
        met_rows.append([f"指增产品-{LABEL[k]}", *m, *em, 0.2 * turn[k]])

    met = pd.DataFrame(met_rows, columns=["组合"] + MET_COLS)
    met.to_csv(ROOT / "backtest_metrics_fusion.csv", index=False, encoding="utf-8-sig")
    print("\n业绩指标表:")
    print(met.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    # 净值曲线数据
    nav = pd.DataFrame({"date": rdf["end_date"]})
    nav["nav_idx"] = np.cumprod(1.0 + r_idx)
    nav["nav_idx_price"] = np.cumprod(1.0 + rdf["r_idx_price"].to_numpy())
    for k in ACTIVE:
        nav[f"nav_{k}"] = np.cumprod(1.0 + rdf[f"r_{k}"].to_numpy())
        nav[f"nav_prod_{k}"] = np.cumprod(1.0 + rdf[f"r_prod_{k}"].to_numpy())
        nav[f"nav_net_{k}"] = np.cumprod(1.0 + rdf[f"r_net_{k}"].to_numpy())
        nav[f"nav_prod_net_{k}"] = np.cumprod(1.0 + rdf[f"r_prod_net_{k}"].to_numpy())
    nav.to_csv(ROOT / "backtest_nav_fusion.csv", index=False, encoding="utf-8-sig")

    if PLOT:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False

        def nav_plot(prefix, title, outname):
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.plot(nav["date"], nav["nav_idx"], color="black", lw=2, label="中证A500全收益")
            for k, c in zip(ACTIVE, COLORS):
                col = f"nav_net_{k}" if prefix == "active" else f"nav_prod_net_{k}"
                lab = LABEL[k] if prefix == "active" else f"指增产品-{LABEL[k]}"
                ax.plot(nav["date"], nav[col], color=c, lw=1.2, label=lab)
            ax.set_title(title)
            ax.legend(); ax.grid(alpha=0.3)
            fig.tight_layout(); fig.savefig(ROOT / outname, dpi=150)
            plt.close(fig)

        def excess_plot(prefix, title, outname):
            fig, ax = plt.subplots(figsize=(10, 5))
            for k, c in zip(ACTIVE, COLORS):
                col = f"r_net_{k}" if prefix == "active" else f"r_prod_net_{k}"
                lab = LABEL[k] if prefix == "active" else f"指增产品-{LABEL[k]}"
                ex = np.cumprod(1.0 + rdf[col].to_numpy()) / np.cumprod(1.0 + r_idx) - 1.0
                ax.plot(nav["date"], ex, color=c, lw=1.2, label=lab)
            ax.axhline(0, color="black", lw=0.8)
            ax.set_title(title)
            ax.legend(); ax.grid(alpha=0.3)
            fig.tight_layout(); fig.savefig(ROOT / outname, dpi=150)
            plt.close(fig)

        nav_plot("active", "组合净值曲线（已扣交易成本 0.15%，2024-01 ~ 2026-10，周频，起点=1）",
                 "nav_curves_fusion.png")
        nav_plot("prod", "指增产品净值曲线（已扣交易成本与管理费，2024-01 ~ 2026-10，周频，起点=1）",
                 "nav_curves_product_fusion.png")
        excess_plot("active", "主动组合相对中证A500的累计超额收益（已扣交易成本 0.15%）",
                    "excess_curves_active_fusion.png")
        excess_plot("prod", "指增产品相对中证A500的累计超额收益（已扣交易成本与管理费）",
                    "excess_curves_fusion.png")
        print("\n图片已输出: nav_curves_fusion.png, nav_curves_product_fusion.png, "
              "excess_curves_active_fusion.png, excess_curves_fusion.png")

    print(f"\n输出目录: {ROOT}")


if __name__ == "__main__":
    main()
