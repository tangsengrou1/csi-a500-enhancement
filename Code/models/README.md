# 收益预测模型

统一封装线性回归、正则化模型、LightGBM 与 Black–Litterman 等方法。训练、验证、测试按时间切分；输入为因子矩阵，输出为可追溯的预期收益或相对收益观点。二进制模型写入根目录 `models/`，不上传。

## 训练集因子质量报告

在项目根目录运行 `python Code/build_factor_quality_report.py`。脚本读取本地 `Data/factor_store/alpha158_values` 与 `gtja191_values`，对 2020–2022 年训练集计算 0–1 截面排名、周频 50% 多头加 50% 空头策略，以及逐周 IC、收益、风险和换手。结果写入 `Result/factor_reports/train_2020_2022/`：交互式 HTML 报告、因子汇总 CSV、逐周 CSV 和异常清单 CSV。可通过 `--factor-store`、`--market`、`--output` 覆盖默认路径。

报告仅为训练集内描述性研究。原始行情未复权，当前也没有历史成分股、同期基准和行业数据；请勿把表内收益排名当作样本外选型结论。
