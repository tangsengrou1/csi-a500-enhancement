# 协作与数据保密规范

## 分支与提交

- 从最新 `main` 创建 `feature/简短任务名`、`fix/简短问题名` 或 `docs/简短主题`。
- 不使用按成员命名的长期分支，不直接向 `main` 开发。
- 提交应小而完整，建议使用 `feat:`、`fix:`、`test:`、`docs:`、`refactor:` 前缀。
- 一个 Pull Request 只解决一个问题；合并后删除功能分支。

## Pull Request 检查

- 说明修改目的、输入、输出和受影响模块。
- 涉及数据时列明字段、频率、时间口径、缺失处理和防前视规则。
- 涉及因子时注明公式、来源、许可证、方向、窗口和可用日期。
- 附合成数据测试结果；每个 PR 至少由一名非作者审查。
- 禁止为通过测试而静默放宽组合约束或替换优化结果。

## 数据保密

- 不提交 Wind CSV/XLSX、清洗数据、股票级因子值、持仓明细、回测缓存或模型文件。
- 不提交账号、密码、Token、Cookie、`.env`、本机绝对路径或个人隐私信息。
- 只允许提交固定种子生成的完全合成数据或其生成器。
- 提交前执行 `git status --short`、`git diff --cached`，并用 `git check-ignore -v` 检查任一数据文件。
- 若敏感数据已进入提交历史，立即停止推送并通知全组，不要只删除工作区文件。

## 最低验证

```bash
pytest Code/tests -q
python Code/run_pipeline.py demo --config Code/config.json
```

CI 只访问仓库内代码和合成数据，不配置 Wind 凭据或上传正式结果。
