# 固定50/50双模型融合回测

先读[融合产品组合优化与回测报告](融合产品组合优化与回测报告.md)。

在A500目录运行：

```powershell
python final_fusion/run_pipeline.py
```

依赖：pandas、numpy、pyarrow、scipy、cvxpy、OSQP、matplotlib、openpyxl。
沿用原项目脚本中的本地价格、指数及行业数据绝对路径。

流程：两模型排名分各50% → 重新优化全部六组合 → 根据新权重重算收益与换手 → 扣交易成本与管理费 → 三模型对照及独立校验。

主要文件：

- `融合产品组合优化与回测报告.md`：设计、参数、结果、比较与限制。
- `run_pipeline.py`：一键重跑；会覆盖本目录生成的脚本快照及结果。
- `evaluate_fusion.py`：同窗口汇总、修正年度统计、持仓及扣费独立核验。
- `render_all_artifacts.py`：参照原目录完整重绘22张对应图表，生成完整报告。
- `图表清单.md`、`chart_inventory.csv`：与原目录的图表逐一对应清单。
- `predictions_fusion.parquet`：融合预测；`fusion_signal_audit.parquet`保留两侧原始分数。
- `portfolio_weights_v*_fusion.parquet`：重新优化的持仓权重。
- `backtest_weekly_fusion.csv`、`backtest_nav_fusion.csv`：收益、换手及净值。
- `comparison_metrics.csv`：正式三模型对照，换手统一包含首期建仓。
- `yearly_metrics_same_window.csv`、`monthly_excess.csv`：分年度及分月结果。
- `validation_results.json`、`run_manifest.json`：校验及输入/源码哈希。

完整流程结束时，`backtest_metrics_fusion.csv`的换手已统一为包含首期建仓的定义，与`comparison_metrics.csv`一致。
年度表和同业指数均按产品同一周区间计算；基金对比图保留原数据重复导出的待复核说明。
仅重绘图表及报告可运行：`python final_fusion/render_all_artifacts.py`。
原始`final`和`final_tree`不被修改。
