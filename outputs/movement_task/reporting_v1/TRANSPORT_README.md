# 本次完整记录的无损分片

本次完整采集已经结束，两个原始文件超过普通 Git 托管的单文件上限。
[GitHub 官方说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
列明普通 Git 会拒绝超过 100 MiB 的文件。沿用仓库已有的
`scripts/archive_action_response.py` 原始字节分片和恢复工具，每块至多
32 MiB；这是已有保存方式，不修改实验、统计或原始记录。

`archive_movement_results.py` 调用已检查的报告完成性入口，要求完整
1,296 次执行、记录审计与独立统计审计通过，并核对全部来源哈希。
因此采集仍在写入时不能生成分片。完成这些阶段后执行：

```powershell
.venv\Scripts\python.exe outputs/movement_task/reporting_v1/archive_movement_results.py outputs/movement_task/development_v1/movement_task_20261019T191708Z_eee0803df5bf
```

结果写入该实验目录下新的 `transport_v1/`。超过 32 MiB 的采集文件
保存为字节分片和 `parts.json` 索引；`archive.json` 绑定原文件、完整
审计来源、入口和既有工具的哈希。每块以及完整拼接字节均核对 SHA-256。
原始文件保留不动；没有解压、重压缩、改换行或省略轨迹。目录已存在则
拒绝覆盖，归档中途失败则保留部分输出与失败记录。

本地提交选择索引、分片以及其余正常大小的结果文件；对于已归档的大文件，
不再重复提交原始大文件。原文件继续在本地用于原有审计。该步骤不自动
完成外部发布，也不解决整个仓库的总大小问题。

在新的复现副本中，原文件缺失时可按以下方式恢复；已有文件会被保护：

```powershell
.venv\Scripts\python.exe scripts/archive_action_response.py restore --index outputs/movement_task/development_v1/movement_task_20261019T191708Z_eee0803df5bf/transport_v1/cases.jsonl.gz.parts/parts.json --target outputs/movement_task/development_v1/movement_task_20261019T191708Z_eee0803df5bf/collection/cases.jsonl.gz
```

对 `archive.json` 中的其他文件使用对应索引和目标路径。恢复后核对原
`collection/completion.json` 的哈希，再按原流程审计。此入口的分片核验
检查实际拼接字节；通用恢复写入行为已有 `test_action_response_archive.py`
测试。本次真实归档已完成：三个原始文件共 568,403,124 字节，保存为
18 个分片；随后在外部临时目录实际恢复全部三个文件，完整 SHA-256
均与原始文件及采集完成回执一致。详见 `transport_v1/restoration_check.json`。
`archive.json` 中的恢复标志描述归档生成时的状态，后续实际恢复由上述
独立回执记录。临时恢复副本继续保留，原始文件与分片也全部保留。
