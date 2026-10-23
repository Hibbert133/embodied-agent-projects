# 时序标准参考实验：交付步骤

本文件是采集期间准备的交付操作说明，不是完成记录。当前科学实现冻结于
`88c168320712dab2db6a4f3de12f515e69e2a4fa`；报告与图表脚本是后处理，
不参与任何代理决策，也不改变冻结配置或数据。

一次性后继作业`finish_after_collector_v2.py`会附着到当前真实采集进程，
保持Windows进程句柄以避免PID复用，并验证正常退出、完整人口和全部
采集产物SHA后才依次执行下列四步。它不会重启采集或自动提交。
作业运行时不要另手工执行相同审计或覆盖目标目录；先查看同一run下
`postprocess_pipeline_v2/status.json`及对应真实作业进程。
**直到该作业完成，保持冻结HEAD和三个后处理程序字节不变。**

v1在启动前因Python 3.10不接受.NET七位小数时间戳而失败，没有启动审计、
新仿真或更改原采集。原程序与失败日志保留；v2只修复时间戳解析并使用新
作业目录，补充了原始失败时间戳、时区及100ns精度测试。

清单：
`outputs/chronological_cache_reference/development_v1/chronological_cache_reference_20261016T114510Z_88c168320712/manifest.json`。

只有真实采集进程正常结束、主阶段状态为`COMPLETED_REFERENCE`且完整4752次
执行后，才按顺序运行下面的命令。不能因为观察超时而重启采集，不能把
尚在写入的压缩文件当完整数据。主采集会话为92654；会话丢失时另查真实
`run_chronological_cache_reference.py ... --phase MAIN`进程及终态。

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts/audit_chronological_cache_reference.py --manifest outputs/chronological_cache_reference/development_v1/chronological_cache_reference_20261016T114510Z_88c168320712/manifest.json --phase MAIN --output outputs/chronological_cache_reference/development_v1/chronological_cache_reference_20261016T114510Z_88c168320712/main_audit/audit.json

.\.venv\Scripts\python.exe -X utf8 scripts/audit_chronological_cache_statistics.py --manifest outputs/chronological_cache_reference/development_v1/chronological_cache_reference_20261016T114510Z_88c168320712/manifest.json --phase MAIN --output outputs/chronological_cache_reference/development_v1/chronological_cache_reference_20261016T114510Z_88c168320712/main_audit/statistics.json

.\.venv\Scripts\python.exe -X utf8 scripts/report_chronological_cache_reference.py --manifest outputs/chronological_cache_reference/development_v1/chronological_cache_reference_20261016T114510Z_88c168320712/manifest.json --phase MAIN --output outputs/chronological_cache_reference/development_v1/chronological_cache_reference_20261016T114510Z_88c168320712/analysis_v1 --report reports/chronological_cache_reference_development_v1.md

& C:\Python314\python.exe -X utf8 scripts/plot_chronological_cache_reference.py --exports outputs/chronological_cache_reference/development_v1/chronological_cache_reference_20261016T114510Z_88c168320712/analysis_v1 --output outputs/chronological_cache_reference/development_v1/chronological_cache_reference_20261016T114510Z_88c168320712/analysis_v1/figures_v1
```

图表使用宿主已有的Matplotlib运行时；不修改项目虚拟环境或依赖锁。
必须查看实际主实验PNG，核对中文、完整十一方法及九因素格。布局示意图
明确标注合成数据，只能验证排版，不能替代实际数据图的检查。

一次性作业完成后，还可用`scripts/plot_chronological_cache_cases.py`读取
相同清单及`analysis_v1`导出目录，输出到`analysis_v1/failure_cases_v1`。
它按固定字典序选择全部注册比较的最早失去／挽回成功案例和每方法最早
停止；全量失败CSV仍保留。该步骤只画已有实际可见轨迹与发送指令，
没有新仿真，也不把方法各自不同的历史解释成单个当前决策的因果效应。
需要逐张查看实际案例PNG并另存QA记录；此步骤未接入已冻结的三个作业程序。

报告导出要求两份匹配且通过的审计及完整人口；它拒绝覆盖既有输出。
导出全部案例、失败／停止、逐例配对差、缓存来源与写入拒绝、右删失刷新
延迟和完整费用。源费用引用真实离线汇总及其SHA，不把未知旧工厂成本填0。

最后补充主要发现与边界、更新README和研究状态，检查所有相对链接及图表
来源。保留925项全仓库测试、编译、依赖、秘密和差异检查记录；新源修改
或者新失败需要相应复验。只暂存本轮明确产物，逐文件比较Git索引与工作
区原始字节并重新验证710个冻结输入，完成本地提交后核对提交blob。
没有push或merge授权。

以下三个旧未跟踪文件属于更早工作，禁止顺手暂存或删除：

- `outputs/action_response/development_v1/action_response_20261014T104928Z_1c3798544481/events.jsonl.gz`
- `reports/action_response_development_v1.md`
- `reports/action_response_development_v2.md`

本轮是标准参考和开发机制实验。完整新方法贡献、新方法独立确认与完整
论文尚待完成，不能因采集、审计或某个基线胜出就标记CCF A目标完成。
