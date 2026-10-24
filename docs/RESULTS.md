# 结果导航与评价口径

[返回首页](../README.md) · [研究方法](RESEARCH_WORKFLOW.md) · [产品复现](PRODUCT_PIPELINE.md)

先分清在读哪一层结果，再比较数字。文件夹中的 `development`、`smoke`、`exploratory` 都有实际含义，不应在报告中省略。

## 推荐阅读顺序

1. [训练期因子质量报告说明](../Result/factor_reports/train_2020_2022/README.md)：理解 344 个因子的覆盖、IC、收益和换手。这是训练集描述统计。
2. [线性模型基线报告](../Result/model_reports/linear_development/model_report.md)：比较 Ridge、Elastic Net、Lasso、OLS。
3. [树模型标签审计](../Result/model_reports/tree_label_audit/label_experiment_report.md)：理解为什么比较原始、相对和去极值收益标签。
4. [暂定树模型选择](../Result/model_reports/MODEL_SELECTION.md)：查看对应模型、配置和轮数，不将暂定选择理解为收益风险全面占优。
5. [最终融合产品报告](../Result/reference/final_fusion/融合产品组合优化与回测报告.md)：看三套信号进入共同组合框架后的结果。
6. [最终正式报告 PDF](../Report/天枢中证A500指数增强基金.pdf)：查看课程交付的完整叙述；代码入口以当前复现指南为准。

## 各目录代表什么

| 位置 | 内容 | 阅读时注意 |
| --- | --- | --- |
| `Result/factor_reports/train_2020_2022/` | 训练期单因子统计与 HTML 报告 | 不能作为独立样本外选型证据 |
| `Result/model_reports/linear_development/` | 线性组默认配置的实验 | 不等于最终产品使用的 Corr 0.50 Ridge 版本 |
| `Result/model_reports/linear_development_*/` | 不同筛选、相关阈值和参数网格的对照 | 每次比较先核对 `run_config.json` |
| `Result/model_reports/tree_tuned_exploratory/` | 原始标签下的调优 Huber 与 LambdaRank | 已有测试反馈后的探索实验 |
| `Result/model_reports/tree_relative_exploratory/` | 相对收益标签对照 | 与去极值版本的收益、回撤和 IC 不同 |
| `Result/model_reports/tree_clipped_relative_exploratory/` | 去极值相对收益标签对照 | 141 周评价，尚无新增独立窗口 |
| `Result/reference/final/` | 最终线性信号产品的冻结汇总、方法说明及参考图表 | 数值来自最终包，非本次重新训练 |
| `Result/reference/final_tree/` | 最终树模型信号产品的冻结汇总 | 同上 |
| `Result/reference/final_fusion/` | 最终融合产品的冻结汇总及对比 | 133 个共同持仓块；与单模型诊断收益不同 |
| `Result/reproduced/` | 当前机器重新运行产品流程得到的结果 | 本地输出；先看校验 JSON 和优化日志 |
| `Result/demo/` | 基础管线合成结果 | 不用于真实策略结论 |
| `Result/official/` | 基础七表管线的输出位置 | 目录存在不代表当前完整正式数据已经齐备 |

## 模型报告中的文件怎样读

| 文件 | 回答的问题 |
| --- | --- |
| `model_report.md` | 这次实验比较了什么，主结果与限制是什么？ |
| `run_config.json` | 具体采用哪些因子筛选、标签和参数候选？ |
| `run_manifest.json` | 来源代码、输入、随机种子和运行模式是什么？历史清单可能保留原机器路径，不作为运行依赖 |
| `fold_models.csv` | 每个测试年份选了哪个候选、多少因子及多少轮？ |
| `feature_screen.csv` | 因子在哪一折、因为什么原因被保留或剔除？ |
| `validation_candidates.csv` | 参数根据哪个验证表现选定？ |
| `yearly_evaluation.csv` / `weekly_evaluation.csv` | 平均结果是否掩盖年度和周度波动？ |
| `feature_importance_stability.csv` | 树模型的重要性跨年度是否稳定？不代表因果贡献 |
| `coefficient_stability.csv` | 线性模型系数方向和大小跨折是否稳定？ |

## 三组不能混用的数字

- **141 周与 133 块**：前者属于预测评价，后者属于最终产品共同持仓区间。
- **20bp 与 15bp**：因子/模型诊断配置通常为 20bp；最终产品为 15bp 主动交易成本，另扣产品管理费。
- **复合超额与 IR**：复合超额根据产品与基准净值比计算；IR 使用算术主动收益均值除以主动收益波动。不能直接把复合年化超额除以 TE 当作报告 IR。

报告中的 52 块年化与按实际日历时长年化也不是同一口径。比对两个数字前，至少核对样本、股票池、执行日、持仓结构、费用、基准和年化方式。
