# -*- coding: utf-8 -*-
"""
六组合年化单边换手率柱状图（指增产品口径 = 0.2 × 主动口径）。
数据取自 backtest_metrics_fusion.csv 的"指增产品-XX"行"年化换手(单边)"列。
输出: turnover_by_combo_fusion.png
"""
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from paths import RESULT
ROOT = RESULT / 'final_fusion'

ACTIVE = ["bl", "blrisk", "mv", "eq", "ind", "blc"]
LABEL = {"bl": "BL组合", "blrisk": "风险约束BL", "mv": "MV组合", "eq": "等权组合",
         "ind": "MV+约束组合", "blc": "BL+约束组合"}
COLORS = {"bl": "#1f77b4", "blrisk": "#ff7f0e", "mv": "#2ca02c",
          "eq": "#d62728", "ind": "#9467bd", "blc": "#8c564b"}


def main():
    met = pd.read_csv(ROOT / "backtest_metrics_fusion.csv")
    names = [f"指增产品-{LABEL[k]}" for k in ACTIVE]
    sub = met[met["组合"].isin(names)].set_index("组合").loc[names]
    vals = sub["年化换手(单边)"].to_numpy()

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar([LABEL[k] for k in ACTIVE], vals,
                  color=[COLORS[k] for k in ACTIVE], width=0.6)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.25, f"{v:.1f}x",
                ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_ylabel("年化单边换手（倍/年）")
    ax.set_title("六组合年化单边换手率（指增产品口径，2024-01 ~ 2026-10）")
    ax.grid(alpha=0.3, axis="y")
    ax.set_ylim(0, max(vals) * 1.15)
    ax.text(0.01, 0.95,
            "指增产品口径换手 = 0.2 × 主动组合换手；MV+约束、BL+约束含换手惩罚项",
            transform=ax.transAxes, fontsize=9, va="top")
    fig.tight_layout()
    fig.savefig(ROOT / "turnover_by_combo_fusion.png", dpi=150)
    plt.close(fig)
    print("年化单边换手（指增产品口径）:")
    for k, v in zip(ACTIVE, vals):
        print(f"  {LABEL[k]:<8} {v:.1f}x/年")
    print(f"\n图片已输出: {ROOT / 'turnover_by_combo_fusion.png'}")


if __name__ == "__main__":
    main()
