# 代码地图

[项目首页](../README.md) · [研究方法](../docs/RESEARCH_WORKFLOW.md) · [复现指南](../docs/REPRODUCING.md) · [最终产品流程](../docs/PRODUCT_PIPELINE.md)

## 三个执行层次

| 层次 | 入口 | 用途 |
| --- | --- | --- |
| 基础工程演示 | `run_pipeline.py demo` | 无真实数据也能验证四类风格因子、BL、硬约束优化与回测 |
| 因子和模型研究 | `run_factor_evaluation.py`、`run_linear_model.py`、`run_tree_model.py` | 单独评价因子和预测模型，保存每折配置及诊断 |
| 最终产品研究 | `product/run.py` | 读取两模型预测，生成三套信号、18 个组合，重算成本后产品收益并校验 |

这三层保留不同输入和费用口径；不要仅按入口名中的 pipeline 或 backtest 判断是否能复现最终报告。

## 原研究核心包 a500

| 文件 | 责任 |
| --- | --- |
| `io.py` | 七张标准表读取、日期转换与基础审计 |
| `synthetic.py` | 固定种子合成 `DataBundle` |
| `factor_registry.py` | 五个基础因子的定义、字段需求及注册接口 |
| `factor_evaluation.py` | 周频 IC、相关性和多种组合映射评价 |
| `factors.py` | 四类风格因子、行业内标准化和 ICIR 权重 |
| `tree_model.py` | 周频样本、时间切分、树模型训练及共享预测评价 |
| `linear_model.py` | 训练期综合筛选、去相关、线性模型拟合与稳定性 |
| `black_litterman.py` | 基准权重先验与逐股观点融合 |
| `optimizer.py` | 投影优化及 TE、行业、个股、换手检查 |
| `pipeline.py` | 基础四风格多因子回测编排，不读取两组模型预测 |
| `metrics.py` | 基础绩效与滚动跟踪误差 |

## 最终产品模块 product

按下列顺序阅读即可追踪完整产品过程：

1. `run.py`：执行顺序、重训开关与校验。
2. `paths.py`：本地数据与输出路径。
3. `signals.py`：周预测到持仓块映射、两侧覆盖核验、固定 50/50 平均。
4. `portfolio_basic.py`、`portfolio_mv.py`、`portfolio_bl.py`：三套信号共用组合方法。
5. `backtest.py`：持仓收益、权重漂移、换手、80/20 产品及费用。
6. `evaluation.py`：三模型共同窗口与持仓独立核验。
7. `verify_reproduction.py`：输入预检、费用关系与冻结收益差异记录。
8. `visualization.py`、`charts/`：报告、净值、年度、成本、同业及行业图表。

`product/feature_engineering.py`、`factor_screening.py`、`tree_model.py`、`a500/linear_model.py` 是最终包的模型快照，保留其独立配置与导入环境。`product/a500/tree_model.py` 是该快照内部的兼容桥，不替换顶层 `a500/tree_model.py`。

## 配置与输出

原研究配置位于 `Code/config/`，最终产品配置位于 `Code/product/config/`。不要混用同名配置：产品 Ridge 使用最终来源的 0.50 去相关阈值，原默认线性实验为 0.70。

- 原模型实验：`Result/model_reports/`，模型文件为 `models/`。
- 基础组合演示与真实数据模式：`Result/demo/`、`Result/official/`。
- 最终产品重算：`Result/reproduced/`；只读参考为 `Result/reference/`。

## 依赖与验证

```bash
python -m pip install -r Code/requirements-dev.txt
python -m pytest Code/tests -q
```

最终产品另需 `Code/requirements-product.txt` 中的 Matplotlib、SciPy、CVXPY 与 OSQP。图表需要系统可用的中文字体；没有中文字体不影响收益计算，但会影响中文标签。

`data_pipeline/`、`factor_library/`、`models/`、`portfolio/`、`backtest/`、`reporting/` 等说明目录是协作边界，具体实现以本页代码地图为准。
