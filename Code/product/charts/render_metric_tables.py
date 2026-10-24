# -*- coding: utf-8 -*-
"""
把 backtest_metrics_fusion.csv 的两个口径渲染成图片表（已扣成本口径）：
- metrics_table_active_fusion.png    主动组合（已扣交易成本 0.15%，6 组合 + 基准）
- metrics_table_product_fusion.png   指增产品（已扣交易成本与管理费，6 组合 + 基准）
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from paths import RESULT
ROOT = RESULT / 'final_fusion'
MET = pd.read_csv(ROOT / "backtest_metrics_fusion.csv")

COLS = ["组合", "累计收益", "年化收益", "年化波动", "最大回撤", "夏普比率",
        "累计超额", "年化超额", "跟踪误差(年化)", "信息比率", "周胜率", "年化换手(单边)"]


def render(rows, title, outname):
    tab = MET[MET["组合"].isin(rows)].set_index("组合").loc[rows, COLS[1:]]
    cell = [[""] + list(tab.columns)]
    for name, r in tab.iterrows():
        line = [name]
        for c in tab.columns:
            v = r[c]
            if pd.isna(v):
                line.append("—")
            elif c == "年化换手(单边)":
                line.append(f"{v:.1f}x")
            elif c in ("夏普比率", "信息比率"):
                line.append(f"{v:.2f}")
            else:
                line.append(f"{v:.2%}")
        cell.append(line)

    n_rows, n_cols = len(cell), len(cell[0])
    fig, ax = plt.subplots(figsize=(1.65 * n_cols, 0.55 * n_rows))
    ax.axis("off")
    table = ax.table(cellText=cell, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
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
    fig.suptitle(title, fontsize=12, fontweight="bold", y=0.93)
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(ROOT / outname, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"输出: {ROOT / outname}")


def main():
    idx_rows = ["中证A500全收益指数"]
    active_rows = ["主动-BL组合", "主动-风险约束BL", "主动-MV组合",
                   "主动-等权组合", "主动-MV+约束组合", "主动-BL+约束组合"]
    prod_rows = ["指增产品-BL组合", "指增产品-风险约束BL", "指增产品-MV组合",
                 "指增产品-等权组合", "指增产品-MV+约束组合", "指增产品-BL+约束组合"]

    render(idx_rows + active_rows,
           "主动组合业绩指标（已扣交易成本 0.15%，2024-01 ~ 2026-10）",
           "metrics_table_active_fusion.png")
    render(idx_rows + prod_rows,
           "指增产品业绩指标（已扣交易成本与管理费，2024-01 ~ 2026-10）",
           "metrics_table_product_fusion.png")


if __name__ == "__main__":
    main()
