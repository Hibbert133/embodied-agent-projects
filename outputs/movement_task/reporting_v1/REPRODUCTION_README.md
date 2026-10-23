# 完整结果的复核顺序

本说明对应 `movement_task_20261019T191708Z_eee0803df5bf`，冻结源码提交为
`eee0803df5bf5c2ce6908912bc77522bbd06a1c9`。当前文件只说明复核方法；
各阶段是否完成应检查该阶段的成功回执，不能根据本说明的存在推定成功。

本研究有 54 个独立组、1,296 次实际执行。重复读取同一批记录或重新计算
统计不产生新的独立样本，也不是外部研究者的独立确认实验。

## 源码和运行库

使用冻结提交对应的源码及其绑定的 Windows 运行库。原配置与模型依赖
均由 `manifest.json` 的 1,201 个输入哈希及运行库哈希约束。后续提交
可能修改这些输入；不能仅凭文件名或包版本相同就认为通过了复核要求。
结果工件可以从保存结果的提交取出，放回对应的源码副本中。

以下命令从仓库根目录运行，使用项目 `.venv`。绘图解释器与科学计算
解释器分开，具体依赖见 [图形说明](FIGURES_README.md)。

## 恢复完整采集文件

查看实验目录 `transport_v1/archive.json` 列出的每个大文件，按
[无损分片说明](TRANSPORT_README.md)恢复对应的 `collection/` 文件。
已存在的原文件不覆盖。恢复器先验证每个分片及整个拼接结果，随后独占
创建目标文件。原始 gzip 字节保持不变。

核对 `collection/completion.json` 所列全部五个文件的 SHA-256：
`cases.jsonl.gz`、`events.jsonl.gz`、`state_witnesses.jsonl.gz`、
`status.json` 和 `summary.json`。其中状态见证属于评价者私有记录，
不能作为可部署代理的输入。

## 在新目录重放审计

已保存的 `audit/`、`analysis/` 和 `statistics_audit/` 目录应保留。
原入口拒绝覆盖这些目录。若要重新运行，在新的复核目录中只复制原始
清单和完整采集目录；不要复制已有的下游审计输出。例如：

```powershell
$runPath = 'outputs/movement_task/development_v1/movement_task_20261019T191708Z_eee0803df5bf'
$replayPath = 'outputs/movement_task/reproduction_check_v1'
New-Item -ItemType Directory -Path $replayPath -ErrorAction Stop
Copy-Item -LiteralPath (Join-Path $runPath 'manifest.json') -Destination (Join-Path $replayPath 'manifest.json')
Copy-Item -LiteralPath (Join-Path $runPath 'collection') -Destination (Join-Path $replayPath 'collection') -Recurse
.venv\Scripts\python.exe scripts/audit_movement_task_v1.py (Join-Path $replayPath 'manifest.json')
```

仅当新目录的 `audit/record_audit.json` 明确为 `PASSED`，并核对了全部
1,296 次执行后，再执行：

```powershell
.venv\Scripts\python.exe scripts/evaluate_movement_task_v1.py (Join-Path $replayPath 'manifest.json')
.venv\Scripts\python.exe scripts/audit_movement_task_statistics_v1.py (Join-Path $replayPath 'manifest.json')
```

第二条命令要求第一条已经完整成功。比较新旧 `analysis/summary.json`
中的统计量、全部案例和失败／拒绝／早结束列表；新的耗时和回执字节不
要求等于旧值。审计器按冻结容差核对独立移动逆估计和统计，不能把增加
一次重放当成新增物理任务。这里不调用收集器。

记录审计检查公开轨迹、保存选择及可检查的完整状态图，并独立复算移动
估计。它没有独立重新模拟全部物理动力学；初始 C4/C8 的部分计算仍复用
已有估计器。跨平台物理一致性和真实机器人迁移不在这一复核的证明范围内。

## 报告、图形与测试

完整审计和统计通过后，按 [报告说明](README.md)与[图形说明](FIGURES_README.md)
生成中文报告及 PNG/SVG。默认报告、来源回执和图形目录均拒绝覆盖；
已经交付的报告应保留，新展示输出使用入口支持的新目标路径。

`results_validation_v1/` 与 `pipeline_validation_v1/` 分别保留本次结果阶段
和冻结实现阶段的测试日志、源码哈希及可记录的软件原生夹具成本。夹具
回执覆盖范围以其 `scope` 字段为准，未记录的软件开销不解释为零。
这些测试不替代科学结果的记录审计，也不构成新方法、收益或投稿资格证明。
