# -*- coding: utf-8 -*-
"""
月度超额收益图：六种组合各一张（指增产品口径、已扣交易成本与管理费，vs 中证A500全收益），
逐月超额柱状图（绿=跑赢、红=跑输）+ 分年度跑赢月数统计。
风格沿用 backtest/monthly_win_plot.py。

输入: backtest_weekly_fusion.csv
输出: monthly_win_{bl,blrisk,mv,eq,ind,blc}_fusion.png
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
df = pd.read_csv(ROOT / "backtest_weekly_fusion.csv")
df["end_date"] = pd.to_datetime(df["end_date"])
d = df[df["end_date"] >= "2024-01-01"].copy()
d["ym"] = d["end_date"].dt.to_period("M")

COMBOS = [("bl", "BL组合"), ("blrisk", "风险约束BL"), ("mv", "MV组合"),
          ("eq", "等权组合"), ("ind", "MV+约束组合"), ("blc", "BL+约束组合")]


def monthly_excess(col):
    g = d.groupby("ym").agg(
        prod=(col, lambda r: np.prod(1.0 + r) - 1.0),
        idx=("r_idx", lambda r: np.prod(1.0 + r) - 1.0),
    )
    g["excess"] = g["prod"] - g["idx"]
    g["win"] = g["excess"] > 0
    return g


def main():
    for k, label in COMBOS:
        g = monthly_excess(f"r_prod_net_{k}")
        months = g.index.astype(str).tolist()

        print(f"=== 指增产品({label}) 分年跑赢月数 ===")
        for y in ["2024", "2025", "2026"]:
            sub = g[g.index.astype(str).str.startswith(y)]
            tag = "（截至10-09，10月为不完整月份）" if y == "2026" else ("（1月自01-15起）" if y == "2024" else "")
            print(f"{y} 年{tag}：跑赢 {int(sub['win'].sum())}/{len(sub)} 个月（月胜率 {sub['win'].mean():.1%}）")

        fig, ax = plt.subplots(figsize=(13, 5.5))
        colors = ["#d62728" if v < 0 else "#2ca02c" for v in g["excess"]]
        ax.bar(months, g["excess"] * 100, color=colors)
        ax.axhline(0, color="black", lw=0.8)
        ax.set_title(f"指增产品({label})月度超额收益 vs 中证A500全收益（已扣交易成本与管理费，2024-2026，截至2026-10-09）")
        ax.set_ylabel("月度超额收益 (%)")
        ax.tick_params(axis="x", rotation=45)
        ax.grid(alpha=0.3, axis="y")
        for i, y in enumerate(["2024", "2025", "2026"]):
            sub = g[g.index.astype(str).str.startswith(y)]
            tag = "（截至10-09）" if y == "2026" else ("（1月自01-15起）" if y == "2024" else "")
            ax.text(0.01, 0.96 - 0.08 * i, f"{y} 年{tag}：跑赢 {int(sub['win'].sum())}/{len(sub)} 个月",
                    transform=ax.transAxes, va="top", fontsize=11)
        fig.tight_layout()
        fig.savefig(ROOT / f"monthly_win_{k}_fusion.png", dpi=150)
        plt.close(fig)
        print(f"输出: monthly_win_{k}_fusion.png\n")


if __name__ == "__main__":
    main()
