# Wind 原始数据（仅本地）

- `wind_exports/`：从 Wind 终端直接导出的原始 CSV/XLSX（中文列名即可），不得修改，不得提交到 Git。导出操作见 `Data/Wind导出操作步骤.md`。
- 本目录根下的 `prices.csv` 等 7 张标准表由 `Code/data_pipeline/wind_export_to_bundle.py` 生成（可随时从原始导出重建），同样不上传。字段要求见 `data_dictionary.csv`。

## 当前进度（2026-10-09）

已就绪(仅本地——仓库 CI 强制要求标准表不入 git,组员各自本地生成):
- `benchmark.csv` 506 行、`risk_free.csv` 6183 行;
- `prices.csv` 253000 行 = 500 只股票 × 2024-09-02 ~ 2026-10-09(由 中证A500.xlsx 行情底表 + 前复权小表合并生成,2024-09 前数据已剔除);
- `valuation.csv` 252930 行、500 只股票(股息率已从 % 转小数;解析器曾漏掉每块首只股票,已修复后重生成)。

未就绪:
- `fundamentals.csv`: 尚未生成。Wind 导出中未找到"公告日期"(ann_dt)指标,仅有"报告期";转换脚本已支持用报告期按法定披露截止日近似公告日,确认后即可转换;
- `constituents.csv`、`industry.csv`: 尚未导出,未处理。

重导清单见 `Data/Wind导出操作步骤.md`。
