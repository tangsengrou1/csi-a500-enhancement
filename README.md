# csi-a500-enhancement

中证 A500 周频指数增强课程项目。研究主线是“多因子选股 → 因子筛选与聚合 → Black–Litterman 观点融合 → 带跟踪误差、行业、个股和换手约束的组合优化 → 含交易成本回测”。正式数据由 Wind 终端手工导出，代码不依赖 WindPy。

> 数据边界：本仓库只保存代码、配置、文档模板和合成测试逻辑。Wind 原始数据、清洗数据、股票级因子值、模型文件和正式/演示回测结果均由 `.gitignore` 排除。

## 研究流程

1. 按 `Data/Wind导出清单.md` 导出历史成分、权重、行情、行业、估值、财务和无风险利率。
2. 数据审计与清洗，严格按公告日处理财务数据，避免未来信息。
3. 从开源因子公式和自研因子构建候选库，统一输入输出、频率、方向和缺失值规则。
4. 用滚动 IC/ICIR、覆盖率、相关性、分组收益和换手率筛选因子。
5. 比较线性模型、LightGBM 等聚合方法；所有调参与评估保持时间顺序。
6. 将预测收益直接或经 Black–Litterman 融合后输入组合优化器。
7. 周频回测并检查多头、跟踪误差、行业、个股和换手率约束。
8. 完成基准、等权、多因子、完整策略和稳健性对照，并输出报告与汇报材料。

## 目录说明

| 目录 | 用途 | 数据规则 |
|---|---|---|
| `.github/` | PR/Issue 模板及只使用合成数据的 CI | 可上传 |
| `Code/a500/` | 当前可运行的核心 Python 包 | 可上传 |
| `Code/config/` | 示例配置与分环境配置说明 | 只上传示例 |
| `Code/data_pipeline/` | 数据读取、校验、清洗和 PIT 对齐 | 可上传代码 |
| `Code/factor_library/` | 因子公式实现及来源/许可证记录 | 可上传代码 |
| `Code/factor_pipeline/` | 去极值、标准化、中性化、IC 与筛选 | 可上传代码 |
| `Code/models/` | 线性模型、LightGBM、BL 等预测接口 | 模型文件不上传 |
| `Code/portfolio/` | 约束优化、交易规则和可成交性处理 | 可上传代码 |
| `Code/backtest/` | 调仓、费用、持仓演进和回测编排 | 可上传代码 |
| `Code/reporting/` | 绩效指标、图表和结果表生成 | 可上传代码 |
| `Code/tests/` | 单元测试与合成数据集成测试 | 可上传 |
| `Data/raw/` | Wind 原始导出，禁止修改 | 不上传数据 |
| `Data/processed/` | 清洗后的研究数据 | 不上传数据 |
| `Data/factor_store/` | 股票级因子值和缓存 | 不上传数据 |
| `Data/metadata/` | 字段、查询和 PIT 规则说明 | 可上传 |
| `Data/sample/` | 固定种子合成数据说明 | 可上传 |
| `Result/demo/` | 合成数据运行输出 | 不上传输出 |
| `Result/official/` | Wind 正式回测输出 | 不上传输出 |
| `Result/*` 其他目录 | 可发布的聚合研究说明与正式图表 | 提交前复核 |
| `Report/` | Word 模板和 Markdown 报告底稿 | 可上传 |
| `Presentation/` | PPT 模板和汇报结构 | 可上传 |

当前实现集中在 `Code/a500/`，新增目录是统一协作边界。新模块按上述目录开发，成熟后再由 PR 完成接口迁移，避免多人同时修改同一文件。

## 环境安装

建议 Python 3.10 以上版本：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r Code/requirements-dev.txt
```

## Wind 数据准备

1. 阅读 `Data/Wind导出清单.md` 和 `Data/data_dictionary.csv`。
2. 将原始 CSV/XLSX 放入 `Data/raw/`，不要改值、改列或覆盖原文件。
3. 在 `Data/query_log.csv` 记录字段代码、参数、日期范围、导出日期和操作人。
4. 保留历史成分和权重，禁止用当前成分回填历史；财务信息最早在公告日后的下一交易日使用。

真实数据放入仓库前先运行 `git check-ignore -v 文件路径`；若未命中忽略规则，不得提交。

## 合成数据测试

`Code/a500/synthetic.py` 使用固定随机种子在内存生成完全合成的数据包，不含真实股票记录：

```bash
pytest Code/tests -q
python Code/run_pipeline.py demo --config Code/config.json
```

演示输出位于 `Result/demo/`，只验证工程管线和约束，不能进入课程结论。

## 正式回测顺序

```bash
python Code/run_pipeline.py audit --config Code/config.json
python Code/run_pipeline.py backtest --config Code/config.json
python Code/run_experiments.py
```

正式输出进入 `Result/official/`。优化失败必须报错并保留诊断，不得静默切换到无约束组合。

## GitHub 协作流程

1. 从最新 `main` 创建 `feature/任务名称` 分支，不建立按成员命名的长期分支。
2. 一个 PR 只解决一个明确问题，并填写输入输出、字段、防前视处理和测试结果。
3. 推送前运行合成数据测试，确认 `git status` 不含真实数据或缓存。
4. 每个 PR 至少由一名非作者审查；检查通过后合并并删除功能分支。
5. `main` 只保存已审查且可复现的版本，禁止直接在 `main` 上开发。

详细规则见 `CONTRIBUTING.md`。本课程私有项目暂不附开源许可证。
