# LightGBM 因子聚合实验包

`lightgbm_exploratory_bundle.zip` 收录本轮 LightGBM 训练代码、配置、测试、标签审计与实验报告，以及四组实验的汇总、分年、逐周、验证候选、因子筛选和重要性结果。四组实验是调优版原始标签（Huber 与 LambdaRank）、普通截面相对收益、去极值截面相对收益，以及标签审计。

压缩包不包含原始行情、因子 parquet、股票级 `oos_predictions.parquet`、复权价逐笔对照或训练好的模型文件；这些文件可能包含或派生出股票级原始数据，并保留在本地。仓库中的代码和配置记录了复现流程，运行时需要本地的 `Data/raw/processed_data.parquet`、`Data/raw/prices.csv` 与 `Data/factor_store/`。

主要结论及完整口径见包内 `Result/model_reports/tree_label_audit/label_experiment_report.md`。2024–2026 年测试结果在本轮标签实验前已被查看，结果属于探索性复评，不是新的独立样本外验证。
