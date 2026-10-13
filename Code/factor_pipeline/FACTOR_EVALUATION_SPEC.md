# 单因子评价系统规格

本文档是当前单因子评价系统的机器可读交接说明，供组员和后续 AI 在不改变研究口径的前提下继续开发。

## 1. 系统目标与边界

系统每周在当时有效的指数成分股内计算一个因子截面，将因子值映射为多头、满仓的股票权重，在下一交易日建仓，并持有至下一个执行日。每个因子独立输出收益、波动率、最大回撤、Sharpe、单边换手率、Rank IC/ICIR、净值曲线、逐期权重和诊断信息，同时输出因子间截面相关性。

当前模块用于“单因子初筛”，不包含行业中性、个股偏离、跟踪误差约束、Black-Litterman或最终组合优化。这些应在后续组合层完成，不能悄悄加入本模块后改变因子评价口径。

## 2. 输入接口

### 行情数据

长表至少包含：

- `date`或`trade_dt`：交易日；
- `wind_code`或`securityID`：证券代码；
- `close`：收盘价。

因子可以额外声明需要`open`、`high`、`low`、`volume`/`vol`、`amount`、`vwap`或`turnover`/`turn`。`date + wind_code`必须唯一。

### 历史成分股

正式运行必须传入历史成分股快照，字段为`date`（或`effective_date`）和`wind_code`（或`securityID`）。信号日仅使用不晚于该日的最近快照。固定股票池只允许通过`allow_development_universe=true`用于开发调试。

### 因子接口

因子通过`FactorRegistry`注册。每个`FactorDefinition`必须给出唯一ID、方向、所需字段和计算函数。计算函数接收`MarketPanel`，返回“交易日 × 股票”的`DataFrame`。方向为`1`表示原值越大越好，`-1`表示原值越小越好。

## 3. 时间线与防前视

1. 每周最后一个实际交易日收盘后形成信号。
2. 只使用信号日及以前的数据和当时有效的成分股。
3. 下一交易日按配置的价格字段执行。
4. 持有至下一次信号后的执行日。
5. 组合收益扣除“单边换手率 × 交易成本”。

因此，任何新因子都不得在信号日读取未来行情。财务因子必须在上游依据公告日期做可得性处理。

## 4. 因子预处理

截面处理顺序固定为：转数值、删除无穷值和缺失值、按`winsorize_lower`/`winsorize_upper`分位数去极值、乘以因子方向。若有效股票少于`minimum_stocks`，或截面只有一个唯一值，本期跳过。

## 5. 仓位映射选项

令处理后的因子值为`s_i`，百分位排名为`r_i ∈ (0, 1]`，最终权重均满足`w_i ≥ 0`且`Σw_i = 1`。

| `position_mapping` | 公式/规则 | 主要参数 | 适用场景与特点 |
|---|---|---|---|
| `top_quantile_equal_weight` | 选择`r_i > 1-q`，入选股票等权 | `top_fraction=q` | 最容易解释，降低极端因子值影响；分位点并列时持仓数可能略有变化 |
| `top_quantile_rank_weighted` | 选择顶部`q`，按`r_i^p`归一化 | `top_fraction`、`rank_exponent=p` | 保留集中选股，同时让高排名获得更高权重 |
| `rank_weighted_long_only` | 全部有效股票按`r_i^p`归一化 | `rank_exponent=p` | 权重连续、较分散，通常比硬切分更稳定 |
| `score_proportional_long_only` | 按`s_i-min(s)+ε`归一化 | `score_floor=ε` | 保留因子值间距；对量纲和极端值较敏感，必须先去极值 |
| `softmax_long_only` | 先截面标准化，再按`exp(z_i/T)`归一化 | `softmax_temperature=T` | 平滑且可调集中度；`T`越小越集中，越大越接近等权 |
| `linear_rank_tilt` | 按`max(0, 1+k(2r_i-1))`归一化 | `rank_tilt_strength=k` | 从全样本等权连续倾斜；`k=0`为等权，`k`越大越偏向高排名 |

参数约束：`0 < top_fraction ≤ 1`、`rank_exponent > 0`、`score_floor > 0`、`softmax_temperature > 0`、`rank_tilt_strength ≥ 0`。非法参数必须直接报错，不得静默使用默认值。

推荐初筛时至少比较：顶部20%等权、全样本排名加权和Softmax。评价结果应同时看收益、风险、换手和稳定性，不能只按累计收益选择。

## 6. 配置示例

```json
{
  "position_mapping": "softmax_long_only",
  "top_fraction": 0.2,
  "rank_exponent": 1.0,
  "score_floor": 1e-12,
  "softmax_temperature": 1.0,
  "rank_tilt_strength": 1.0,
  "minimum_stocks": 10,
  "ic_minimum_stocks": 10,
  "correlation_minimum_stocks": 10,
  "periods_per_year": 52,
  "transaction_cost_bps": 20
}
```

一次运行只采用一种映射。横向比较不同映射时，除映射及其专属参数外，其余配置、股票池和样本期必须保持一致。

## 7. Rank IC与ICIR口径

每个信号日，在当时有效成分股中，将完成去极值和方向统一后的因子分数，与“下一执行日到再下一执行日”的个股收益做Spearman秩相关。该相关系数为当期Rank IC。只有共同有效股票数不低于`ic_minimum_stocks`且两个截面均有变化时才计算。

- `rank_ic_mean`：各期Rank IC算术平均；
- `rank_ic_std`：各期Rank IC样本标准差；
- `rank_icir`：`rank_ic_mean / rank_ic_std`，不年化；
- `rank_icir_annualized`：`rank_icir × sqrt(periods_per_year)`；
- `rank_ic_positive_ratio`：Rank IC大于0的期数比例。

因子方向已统一，因此正Rank IC表示因子排序与未来收益方向一致。IC使用全部有效股票，而不是仓位映射后入选的股票。

## 8. 因子相关性口径

每个信号日，对两个因子在共同有效成分股上的处理后分数计算Spearman相关系数，随后对时间求均值。只有共同样本数不低于`correlation_minimum_stocks`时才计算。由于相关性使用方向统一后的分数，正值表示两个因子的预期收益排序相近。

该指标用于识别重复因子，不代表因果关系。筛选时应结合Rank IC、稳定性、换手率和经济含义，不能简单删除所有高相关因子。

## 9. 输出契约

`FactorEvaluationResult.save()`产生：

- `factor_summary.csv`：累计收益、年化收益、年化波动率、最大回撤、Sharpe和平均单边换手率；
- `factor_rank_ic.csv`：逐信号日Rank IC、有效样本数和覆盖率；
- `factor_weekly_returns.csv`：周度净收益；
- `factor_pnl_curves.csv`：从1开始的累计净值；
- `factor_turnover.csv`：逐期单边换手率；
- `factor_weights.csv`：信号日、执行日、退出日、原始因子值、处理后分数和权重；
- `factor_diagnostics.csv`：覆盖率、股票数、成本、收益、状态和股票池类型。
- `factor_correlations_weekly.csv`：逐信号日、逐因子对的Spearman相关性；
- `factor_correlations_summary.csv`：因子对的时间均值、标准差、平均绝对相关性和样本数；
- `factor_correlation_matrix.csv`：平均Spearman相关系数矩阵，便于热力图和聚类使用。

组合收益、净值、换手率、权重、诊断和总表携带`position_mapping`字段，便于合并多种映射的试验结果时追溯口径。Rank IC和因子相关性由映射前的因子分数计算，因此不随`position_mapping`变化。

## 10. 扩展规则

新增仓位映射时，只修改`scores_to_weights()`及配置文档，并遵守以下不变量：

1. 输入为已经完成方向统一和去极值的`Series`；
2. 输出索引只能是输入股票的子集；
3. 输出必须有限、非负、总和为1；
4. 无法形成合法组合时返回空`Series`，参数非法时抛出`ValueError`；
5. 增加单元测试和小型端到端测试；
6. 不在映射函数内读取行情、成分股或未来数据。

## 11. 验证命令

```bash
python -m compileall Code/a500 Code/run_factor_evaluation.py Code/tests
python Code/tests/run_tests.py
```

如果环境已安装`pytest`，也可以运行：

```bash
pytest -q Code/tests
```

正式研究前仍需补齐2020—测试期的历史成分股，以及可支持相应因子窗口的更早行情。当前固定500只股票的数据只能用于开发验证，不能当作无前视偏差的正式结果。
