# 完整轨迹的无损传输归档

本轮 events.jsonl.gz 在收集时已超过 100 MiB。
[GitHub 官方文档](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
说明普通 Git 推送会拒绝超过 100 MiB 的单文件。原文件仍作为本地
不可变审计输入保留；不把仍在写入的压缩流分块或暂存成完成结果。

完整收集和主审计 PASSED 后，archive_action_response.py 将超过
32 MiB 的已审计文件复制为每块至多 32 MiB 的原始二进制片段。
它不解压、不重新压缩、不改换行、不改变任何请求、观察、选择、
时间戳或随机数记录。每块保存偏移、长度及 SHA-256；整个串联结果
再核对原审计 SHA-256。小文件仍使用原始文件。

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/archive_action_response.py pack `
  --manifest outputs/action_response/development_v1/action_response_20261014T104928Z_1c3798544481/manifest.json `
  --audit outputs/action_response/analysis_v1/audit.json `
  --output outputs/action_response/transport_v1
```

归档输出必须是新目录且位于原始目录之外。归档索引绑定原运行、
清单、冻结源、主审计和归档工具散列。原始文件继续保留；实际提交
应选择分块和索引，避免把超过限制的原始大文件加入普通 Git 历史。
这不自动解决整个仓库大小或完成外部发布，当前没有授权推送。

复现方在原文件缺失时，从索引恢复到指定的新文件，再运行原审计。
恢复工具先检验全部块的顺序、长度和散列，再以独占创建方式写入。
已有文件拒绝覆盖；传输中变化会报错并保留新建的部分文件。

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/archive_action_response.py restore `
  --index outputs/action_response/transport_v1/events.jsonl.gz.parts/parts.json `
  --target outputs/action_response/development_v1/action_response_20261014T104928Z_1c3798544481/events.jsonl.gz
```

当前本地已有原文件，上述恢复命令应拒绝覆盖。在新的复现副本中，
恢复后还需用 archive.json／原主审计核对源散列。归档仅保证字节
运输完整性，不增加仿真、API、算法性质或物理／概率资格。
