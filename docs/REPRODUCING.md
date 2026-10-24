# 复现指南

[返回首页](../README.md) · [研究方法](RESEARCH_WORKFLOW.md) · [结果导航](RESULTS.md)

所有命令在仓库根目录运行。原始数据需要自行取得授权；下载源码不代表具备完整研究数据。

## 1 安装与合成演示

建议 Python 3.10 及以上：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r Code/requirements-dev.txt
python -m pytest Code/tests -q
python Code/run_pipeline.py demo --config Code/config.json
```

输出 `Result/demo/` 包含权重、收益、绩效和约束诊断。该步骤不读取 Wind 或外部因子，是检查环境和基础组合管线的最短路径。测试和演示通过不代表真实数据准备、历史成分或产品研究已经通过验证。

## 2 选择需要复现的路径

| 路径 | 必备输入 | 主入口 |
| --- | --- | --- |
| 五个基础因子评价 | 含收盘价及相关量价字段的 CSV/XLSX；正式模式还需历史成分 | `run_factor_evaluation.py` |
| 344 因子训练期报告 | 行情文件与两套现成因子矩阵 | `build_factor_quality_report.py` |
| 线性或树模型 | `processed_data.parquet`、两套因子矩阵；正式模式还需历史成分 | `run_linear_model.py` / `run_tree_model.py` |
| 基础多因子组合回测 | `prices`、`benchmark`、`constituents`、`industry`、`valuation`、`fundamentals`、`risk_free` 七表 | `run_pipeline.py` |

每个脚本的完整参数可通过 `python Code/脚本名.py --help` 查看。`run_experiments.py` 会立即读取数据并运行实验，不是带 `--help` 的 CLI。

## 3 准备模型研究输入

```text
Data/raw/processed_data.parquet
    securityID / trade_dt / close / amt
Data/factor_store/alpha158_values/<factor>.parquet
Data/factor_store/gtja191_values/<factor>.parquet
    因子矩阵：日期索引 × 证券列
```

历史成分 CSV/parquet 支持日期列 `date` 或 `effective_date`，证券列 `wind_code` 或 `securityID`；每个日期代表有效成分快照，必须覆盖训练期起点。代码取信号日之前最近的快照。完整性与证券编码须自行核验。

因子公式的外部计算环境并未在当前 Python 工程中完整封装。没有矩阵时，不能仅靠模型脚本重新生成全部 344 个因子。

## 4 因子质量报告

已有输入时运行：

```bash
python Code/build_factor_quality_report.py
```

输出位于 `Result/factor_reports/train_2020_2022/`。请先阅读其中 README，理解训练期和多空权重口径。

五个基础因子是另一条入口，开发验证示例：

```bash
python Code/run_factor_evaluation.py \
  --market Data/raw/processed_data.csv \
  --development-universe \
  --output Result/factor_reports/development
```

CSV 须满足该评价模块的字段要求，不能只改 parquet 扩展名。正式模式改为提供 `--constituents Data/raw/constituents.csv`，不传开发开关。

## 5 线性与树模型

先用少量特征和一折检验输入接口：

```bash
python Code/run_linear_model.py --development-universe --smoke
python Code/run_tree_model.py --development-universe --smoke
```

开发股票池的完整基线实验：

```bash
python Code/run_linear_model.py --development-universe
python Code/run_tree_model.py --development-universe
```

重跑目前暂定的树模型标签方案：

```bash
python Code/run_tree_model.py \
  --config Code/config/tree_model_clipped_relative.json \
  --development-universe \
  --output Result/model_reports/tree_clipped_relative_exploratory \
  --model-dir models/tree/clipped_relative_exploratory
```

上面的显式输出路径可能覆盖同名实验文件。需要保留原实验时，把 `--output`、`--model-dir` 改为新的目录；不要只替换配置而复用旧结果名称。

准备好历史成分后，正式模式的入口为：

```bash
python Code/run_linear_model.py --constituents Data/raw/constituents.csv
python Code/run_tree_model.py --constituents Data/raw/constituents.csv
```

两种模式不能同时指定。命令称为正式模式，只表示代码要求提供历史成分，不自动保证数据无误或独立检验成立。

## 6 查看输出

从 `model_report.md` 开始，然后读 `evaluation_summary.csv`、`yearly_evaluation.csv`、`fold_models.csv`、`run_config.json` 与 `run_manifest.json`。线性模型另看系数和稳定性，树模型另看特征重要性和稳定性。

逐股票预测 `oos_predictions.parquet` 含信号日、执行日、证券、预测和折号；融合前需核对模型版本、年度与共同样本。GitHub 上的模型文件不等于完整复现包，还需要相同因子与预处理。

## 7 最终产品回测

最终包产品已并入 `Code/product/`。其输入布局不同于前面的模型研究命令，按[产品流程](PRODUCT_PIPELINE.md)准备 `Data/product/`，然后执行：

```bash
python -m pip install -r Code/requirements-product.txt
python Code/product/run.py --check-inputs
python Code/product/run.py
```

默认使用归档预测重新优化和回测；`--train-linear`、`--train-tree` 可以先重新训练。结果写入 `Result/reproduced/`，冻结参照在 `Result/reference/`。

## 8 基础组合管线

七表字段见 [`data_dictionary.csv`](../Data/data_dictionary.csv) 与 [`io.py`](../Code/a500/io.py)。每类表在 `Data/raw/` 中恰好有一个 CSV/XLSX/XLSM 文件，日期和权重字段按定义提供。

```bash
python Code/run_pipeline.py audit --config Code/config.json
python Code/run_pipeline.py backtest --config Code/config.json
python Code/run_experiments.py
```

审计输出在 `Data/processed/`，基础回测和稳健性输出在 `Result/official/`。约束失败会终止回测，不静默切换为无约束组合。该路径不加载两组模型预测，不能用于重现双模型融合产品。

## 常见问题

| 现象 | 检查项 |
| --- | --- |
| 提示必须传 `--constituents` | 正式模式需历史成分；仅工程调试可显式使用开发模式 |
| 找不到因子或没有通过质量筛选的因子 | 检查 parquet 路径、日期索引、证券列和训练期覆盖 |
| 只能找到年度模型，无法生成同样预测 | 还需要每折因子名单、预处理、配置和最佳轮数 |
| 七表模式报缺表 | 不能拿 `processed_data.parquet` 替代完整 `DataBundle` |
| 数值与报告不一致 | 先比较股票池、复权、信号/执行日、标签、年度、费用和持仓口径 |
| CI 数据边界检查失败 | 已跟踪数据可能违反现有检查；`.gitignore` 不会从索引中移除它们 |
