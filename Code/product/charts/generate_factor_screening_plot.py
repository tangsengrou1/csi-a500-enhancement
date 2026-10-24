from pathlib import Path
import os

import matplotlib.pyplot as plt
import pandas as pd


from paths import DATA, RESULT
REPORT_DIR = Path(os.environ.get('A500_REPORT_ROOT', str(RESULT)))
DATA_DIR = DATA / 'provenance'
(REPORT_DIR / 'figures').mkdir(parents=True, exist_ok=True)
OUTPUT = REPORT_DIR / 'figures/factor_screening_summary.png'
RANK_IC_OUTPUT = REPORT_DIR / 'figures/ridge_rank_ic_screening.png'
CORR_OUTPUT = REPORT_DIR / 'figures/ridge_selected_factor_correlation.png'
LAYERED_OUTPUT = REPORT_DIR / 'figures/factor_layered_returns.png'

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS"],
        "axes.unicode_minus": False,
        "axes.edgecolor": "#B8BEC5",
        "axes.labelcolor": "#1F252B",
        "text.color": "#1F252B",
        "xtick.color": "#4B535B",
        "ytick.color": "#1F252B",
    }
)


def screening_counts(path: Path, reason_order: list[str]) -> pd.DataFrame:
    records = pd.read_csv(path, dtype={"fold_id": str})
    counts = (
        records.groupby(["fold_id", "reason"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=reason_order, fill_value=0)
        .sort_index()
    )
    totals = counts.sum(axis=1)
    if not totals.eq(344).all():
        raise ValueError(f"Unexpected factor totals in {path}: {totals.to_dict()}")
    return counts


def draw_panel(ax, data, title, labels, colors):
    y = range(len(data.index))
    left = pd.Series(0, index=data.index, dtype=float)
    for reason, label, color in zip(data.columns, labels, colors):
        values = data[reason]
        bars = ax.barh(
            y,
            values,
            left=left,
            height=0.58,
            label=label,
            color=color,
            edgecolor="white",
            linewidth=0.8,
        )
        for bar, value in zip(bars, values):
            if value >= 8:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{int(value)}",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="#1F252B",
                    fontweight="semibold",
                )
        left = left + values

    ax.set_title(title, fontsize=12, fontweight="bold", color="#000000", pad=10)
    ax.set_yticks(list(y), data.index)
    ax.invert_yaxis()
    ax.set_xlim(0, 344)
    ax.set_xticks([0, 100, 200, 300, 344])
    ax.grid(axis="x", color="#E4E7EA", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.19),
        ncol=len(labels),
        frameon=False,
        fontsize=9,
        handlelength=1.4,
        columnspacing=1.2,
    )


def main():
    ridge = screening_counts(
        DATA_DIR / "linear" / "feature_screen.csv",
        ["QUALITY_OR_IC_GATE", "CORRELATION_GATE", "SELECTED"],
    )
    lightgbm = screening_counts(
        DATA_DIR / "tree" / "feature_screen.csv",
        ["QUALITY_GATE", "SELECTED"],
    )

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7), sharex=True)
    draw_panel(
        axes[0],
        ridge,
        "Ridge：逐步压缩并去冗余",
        ["质量或IC门槛剔除", "相关性门槛剔除", "最终入选"],
        ["#D9DDE1", "#E6B85C", "#45A89A"],
    )
    draw_panel(
        axes[1],
        lightgbm,
        "LightGBM：保留宽特征集",
        ["质量门槛剔除", "最终入选"],
        ["#D9DDE1", "#45A89A"],
    )
    fig.supxlabel("因子数量（每折原始因子共344个）", fontsize=10, y=0.05)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.87, bottom=0.28, wspace=0.17)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    linear = pd.read_csv(DATA_DIR / "linear" / "feature_screen.csv", dtype={"fold_id": str})
    linear = linear.dropna(subset=["rank_ic_abs"]).copy()
    linear["category"] = linear["reason"].map(
        {
            "SELECTED": "最终入选",
            "CORRELATION_GATE": "相关性门槛剔除",
            "QUALITY_OR_IC_GATE": "质量或IC门槛剔除",
        }
    )
    linear = linear.dropna(subset=["category"])
    categories = ["最终入选", "相关性门槛剔除", "质量或IC门槛剔除"]
    colors = ["#45A89A", "#E6B85C", "#D9DDE1"]
    fig, ax = plt.subplots(figsize=(9.8, 4.6))
    positions = list(range(1, len(categories) + 1))
    values = [linear.loc[linear["category"] == c, "rank_ic_abs"] for c in categories]
    box = ax.boxplot(
        values,
        positions=positions,
        widths=0.52,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "#1F252B", "linewidth": 1.5},
        whiskerprops={"color": "#7C858D", "linewidth": 1.0},
        capprops={"color": "#7C858D", "linewidth": 1.0},
    )
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_edgecolor("white")
    fold_offsets = [-0.12, 0, 0.12]
    fold_colors = ["#227C9D", "#8B5E34", "#7A4EAB"]
    for fold, offset, color in zip(sorted(linear["fold_id"].unique()), fold_offsets, fold_colors):
        means = linear.loc[linear["fold_id"] == fold].groupby("category")["rank_ic_abs"].mean()
        for pos, category in zip(positions, categories):
            if category in means.index:
                ax.scatter(pos + offset, means[category], s=26, color=color, zorder=4, label=f"{fold}折" if pos == 1 else None)
    ax.axhline(0.01, color="#B34A4A", linewidth=1.2, linestyle="--", label="绝对Rank IC门槛 0.01")
    ax.set_xticks(positions, categories)
    ax.set_ylabel("训练期绝对 Rank IC")
    ax.set_title("Ridge筛选结果的训练期绝对 Rank IC 分布", fontsize=12, fontweight="bold", color="#000000", pad=10)
    ax.grid(axis="y", color="#E4E7EA", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper right", frameon=False, fontsize=8.5, ncol=2)
    ax.text(0.01, -0.22, "箱体为三折合并分布；点为各折均值。相关性剔除的因子预测力仍可能较高，剔除原因是与已选因子重复。", transform=ax.transAxes, fontsize=8.5, color="#4B535B")
    fig.subplots_adjust(left=0.10, right=0.98, top=0.86, bottom=0.25)
    fig.savefig(RANK_IC_OUTPUT, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # Use the 2026 Ridge fold for a readable correlation view of the deployed factor set.
    ridge_2026 = linear[(linear["fold_id"] == "2026") & (linear["selected"])]
    ridge_factors = ridge_2026.sort_values("selection_score", ascending=False)["factor"].tolist()
    factor_root = DATA_DIR.parent / "factor_store"
    factor_paths = {p.stem: p for p in factor_root.rglob("*.parquet")}
    missing = [name for name in ridge_factors if name not in factor_paths]
    if missing:
        raise FileNotFoundError(f"Missing factor files for correlation plot: {missing}")
    factor_values = []
    for name in ridge_factors:
        frame = pd.read_parquet(factor_paths[name])
        frame.columns = frame.columns.astype(str)
        factor_values.append(frame.stack(dropna=False).rename(name))
    corr = pd.concat(factor_values, axis=1).corr(method="spearman")
    fig, ax = plt.subplots(figsize=(10.8, 9.5))
    im = ax.imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1, aspect="equal")
    labels = [name.replace("gtjaAlpha", "A") for name in corr.columns]
    ax.set_xticks(range(len(labels)), labels, rotation=90, fontsize=5.3)
    ax.set_yticks(range(len(labels)), labels, fontsize=5.3)
    ax.set_title("2026折 Ridge 入选因子 Spearman 相关性", fontsize=12, fontweight="bold", color="#000000", pad=12)
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("相关系数", fontsize=9)
    fig.subplots_adjust(left=0.16, right=0.91, bottom=0.18, top=0.91)
    fig.savefig(CORR_OUTPUT, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # Compare one representative factor from each model with equal-weight quintile portfolios.
    market = pd.read_parquet(
        DATA_DIR.parent / "raw" / "processed_data.parquet",
        columns=["securityID", "trade_dt", "close"],
    )
    market["trade_dt"] = pd.to_datetime(market["trade_dt"])
    close = market.pivot(index="trade_dt", columns="securityID", values="close").sort_index()
    signal_dates = pd.read_parquet(factor_paths["gtjaAlpha70"]).index
    signal_dates = pd.DatetimeIndex(signal_dates).tz_localize(None)
    calendar = close.index
    rows = []
    for i, signal_date in enumerate(signal_dates[:-1]):
        next_signal = signal_dates[i + 1]
        exec_date = calendar[calendar > signal_date][0]
        next_exec = calendar[calendar > next_signal][0]
        ret = close.loc[next_exec] / close.loc[exec_date] - 1
        rows.append((signal_date, ret))
    returns = pd.DataFrame({date: ret for date, ret in rows}).T

    def layered_curve(factor_name):
        factor = pd.read_parquet(factor_paths[factor_name])
        factor.index = pd.to_datetime(factor.index).tz_localize(None)
        factor.columns = factor.columns.astype(str)
        common = factor.index.intersection(returns.index)
        layer_returns = {q: [] for q in range(1, 6)}
        for date in common:
            values = factor.loc[date].reindex(returns.columns)
            future = returns.loc[date]
            valid = pd.concat([values.rename("factor"), future.rename("ret")], axis=1).dropna()
            if len(valid) < 50:
                for q in layer_returns:
                    layer_returns[q].append(float("nan"))
                continue
            ranks = valid["factor"].rank(method="first")
            groups = pd.qcut(ranks, 5, labels=False) + 1
            for q in layer_returns:
                layer_returns[q].append(valid.loc[groups == q, "ret"].mean())
        out = pd.DataFrame(layer_returns, index=common).fillna(0.0)
        return (1 + out).cumprod()

    curves = {"Ridge: gtjaAlpha70": layered_curve("gtjaAlpha70"), "LightGBM: gtjaAlpha127": layered_curve("gtjaAlpha127")}
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    palette = ["#B24C63", "#D98E4A", "#7A9E9F", "#3D8C8C", "#1D5D75"]
    for ax, (title, curve) in zip(axes, curves.items()):
        for q, color in zip(range(1, 6), palette):
            ax.plot(curve.index, curve[q], color=color, linewidth=1.2, label=f"第{q}组")
        ax.axhline(1.0, color="#B8BEC5", linewidth=0.8)
        ax.set_title(title, fontsize=11, fontweight="bold", color="#000000", pad=9)
        ax.grid(axis="y", color="#E4E7EA", linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="x", rotation=35, labelsize=8)
        ax.legend(frameon=False, fontsize=8, ncol=5, loc="upper left")
    axes[0].set_ylabel("分层组合累计净值（初始=1）")
    fig.supxlabel("信号周", fontsize=9, y=0.03)
    fig.suptitle("Ridge与LightGBM代表因子的五分位分层收益", fontsize=12, fontweight="bold", color="#000000", y=0.99)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.83, bottom=0.20, wspace=0.10)
    fig.savefig(LAYERED_OUTPUT, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
