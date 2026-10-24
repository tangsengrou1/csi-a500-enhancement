"""绘制融合 BL 约束组合的行业平均偏离图。

偏离定义为：主动组合行业权重 - 中证 A500 基准行业权重。
正值表示相对基准超配，负值表示相对基准低配。
运行：
    python plot_industry_deviation.py
"""
from pathlib import Path
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


from paths import RESULT
ROOT = Path(os.environ.get('A500_REPORT_ROOT', str(RESULT)))
INPUT = RESULT / 'final_fusion/industry_deviation_v3_fusion.parquet'
OUT_DIR = ROOT / 'figures'
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    data = pd.read_parquet(INPUT)
    # 逐行业跨期平均。保留符号，才能同时显示超配和低配方向。
    summary = (
        data.groupby("industry", as_index=False)
        .agg(mean_dev=("dev", "mean"), mean_abs_dev=("dev", lambda x: x.abs().mean()),
             max_abs_dev=("dev", lambda x: x.abs().max()))
        .sort_values("mean_dev")
    )
    summary.to_csv(OUT_DIR / "industry_deviation_by_industry.csv", index=False, encoding="utf-8-sig")

    plt.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial"],
        "axes.unicode_minus": False,
        "font.size": 11,
        "pdf.fonttype": 42,
    })
    fig, ax = plt.subplots(figsize=(12, 10))
    values = summary["mean_dev"] * 100
    colors = ["#2F78B7" if value >= 0 else "#D97757" for value in values]
    ax.barh(summary["industry"], values, color=colors, edgecolor="white", linewidth=0.35)
    ax.axvline(0, color="#444444", linewidth=0.9)
    ax.grid(axis="x", color="#B8B8B8", linewidth=0.6, alpha=0.7)
    ax.set_axisbelow(True)
    ax.set_xlabel("超配（+）/ 低配（−），百分点")
    ax.set_ylabel("申万一级行业")
    ax.set_title("融合 BL 约束组合相对中证 A500 的行业平均偏离", fontsize=15, pad=12)
    ax.text(0.99, 0.01, "蓝色：平均超配    橙色：平均低配\n统计期：98 个行业约束生效期",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=9, color="#555555")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "industry_deviation_by_industry.png", dpi=240, bbox_inches="tight")
    fig.savefig(OUT_DIR / "industry_deviation_by_industry.pdf", bbox_inches="tight")
    plt.close(fig)

    top = summary.loc[summary["mean_dev"].abs().idxmax()]
    print(f"行业数: {len(summary)}")
    print(f"平均偏离绝对值最大的行业: {top['industry']} ({top['mean_dev']:.4%})")
    print(f"图表输出: {OUT_DIR / 'industry_deviation_by_industry.png'}")


if __name__ == "__main__":
    main()
