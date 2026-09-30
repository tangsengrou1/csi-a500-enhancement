# Wind 手工导出清单

## 导出原则

- 每张表导出为独立 CSV 或 XLSX，文件名使用 `prices`、`benchmark`、`constituents`、`industry`、`valuation`、`fundamentals`、`risk_free`。
- 保留 Wind 原始导出文件，不在原文件内删除行、替换空值或更改数值。
- 在 `query_log.csv` 记录 Wind 字段代码、参数、时间范围、导出时间和操作人，并将查询设置截图放入 `query_screenshots`。
- 股票数据至少覆盖正式回测开始日前 250 个交易日。
- 成分和权重必须使用历史时点数据，不能用最新成分回填。

## 终端查询内容

| 文件 | 内容 | 关键口径 |
|---|---|---|
| benchmark | 中证 A500 价格指数、全收益指数日收盘 | 日频，不复权 |
| constituents | 历史成分及权重 | 每个周度信号日或最近生效日 |
| prices | 收盘、前复权收盘、成交额、交易状态、涨跌停 | 日频，全体历史成分 |
| industry | 申万一级行业 | 使用历史分类与生效日期 |
| valuation | PE TTM、PB LF、PS TTM、股息率 | 周频或日频 |
| fundamentals | ROE、毛利率、经营现金流质量、资产负债率 | 同时导出报告期与公告日 |
| risk_free | 一年期国债或中债收益率 | 日频或按交易日向前填充 |

导出后先运行数据审计。审计失败时修复查询或重新导出，不直接修改原始数值。

