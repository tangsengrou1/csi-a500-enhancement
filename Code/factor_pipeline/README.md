# 因子处理与筛选

负责覆盖率检查、缺失值处理、去极值、标准化、方向统一、周频单因子组合评价及后续的相关性和IC检验。所有统计只能使用当时已知的信息。

当前基础实现位于：

- `a500/factor_registry.py`：统一注册内置、开源库和自研因子；
- `a500/factor_evaluation.py`：每周计算、成分股过滤、仓位映射、持有期收益和绩效评价；
- `run_factor_evaluation.py`：命令行入口；
- `factor_evaluation_config.json`：仓位映射、费用和因子列表。

基础版默认将每周因子排名最高的20%股票等权持有。正式评价必须提供历史成分股文件；`--development-universe` 只允许用于调试。
