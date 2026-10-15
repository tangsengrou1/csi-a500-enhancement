# LightGBM 因子聚合实验结果

报告和汇总表已作为普通文件放在下列目录，可直接在 GitHub 浏览：

- `tree_tuned_exploratory/`：调优版原始收益标签的 Huber 与 LambdaRank 结果及对照。
- `tree_relative_exploratory/`：截面相对收益标签的 Huber 结果。
- `tree_clipped_relative_exploratory/`：去极值截面相对收益标签的 Huber 结果。
- `tree_label_audit/`：标签审计摘要与三组标签实验报告。

各实验目录包含汇总、分年、逐周、验证候选、因子筛选、重要性、配置和运行记录。训练代码在 `Code/`；[当前选用模型](../../models/tree/clipped_relative_exploratory/)的三个年度文本文件也已上传。其他实验模型、股票级 `oos_predictions.parquet`、复权价逐笔对照、原始行情和因子 parquet 保留在本地。完整复现需要本地的 `Data/raw/processed_data.parquet`、`Data/raw/prices.csv` 与 `Data/factor_store/`。

主要结论和口径见 `tree_label_audit/label_experiment_report.md`。2024–2026 年测试结果在本轮标签实验前已被查看，因此结果属于探索性复评，不是新的独立样本外验证。
