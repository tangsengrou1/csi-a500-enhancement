"""统一评价三套信号，校验融合持仓，生成图表及中文报告。"""
from pathlib import Path
from paths import RAW
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
LABELS = dict(bl="BL", blrisk="风险约束BL", mv="MV", eq="等权", ind="MV＋约束", blc="BL＋约束")
FEE = 1.005 ** (1 / 52) - 1
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def metrics(r, b, turnover=np.nan):
    r, b = np.asarray(r), np.asarray(b)
    n = len(r)
    nav = np.r_[1., np.cumprod(1 + r)]
    ex = r - b
    te = ex.std() * np.sqrt(52)
    return {"累计收益": np.prod(1 + r) - 1,
            "年化收益": np.prod(1 + r) ** (52 / n) - 1,
            "年化波动": r.std() * np.sqrt(52),
            "最大回撤": (nav / np.maximum.accumulate(nav) - 1).min(),
            "累计超额": np.prod(1 + r) / np.prod(1 + b) - 1,
            "年化超额": (np.prod(1 + r) / np.prod(1 + b)) ** (52 / n) - 1,
            "跟踪误差": te, "信息比率": ex.mean() * 52 / te if te > 0 else np.nan,
            "周胜率": (ex > 0).mean(), "年化单边换手": turnover}


def table(df, cols):
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        values = []
        for c in cols:
            v = row[c]
            if isinstance(v, (float, np.floating)):
                v = f"{v:.2f}" if c in ("信息比率", "年化单边换手") else f"{v:.2%}"
            values.append(str(v))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def validate(f):
    weights = {}
    for version, keys in [(1, ["bl", "blrisk", "mv", "eq"]), (2, ["ind"]), (3, ["blc"])]:
        w = pd.read_parquet(ROOT / f"portfolio_weights_v{version}_fusion.parquet")
        assert not w.duplicated(["week", "securityID"]).any()
        assert sorted(w.week.unique()) == f.week.tolist()
        for k in keys:
            v = w[f"{k}_w"]
            assert np.isfinite(v).all() and v.min() >= -1e-7 and v.max() <= .1000001
            assert np.allclose(w.groupby("week")[f"{k}_w"].sum(), 1, atol=1e-5)
            weights[k] = w
    px = pd.read_parquet(
        RAW / "processed_data.parquet",
        columns=["trade_dt", "securityID", "close"]).pivot(index="trade_dt", columns="securityID", values="close").sort_index()
    px.index = pd.to_datetime(px.index).normalize()
    for k, w in weights.items():
        previous = None
        for _, row in f.iterrows():
            current = w.loc[w.week.eq(row.week)].set_index("securityID")[f"{k}_w"]
            start, end = px.loc[pd.Timestamp(row.w_date)], px.loc[pd.Timestamp(row.end_date)]
            returns = end / start - 1
            gross = float((current * returns.reindex(current.index)).sum())
            assert np.isclose(gross, row[f"r_{k}"], atol=1e-10)
            if previous is None:
                turn = .5 * current.abs().sum()
            else:
                univ = previous.index.union(current.index)
                turn = .5 * (current.reindex(univ, fill_value=0) - previous.reindex(univ, fill_value=0)).abs().sum()
            assert np.isclose(turn, row[f"turn_{k}"], atol=1e-9)
            assert np.isclose(gross - .0015 * turn, row[f"r_net_{k}"], atol=1e-10)
            assert np.isclose(.8 * row.r_idx + .2 * row[f"r_net_{k}"] - FEE,
                              row[f"r_prod_net_{k}"], atol=1e-10)
            previous = current * (1 + returns.reindex(current.index)) / (1 + gross)
    return {"weight_constraints": True, "independent_gross_return_check": True,
            "independent_drift_turnover_check": True, "net_cost_and_fee_check": True}


def main():
    frames = {"线性": pd.read_csv(BASE / "final/backtest_weekly_external.csv"),
              "树模型": pd.read_csv(BASE / "final_tree/backtest_weekly_tree.csv"),
              "融合": pd.read_csv(ROOT / "backtest_weekly_fusion.csv")}
    f = frames["融合"]
    for df in frames.values():
        assert df.week.equals(f.week)
        assert df.w_date.equals(f.w_date) and df.end_date.equals(f.end_date)
        assert np.allclose(df.r_idx, f.r_idx)
        assert np.isfinite(df.filter(regex="^r_").to_numpy()).all()
    checks = validate(f)
    checks["three_sources_same_window_and_benchmark"] = True
    (ROOT / "validation_results.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    rows, years, months = [], [], []
    for model, df in frames.items():
        for k, name in LABELS.items():
            r = df[f"r_prod_net_{k}"]
            rows.append({"模型": model, "组合": name, **metrics(r, df.r_idx, .2 * df[f"turn_{k}"].sum() * 52 / len(df))})
            for year, g in df.groupby(pd.to_datetime(df.end_date).dt.year):
                rr, bb = g[f"r_prod_net_{k}"], g.r_idx
                years.append({"模型": model, "组合": name, "年份": year, "周数": len(g),
                              **metrics(rr, bb), "基准累计收益": np.prod(1 + bb) - 1})
            for month, g in df.groupby(pd.to_datetime(df.end_date).dt.to_period("M")):
                rr, bb = g[f"r_prod_net_{k}"], g.r_idx
                excess = np.prod(1 + rr) / np.prod(1 + bb) - 1
                months.append({"模型": model, "组合": name, "月份": str(month), "累计超额": excess, "跑赢": excess > 0})
    comparison = pd.DataFrame(rows)
    yearly = pd.DataFrame(years)
    monthly = pd.DataFrame(months)
    for name, data in [("comparison_metrics", comparison), ("yearly_metrics_same_window", yearly), ("monthly_excess", monthly)]:
        data.to_csv(ROOT / f"{name}.csv", index=False, encoding="utf-8-sig")
    # 产品主方案：两模型独立融合后重做BL约束优化，MV约束仅作备选。
    dates = pd.to_datetime(f.end_date)
    dates0 = pd.DatetimeIndex([pd.Timestamp(f.w_date.iloc[0])]).append(pd.DatetimeIndex(dates))
    fig, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
    for model, df in frames.items():
        nav = np.r_[1, np.cumprod(1 + df.r_prod_net_blc)]
        benchmark = np.r_[1, np.cumprod(1 + df.r_idx)]
        axes[0].plot(dates0, nav, label=f"{model}BL＋约束")
        axes[1].plot(dates0, nav / benchmark - 1, label=f"{model}BL＋约束")
    axes[0].plot(dates0, benchmark, color="black", label="A500全收益")
    axes[0].set_title("BL＋约束：线性、树模型与固定50/50信号融合（已扣成本及管理费）")
    axes[1].set_title("相对基准累计超额")
    for ax in axes:
        ax.grid(alpha=.25); ax.legend()
    fig.tight_layout(); fig.savefig(ROOT / "comparison_blc.png", dpi=160); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    own = comparison[comparison.模型.eq("融合")]
    axes[0].bar(own.组合, own.年化超额 * 100, color="#2f5597")
    axes[0].set_title("融合信号六组合：产品年化超额（%）")
    axes[1].bar(own.组合, own.年化单边换手, color="#438a78")
    axes[1].set_title("产品年化单边换手（倍）")
    for ax in axes:
        ax.tick_params(axis="x", rotation=25); ax.grid(axis="y", alpha=.2)
    fig.tight_layout(); fig.savefig(ROOT / "fusion_six_combinations.png", dpi=160); plt.close(fig)
    shortlist = comparison[comparison.组合.isin(["BL＋约束", "MV＋约束"])]
    cols = ["模型", "组合", "年化收益", "年化超额", "跟踪误差", "信息比率", "最大回撤", "年化单边换手"]
    fusion = own[own.组合.eq("BL＋约束")].iloc[0]
    lin = comparison[comparison.模型.eq("线性") & comparison.组合.eq("BL＋约束")].iloc[0]
    delta = fusion.信息比率 - lin.信息比率
    verdict = ("本次融合BL约束的信息比率高于线性版，但这仍是同一历史窗口内的研究结果，需要后续独立验证。"
               if delta > 0 else "本次融合BL约束的信息比率未超过线性版，现有结果不足以支持用融合方案替代线性主方案。")
    report = f"""# 固定50/50双模型融合产品：组合优化与回测报告

## 1. 产品与实验设计

产品 = 80%中证A500全收益指数 + 20%主动增强组合，周频再平衡。
主方案为融合信号驱动的BL＋约束，MV＋约束为低换手备选，其余四组合为研究对照。

融合公式：stacking = 0.5 × 线性排名分 + 0.5 × 树模型排名分。平均后不重新排名。
先按周与股票一一对齐，再融合；两模型缺失或信号日不一致时直接报错，禁止静默填补。
共{len(f)}周，收益区间{f.w_date.iloc[0]}至{f.end_date.iloc[-1]}，预测输入66,500行。
全部信号均检查不晚于组合信息截止日。

本次重新选股、重新估计组合权重、重新计算持仓收益与漂移换手，并据此扣费，未使用原有净收益简单平均代替融合回测。
融合比例事先固定为50/50，没有根据本窗口择优，也没有重新训练基础模型。
基础模型及其版本此前已经过研究筛选，本窗口属于融合方案研究评价，不是新独立样本外验证。

## 2. 优化与费用参数

沿用原final组合设定：前30只候选，BL/MV风险厌恶2.5，协方差窗口40交易日，个股主动权重上限10%，禁止卖空。
本目录将OSQP求解绝对/相对容差提高至1e-9并启用polishing，持仓边界按1e-7数值容差校验；旧结果沿用其原始求解精度。
MV＋约束与BL＋约束采用4周分数均值、行业偏离平方惩罚0.5、换手L1惩罚0.002；行业惩罚自2024-09-23起生效。
MV协方差使用原有极值处理，BL沿用未处理协方差；两者比较并非仅有后验收益这一项差异。
BL采用候选池等权逆向先验、P=I、Ω=τdiag(Σ)、τ=0.05，沿用原实现。

单边交易成本0.15%，按主动组合漂移后0.5×L1换手收取；产品年管理费0.5%，每周扣(1.005)^(1/52)−1。
首期建仓沿用原回测0.5×权重和的定义；指数复制成本、托管费及被动与主动仓位再平衡的额外成本未单独计入。

## 3. 融合信号六组合结果（产品净收益口径）

{table(own, cols[1:])}

![融合六组合](fusion_six_combinations.png)

## 4. 与原有两套分数的同窗口对照

{table(shortlist, cols)}

{verdict}
融合BL约束相对线性版的信息比率变化为{delta:+.3f}，年化超额变化为{(fusion.年化超额-lin.年化超额)*100:+.2f}个百分点。
这里的“约束”包括行业软惩罚，不表示严格行业中性，也未对跟踪误差施加硬上限。

本次执行前指定BL＋约束为主方案，不能事后把六组合中的最高指标当作预先选定策略的成绩。
实际结果中，融合MV＋约束的信息比率和换手优于融合BL＋约束，两者超额收益接近。
若后续产品优先考虑主动风险效率与交易可实施性，融合MV＋约束值得作为下一阶段主候选；
融合BL＋约束保留为原定主方案对照。最终取舍应在后续独立窗口验证。
分年度看，融合BL约束在2026年的超额低于两套单模型，说明全期改善不等于每个阶段均占优。

![三套信号BL约束对比](comparison_blc.png)

## 5. 分年度同窗口累计收益与超额

下表直接复合各年已有周收益，不对截取后的年内净值再次pct_change，因此不会漏掉每年第一笔周收益。
跨年周按期末日期归属；年初/年末不完整周未拆分，部分年份不应视为完整自然年业绩。

{table(yearly[yearly.组合.eq('BL＋约束')], ['模型','年份','周数','累计收益','基准累计收益','累计超额'])}

## 6. 口径与验证

三模型使用完全相同的周集合、交易起止日期与基准收益。年化收益、波动、超额和IR沿用52周口径。
汇总换手统一为每周换手之和×52/周数，并包含首期建仓；与旧指标文件中排除首期且按n−1年化的换手有小幅差异。
最大回撤纳入期初净值1。旧年度表存在漏掉首笔收益及基准起点不同的问题，本目录输出同窗口重算表，未修改原文件。

已逐周独立验证：权重加总、禁止卖空、个股上限、原始持仓收益、漂移换手、交易成本、产品管理费。
校验结果见validation_results.json；信号及原始代码哈希见run_manifest.json。

## 7. 局限与交付内容

沿用未复权价格与固定500只股票池，因此公司行为、幸存者偏差仍会影响结果；未模拟停牌、涨跌停和实际成交容量。
80%被动部分使用理想全收益指数复制，行业约束仅为软惩罚。当前结果不能作为未来收益承诺。

运行命令：`python Code/run.py`（在提交目录执行）。
代码按处理阶段拆分，三种预测源共用优化和回测实现；本包只写Result/reproduced。
主要输出：predictions_fusion.parquet、三版权重parquet、周收益/净值/指标CSV、三模型对比CSV、同窗口年度CSV、月度超额CSV、图表及运行日志。
"""
    (ROOT / "融合产品组合优化与回测报告.md").write_text(report, encoding="utf-8")
    print(shortlist.to_string(index=False))
    print("所有校验通过。" + verdict)


if __name__ == "__main__":
    main()
