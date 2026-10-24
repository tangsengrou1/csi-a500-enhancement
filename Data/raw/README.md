# 原研究数据接口

本目录用于原模型研究行情和基础管线的标准表。最终小组产品使用独立的 `Data/product/raw/`，不要混用两套数据目录。

- 模型研究行情：`processed_data.parquet`，字段为 `securityID`、`trade_dt`、`close`、`amt`；配套因子在 `Data/factor_store/`。
- 基础管线：`prices`、`benchmark`、`constituents`、`industry`、`valuation`、`fundamentals`、`risk_free` 七类 CSV/XLSX/XLSM；字段见 [data_dictionary.csv](../data_dictionary.csv)。
- 导出字段和时间要求见 [Wind 导出清单](../Wind导出清单.md)。

历史成分、公告日期、复权方式和证券编码需独立核验。目录中存在某个文件不等于完整历史研究数据已经就绪。当前 Python 工程不提供完整的 Wind 导出与全部 344 因子计算器。

数据公开授权与代码许可分别处理；`.gitignore` 不会移除已跟踪文件或 Git 历史。
