# 中文报告生成工具

本目录只负责呈现已完成、已审计的四方法任务比较。它不修改冻结收集器、
统计方法、样本量或模型，不读取部分成绩来选择方法。

`render_report.py` 绑定本次 manifest 的 SHA-256。它要求收集完成、记录
审计通过、统计汇总完成和独立统计审计通过，并检查来源哈希、全部 1,296
案例、各方法 324 个案例以及完整失败／拒绝／早结束列表。已有报告和
回执不会被覆盖。

完成全部前置阶段后，在仓库根目录执行：

```powershell
.venv\Scripts\python.exe outputs/movement_task/reporting_v1/render_report.py outputs/movement_task/development_v1/movement_task_20261019T191708Z_eee0803df5bf
```

默认写入 `reports/movement_task_development_v1_zh.md`，来源与渲染器哈希
写入本目录 `report_sources.json`。任务采集仍在运行时，不会生成报告。
生成后还需人工核对表格、结论和全部链接，再进行本地结果提交。

`check_renderer.py` 使用纯软件样例检查完整分母、六组比较、区间方向、
拒绝未完成输入、拒绝其他 manifest 和保护已有文件。
`renderer_check_v1.json` 记录通过的软件检查及源码哈希。它没有读取本次
实际任务结局，没有运行机器人环境，也没有验证真实报告的最终文件链；
真实文件链仍须在完整采集和审计后检查。

这些文件位于冻结研究源码之外。统计量及原始数据的正确性仍由既有的
记录／数值审计与独立统计审计负责，不能用排版检查替代。
