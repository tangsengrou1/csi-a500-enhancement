# -*- coding: utf-8 -*-
"""
指增产品扣成本与费用前后业绩指标（毛 → 扣交易成本 → 扣交易成本+管理费）。
交易成本：单边 0.15%（打包：佣金+印花税+冲击成本），对每周单边换手收取；
管理费：0.5%/年，按周折算，对全部产品净值收取（含 80% 指数部分）。
第 T 周：主动净收益 = r_T − 0.15%×turn_T；
指增产品净收益 = 0.8×指数 + 0.2×主动净收益 − 周管理费。未扣托管费。

输入: backtest_weekly_fusion.csv（含 turn_{k}、r_net_{k}、r_prod_net_{k} 列）
输出:
- backtest_metrics_net_fusion.csv                毛/扣交易/扣交易+管理费 三组指标
- metrics_table_product_net_fusion.png           对应图片表
"""
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from paths import RESULT
ROOT = RESULT / 'final_fusion'
COST = 0.0015       # 单边交易成本（打包：佣金+印花税+冲击成本）
MGMT_FEE = 0.005    # 年化管理费
FEE_W = (1.0 + MGMT_FEE) ** (1.0 / 52.0) - 1.0
PASSIVE_W = 0.8
RF = 0.0

ACTIVE = ["bl", "blrisk", "mv", "eq", "ind", "blc"]
LABEL = {"bl": "BL组合", "blrisk": "风险约束BL", "mv": "MV组合", "eq": "等权组合",
         "ind": "MV+约束组合", "blc": "BL+约束组合"}
MET_COLS = ["年化收益(毛)", "年化收益(扣交易)", "年化收益(扣交易+管理费)",
            "年化超额(毛)", "年化超额(扣交易)", "年化超额(扣交易+管理费)",
            "信息比率(毛)", "信息比率(扣交易)", "信息比率(扣交易+管理费)"]


def ann_return(r):
    n = len(r)
    total = np.prod(1.0 + r) - 1.0
    return (1.0 + total) ** (52.0 / n) - 1.0


def ann_excess(rp, rb):
    n = len(rp)
    ratio = np.prod(1.0 + rp) / np.prod(1.0 + rb) - 1.0
    return (1.0 + ratio) ** (52.0 / n) - 1.0


def excess_ir(rp, rb):
    ex = rp - rb
    te = ex.std() * np.sqrt(52.0)
    return ex.mean() * 52.0 / te if te > 0 else np.nan


def main():
    df = pd.read_csv(ROOT / "backtest_weekly_fusion.csv")
    r_idx = df["r_idx"].to_numpy()

    rows = []
    for k in ACTIVE:
        rp_gross = PASSIVE_W * r_idx + (1.0 - PASSIVE_W) * df[f"r_{k}"].to_numpy()
        rp_trade = PASSIVE_W * r_idx + (1.0 - PASSIVE_W) * df[f"r_net_{k}"].to_numpy()
        rp_full = df[f"r_prod_net_{k}"].to_numpy()
        rows.append([
            f"指增产品-{LABEL[k]}",
            ann_return(rp_gross), ann_return(rp_trade), ann_return(rp_full),
            ann_excess(rp_gross, r_idx), ann_excess(rp_trade, r_idx), ann_excess(rp_full, r_idx),
            excess_ir(rp_gross, r_idx), excess_ir(rp_trade, r_idx), excess_ir(rp_full, r_idx),
        ])

    a = ann_return(r_idx)
    rows.append(["中证A500全收益指数", a, a, a, 0.0, 0.0, 0.0, np.nan, np.nan, np.nan])

    met = pd.DataFrame(rows, columns=["组合"] + MET_COLS)
    met.to_csv(ROOT / "backtest_metrics_net_fusion.csv", index=False, encoding="utf-8-sig")
    print(f"交易成本: 单边 {COST:.2%}；管理费: {MGMT_FEE:.1%}/年（未扣托管费）")
    print("指增产品口径，毛 → 扣交易成本 → 扣交易成本+管理费:")
    print(met.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    cell = [[""] + MET_COLS]
    for _, r in met.iterrows():
        line = [r["组合"]]
        for c in MET_COLS:
            v = r[c]
            if pd.isna(v):
                line.append("—")
            elif c.startswith("信息比率"):
                line.append(f"{v:.2f}")
            else:
                line.append(f"{v:.2%}")
        cell.append(line)

    n_rows, n_cols = len(cell), len(cell[0])
    fig, ax = plt.subplots(figsize=(1.55 * n_cols, 0.55 * n_rows))
    ax.axis("off")
    table = ax.table(cellText=cell, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1, 1.9)
    for j in range(n_cols):
        table[0, j].set_facecolor("#2f5597")
        table[0, j].set_text_props(color="white", fontweight="bold")
    for i in range(1, n_rows):
        table[i, 0].set_text_props(fontweight="bold")
        table[i, 0].set_facecolor("#f2f2f2")
        for j in range(1, n_cols):
            if i % 2 == 0:
                table[i, j].set_facecolor("#f7f9fc")
    fig.suptitle("指增产品扣成本与费用前后业绩指标（单边交易成本 0.15% + 管理费 0.5%/年，2024-01 ~ 2026-10）",
                 fontsize=12, fontweight="bold", y=0.93)
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(ROOT / "metrics_table_product_net_fusion.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n图片已输出: {ROOT / 'metrics_table_product_net_fusion.png'}")


if __name__ == "__main__":
    main()
