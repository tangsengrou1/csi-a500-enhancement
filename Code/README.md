# 代码使用说明

## 环境

建议使用 Python 3.10 以上版本。安装 `requirements.txt` 后，在项目根目录执行命令。

## 输入文件

`Data/raw` 中必须恰好包含以下文件之一，扩展名可为 CSV 或 XLSX：

- `prices`：股票行情与可交易状态。
- `benchmark`：中证 A500 价格指数和全收益指数。
- `constituents`：历史成分股和权重。
- `industry`：历史申万一级行业。
- `valuation`：估值因子。
- `fundamentals`：财务因子及公告日期。
- `risk_free`：年化无风险利率。

字段定义见 `Data/data_dictionary.csv`。字段名必须与字典完全一致；日期采用 `YYYY-MM-DD`，权重和收益率采用小数。

## 执行顺序

```bash
python Code/run_pipeline.py audit --config Code/config.json
python Code/run_pipeline.py backtest --config Code/config.json
python Code/run_experiments.py
```

## 周频单因子组合评价

正式评价必须传入历史成分股文件：

```bash
python Code/run_factor_evaluation.py \
  --market Data/raw/processed_data.csv \
  --constituents Data/raw/constituents.csv \
  --config Code/factor_evaluation_config.json \
  --output Result/factor_reports/basic
```

在历史成分股尚未到位时，只能用开发模式验证工程流程：

```bash
python Code/run_factor_evaluation.py \
  --market Data/raw/processed_data.csv \
  --development-universe \
  --output Result/factor_reports/development
```

开发模式会把每周有行情的股票视为股票池，结果不得写入正式报告。基础版默认选取因子排名最高的20%股票等权持有，信号日在周末前最后一个交易日收盘后形成，下一交易日建仓，并持有至下一次调仓执行日。

无正式数据时可运行：

```bash
python Code/run_pipeline.py demo --config Code/config.json
```

`demo` 使用固定随机种子的合成数据，仅用于验证管线和约束，不得作为作业结果。

## 输出

- `data_audit.csv`：数据覆盖、重复键和权重合计检查。
- `portfolio_weights.csv`：每期策略和基准权重。
- `constraint_diagnostics.csv`：预期跟踪误差、换手率、行业和个股偏离。
- `factor_ic.csv`：滚动因子 IC。
- `daily_returns.csv`：策略和基准日收益。
- `performance_metrics.csv`：核心绩效指标。
- `rolling_tracking_error.csv`：滚动 20 周实现跟踪误差。

`run_experiments.py` 在主回测通过后运行，自动生成 10/20/30bp 交易成本、4%/5%/6% 跟踪误差预算、无 Black-Litterman 及逐类因子剔除实验。

优化器使用确定性的投影梯度方法，并在每期完成后重新检查全部硬约束。任何一期不满足约束都会终止正式回测，不会静默降级。
