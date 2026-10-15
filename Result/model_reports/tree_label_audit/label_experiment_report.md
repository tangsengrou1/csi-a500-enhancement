# 周收益标签审计与 Huber 对照

## 数据审计

模型行情文件覆盖 2020–2026 年，只有未复权收盘价。另一个 `prices.csv` 的复权价只覆盖 2024-09-02 至 2026-10-09，不能覆盖初始训练期。167,845 个有效周收益标签中，812 个绝对收益超过 30%。在 54,000 个可比较的原始价与复权价周收益中，78 个相差超过 5 个百分点；最大的差异为 63.4 个百分点。逐笔清单见 `extreme_raw_returns.csv` 和 `large_adjustment_gaps.csv`。

复权价重叠期的排序核查（108 周、54,000 个股票周）显示，调优 Huber 的平均 Rank IC 按原始价与复权价分别为 0.01029、0.01025；相对收益版为 0.03534、0.03385；去极值相对收益版为 0.04211、0.04076。公司行为导致部分收益异常，但在可比较时期未改变这三组模型排序表现的方向。复权价不足以评价 2020–2024 年 8 月的标签。

## 标签实验

三组模型使用相同股票池、因子质量筛选、LightGBM 候选参数和验证期轮数选择。只有 Huber 的训练标签不同；验证 Rank IC 和回测收益始终使用原始周收益。

| 训练标签 | 平均 Rank IC | Rank ICIR | 正 IC 周比例 | 成本后年化收益 | 最大回撤 | 平均单边换手 |
|---|---:|---:|---:|---:|---:|---:|
| 原始周收益 | 0.0142 | 0.100 | 57.3% | +1.6% | −12.9% | 46.7% |
| 当周减股票池平均收益 | 0.0248 | 0.143 | 54.6% | +8.2% | −9.9% | 53.3% |
| 每周 1%/99% 去极值后减均值 | 0.0303 | 0.173 | 57.4% | +7.8% | −15.5% | 55.5% |

| 测试年 | 原始标签 Rank IC / 成本后收益 | 相对标签 Rank IC / 成本后收益 | 去极值相对标签 Rank IC / 成本后收益 |
|---|---:|---:|---:|
| 2024 | 0.0285 / +8.7% | 0.0196 / +12.3% | 0.0249 / +13.7% |
| 2025 | 0.0024 / −3.5% | 0.0321 / +6.7% | 0.0351 / +5.9% |
| 2026（部分年度） | −0.0038 / −0.6% | 0.0218 / +3.4% | 0.0310 / +1.8% |

## 判断与复现

相对收益标签带来更均衡的跨年排序结果。去极值进一步提升 Rank IC，但收益、回撤和换手并非同时改善。2024–2026 年测试结果在这些实验前已经被查看，因此这是一组探索性复评，不能据此宣称已完成独立样本外验证，也不能仅凭这组结果选定最终标签。完整的回归与排序模型实验仍由基线及调优配置保留。

复现命令：

```bash
python Code/audit_tree_labels.py
python Code/run_tree_model.py --config Code/config/tree_model_relative.json --development-universe --output Result/model_reports/tree_relative_exploratory --model-dir models/tree/relative_exploratory
python Code/run_tree_model.py --config Code/config/tree_model_clipped_relative.json --development-universe --output Result/model_reports/tree_clipped_relative_exploratory --model-dir models/tree/clipped_relative_exploratory
```
