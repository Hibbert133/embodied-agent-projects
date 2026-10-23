# 四步与八步标准基线：复现入口

这份入口用于复核已保存的实验，调用时不会重新采集机器人轨迹，也不会调用在线 API。原实验按[冻结协议](../protocols/short_probe_reference_development_v1.md)执行一次；复核输出写入新的目录，不能覆盖原结果或已有复核回执。

## 运行方式

在仓库根目录使用已经安装依赖的项目虚拟环境：

```powershell
.venv\Scripts\python.exe docs/paper/replay_short_probe_results_20261019.py --phase MAIN --mode numeric
```

默认产生带时间戳的新 JSON，位于 `outputs/reproduction_reviews/short_probe_reference_v1/`。运行结束会打印状态与路径。也可以用 `--output` 指定该目录下尚不存在的 JSON 文件；已有文件会被拒绝，来源目录不会被写入。

| 模式 | 检查内容 | 额外计算与限制 |
|---|---|---|
| `hashes` | 版本化锚点、完整收集产物、分析、报告、流水线日志及 810 个冻结输入的哈希和相互引用 | 仅需 Python 标准库；不重算统计，也不检查已安装原生运行库。 |
| `numeric` | 上述检查，加上当前运行库绑定、总体与分组统计、注册区间、费用和三份完整 CSV 的复算 | 复用冻结的数值审计器；没有环境步、重置或 API 调用。 |
| `records` | 上述检查，加上完整事件、实际保存命令、连续状态、匹配前缀与成本的日志重放 | 复用冻结的日志审计器，重新查询固定政策、拟合参数及核对设计；这些是计算成本，不是新的物理执行。 |

例如，重放较小的预检记录：

```powershell
.venv\Scripts\python.exe docs/paper/replay_short_probe_results_20261019.py --phase SMOKE --mode records
```

主实验的 `records` 模式需要读取全部压缩日志，会明显慢于 `numeric`。正常查看原始结果可直接打开[预检报告](../../reports/short_probe_reference/smoke_v1.md)和[主实验报告](../../reports/short_probe_reference/main_v1.md)。不要再次运行原始采集流水线来做结果复核。

## 信任与证据范围

[入口源码](replay_short_probe_results_20261019.py)与各阶段的锚点文件一起纳入版本控制。获取材料时应核对可信 Git 提交；锚点文件本身不是外部真实性证明。入口要求原流水线五阶段全部成功、记录审计与数值审计通过，并核对各回执的运行身份和相互哈希；不完整数据会留下失败复核记录。

本轮清单是 `470c763b64db660ba5f0f075508f625bda894cbadd597aab8ae7cc84cb84576f`，采集源码提交是 `39300e55637971c8426effd20b49d3f0644fecd3`。每次复核另存入口源码、锚点和 Python/NumPy 版本及耗时。输入在复核结束时再次核对，避免把过程中改变的文件计为通过。

此入口复用原来的审计实现，并未增加第三套独立审计器。原日志审计已披露共享估计器、动作设计、固定政策及数值函数；状态见证来自原执行进程。通过重放不等于重新运行物理实验，也不能证明其他主机或其他环境版本下的隐藏状态完全一致。

## 已执行的入口检查

[预检重放回执](../../outputs/reproduction_reviews/short_probe_reference_v1/smoke_records_v1.json)完成 63 次执行、31,827 条事件的重放。731 项统计字段及 565 项日志审计回执字段均一致，最大绝对差为零；三份 CSV 合计核对 72 行。入口核对了 833 个唯一绑定文件，包括 810 个冻结输入。

这次复核额外进行了 7,891 次固定政策查询、54 次参数拟合、54 个优化器 nfev 以及 5,184 个设计候选核对，主体耗时约 32.71 秒。新增环境步、重置与 API 调用均为零。它检查复现入口是否正确连接已有材料，不增加原实验样本量。

[主实验数值重放](../../outputs/reproduction_reviews/short_probe_reference_v1/main_numeric_v1.json)也已通过，重新核对全部统计、成本和三份 CSV。正式图表及主比较的解释见[中文结果解读](short_probe_results_interpretation_20261019_zh.md)。原流水线现已完成五阶段，完整日志审计覆盖 1,817,244 条事件；该主实验日志审计是原独立审计器的一次执行，没有为了生成图表再跑一遍物理任务。
