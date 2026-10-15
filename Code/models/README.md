# 收益预测模型

统一封装线性回归、正则化模型、LightGBM 与 Black–Litterman 等方法。训练、验证、测试按时间切分；输入为因子矩阵，输出为可追溯的预期收益或相对收益观点。模型文件写入根目录 `models/`；当前选用的三个 LightGBM 年度模型已上传，其余实验模型不上传。

## 训练集因子质量报告

在项目根目录运行 `python Code/build_factor_quality_report.py`。脚本读取本地 `Data/factor_store/alpha158_values` 与 `gtja191_values`，对 2020–2022 年训练集计算 0–1 截面排名、周频 50% 多头加 50% 空头策略，以及逐周 IC、收益、风险和换手。结果写入 `Result/factor_reports/train_2020_2022/`：交互式 HTML 报告、因子汇总 CSV、逐周 CSV 和异常清单 CSV。可通过 `--factor-store`、`--market`、`--output` 覆盖默认路径。

报告仅为训练集内描述性研究。原始行情未复权，当前也没有历史成分股、同期基准和行业数据；请勿把表内收益排名当作样本外选型结论。

## LightGBM 树模型

`Code/run_tree_model.py` 读取 Alpha158 与 GTJA 因子矩阵，按周五所在周的最后实际交易日生成截面信号。每个截面先去除非有限值、做 1%/99% 去极值，再转为 0–1 平均秩；缺失值保留为 NaN，交由 LightGBM 处理。2020–2022 训练、2023 验证、2024 测试，随后逐年扩展训练窗口并推进验证与测试。跨年标签按结束日期 purge。每个折只用其训练期做覆盖率和截面有效性筛选，阈值与候选参数见 `Code/config/tree_model.json`。筛选结果另存，供线性模型组复用相同输入。

两组目标分别为 Huber 回归和 LambdaRank；早停及超参数选择只读取对应折的验证期。外层测试生成 `oos_predictions.parquet`，包含任务说明要求的日期、证券、预测、模型名和折号，并附原始预测、截面排名、标签和模型版本。输出还包括候选参数、每折入选因子、重要性与跨折稳定性、统一成本口径的逐周及逐年评价，以及自动生成的 `model_report.md`。

正式运行需要提供历史成分股文件：

```bash
python Code/run_tree_model.py --constituents Data/raw/constituents.csv
```

当前只有按本地可观察股票构成的研究股票池；可用下面的开发模式跑通管线：

```bash
python Code/run_tree_model.py --development-universe --smoke
python Code/run_tree_model.py --development-universe
python Code/run_tree_model.py --development-universe --feature-policy all_usable
```

`--smoke` 只跑 8 个因子及 2024 年一折，不能用于模型结论。开发模式及其预测、模型文件分别写入忽略 Git 的 `Result/model_reports/tree_development/` 和 `models/tree/development/`。固定股票集合向历史倒推偏离任务说明的正式股票池要求，开发结果须单独标识。

## 探索性调优

`Code/config/tree_model_tuned.json` 增加浅树、较强正则化和特征采样候选。每个候选训练至 120 轮，仅在对应验证年比较第 5、10、20、40、80、120 轮的周度平均 Rank IC，并以最优验证期轮数预测下一年。运行命令：

```bash
python Code/run_tree_model.py --config Code/config/tree_model_tuned.json --development-universe --output Result/model_reports/tree_tuned_exploratory --model-dir models/tree/tuned_exploratory
```

2024–2026 年外层测试结果在这一轮调优前已被查看，因此新结果是探索性复评；不能再把这些年份当成完全未触碰的独立检验集。后续需要新的时间段或新数据做最终确认。

## 收益标签诊断

`python Code/audit_tree_labels.py` 检查未复权周收益的极端值，并在 `Data/raw/prices.csv` 有复权价的 2024 年 9 月以后比较同一执行区间的收益。结果写入 `Result/model_reports/tree_label_audit/`。

`Code/config/tree_model_relative.json` 使用每周个股收益减去当周股票池平均收益作为 Huber 训练标签；`Code/config/tree_model_clipped_relative.json` 先对每周收益做 1%/99% 去极值再减均值。验证和回测仍用未经转换的原始收益，便于与原模型同口径比较；训练标签的转换只依赖该周已完成的收益，不进入信号日特征。两份配置仅用于探索性 Huber 对照，完整的回归与排序两组实验仍见基线配置。

## 线性模型组

`Code/run_linear_model.py` 使用与树模型相同的周频面板、时间切分、标签和统一评价函数，
比较 Ridge、Elastic Net、Lasso 与普通多元线性回归。四个模型使用标准 MSE；Ridge 是基准，
Elastic Net 是主模型，Lasso 和 OLS 是对照。

每个滚动折只使用训练期筛选因子：先检查覆盖率、有效周数和绝对 Rank IC 下限，再综合
训练期 Rank IC、ICIR、方向稳定性以及固定的 2020–2022 单因子成本后结果排名。候选按综合
分数依次进入，并剔除与已入选因子绝对相关系数超过 `maximum_abs_pairwise_correlation` 的
变量。所有阈值和四个模型的参数候选位于 `Code/config/linear_model.json`。

开发模式和正式模式分别运行：

```bash
python Code/run_linear_model.py --development-universe --smoke
python Code/run_linear_model.py --development-universe
python Code/run_linear_model.py --constituents Data/raw/constituents.csv
```

输出目录包含统一格式的 `oos_predictions.parquet`、每折筛选记录、验证参数、因子系数、
系数跨折稳定性、逐周/逐年评价和 Markdown 报告。没有历史成分股时，开发模式结果不能称为
正式中证 A500 样本外结果。
