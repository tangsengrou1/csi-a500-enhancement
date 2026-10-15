# 当前选用的 LightGBM 因子聚合模型

## 选择结论

后续因子聚合研究**暂定使用 LightGBM Huber 回归 + 逐周 1%/99% 去极值后的截面相对收益标签**，对应配置为 [`Code/config/tree_model_clipped_relative.json`](../../Code/config/tree_model_clipped_relative.json)。训练标签是每只股票下一持有周的未复权收益，先在该周截面做 1%/99% 去极值，再减去股票池当周平均收益。验证 Rank IC 与策略回测仍按未经转换的个股原始收益计算。输入因子在每个信号日做截面去极值和平均秩映射；每折仅用训练期筛选因子。

选择依据是统一任务说明把周度 Rank IC 和跨年稳定性列为主指标：此版本在 2024、2025 和 2026 年的 Rank IC 分别为 0.0249、0.0351、0.0310，合并平均为 0.0303；141 个测试周的成本后年化收益约 7.8%。[普通截面相对收益版](tree_relative_exploratory/model_report.md)的平均 Rank IC 为 0.0248，成本后年化收益约 8.2%，最大回撤约 −9.9%，优于选用版的 −15.5%。因此，本次选择优先考虑排序预测能力，**并不表示选用版在收益和风险上全面占优**。LambdaRank 未显示稳定正向 Rank IC，暂不作为后续主模型。

2024–2026 年测试结果在标签调优前已被查看，2026 年只有部分年度数据；当前选择属于**项目研究阶段的暂定版本**，尚无新的独立样本外验证。固定股票池向历史回看、未复权价格和 20 bp 单边换手成本等口径见[标签实验报告](tree_label_audit/label_experiment_report.md)。

## 从哪个文件夹调用

| 用途 | 本地路径 | 说明 |
|---|---|---|
| 读取已有历史预测 | `Result/model_reports/tree_clipped_relative_exploratory/oos_predictions.parquet` | 本地保留，含 2024–2026 年逐股票预测；使用 `signal_date`、`execution_date`、`wind_code`、`prediction_rank`、`fold_id`。后续组合使用逐周 0–1 的 `prediction_rank`；`prediction` 是模型原始分数，不应直接解释为绝对预期收益。 |
| 加载已训练模型 | `models/tree/clipped_relative_exploratory/` | 本地保留，按测试年分别有 `..._2024.txt`、`..._2025.txt`、`..._2026.txt`。读取对应年份模型，并使用下面 `fold_models.csv` 中的 `best_iteration`。 |
| 查看模型与入选因子 | [`tree_clipped_relative_exploratory/`](tree_clipped_relative_exploratory/) | `fold_models.csv` 给出每折所选轮数和候选；`feature_screen.csv` 给出每折入选因子；`model_report.md` 与评价 CSV 可在 GitHub 直接浏览。 |
| 重新生成 | [`Code/run_tree_model.py`](../../Code/run_tree_model.py) 与上述配置 | 需要本地原始行情和 `Data/factor_store/`。 |

本次模型的 `model_id` 为 `lightgbm_huber_quality_screen_development_6050f4d3`。三个模型文件分别是：

| 预测年份 | 模型文件名 | 使用轮数 |
|---|---|---:|
| 2024 | `lightgbm_huber_quality_screen_development_6050f4d3_2024.txt` | 120 |
| 2025 | `lightgbm_huber_quality_screen_development_6050f4d3_2025.txt` | 120 |
| 2026 | `lightgbm_huber_quality_screen_development_6050f4d3_2026.txt` | 20 |

`models/`、股票级预测 parquet、原始行情和因子 parquet 均被 Git 忽略，因此 **GitHub 上的报告目录不能直接加载模型做推理**。本地模型和预测可直接调用；换一台机器时，先准备本地数据，再在项目根目录运行：

```bash
python Code/run_tree_model.py \
  --config Code/config/tree_model_clipped_relative.json \
  --development-universe \
  --output Result/model_reports/tree_clipped_relative_exploratory \
  --model-dir models/tree/clipped_relative_exploratory
```

2024、2025、2026 年文件是各自滚动折的历史预测模型，不能把一个年度模型当作所有时期的统一模型。若预测新的年度，需按相同时间切分规则重新训练和验证，并保存新折的因子名单与最佳轮数。
