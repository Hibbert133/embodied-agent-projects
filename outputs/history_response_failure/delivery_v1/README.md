# 诊断交付索引

本轮是已封存响应模型的事后描述性诊断。原独立资格 NOT_QUALIFIED 保持不变，全部失败与缺失保留。新增环境交互、API 和模型拟合均为零。

- 主报告：`reports/history_response_failure_analysis_v1_zh.md`。
- 研究判断与反证：`docs/research/history_response_failure_research_decision_v1_zh.md`。
- 查新：`docs/research/history_response_failure_prior_art_v1_zh.md`。
- 全量诊断、逐案登记及独立审计：相邻 `analysis_v1/`。
- 指标聚合差异的补充复算：本目录 `objective_comparison.json`、`prepare_delivery.py`；图为 `objective_comparison.png`／`.svg`。
- 本目录 `delivery_audit.json` 独立核对补充算术、源码与测试回执、原来源字节、图形及实际恢复。
- `staged_index.json` 与 `final_index_closure.json` 记录暂存／磁盘字节、解码秘密扫描与普通／暂存差异检查；最终闭合回执自身不纳入自己的哈希。

`analysis_v1/grouped_tables.json` 和 `trajectory_stage_diagnostics.jsonl.gz` 原始文件继续留在本地；Git 提交的是相邻 `transport_v1/` 的四个有序分片和两个索引。`restoration_v1/` 的实际恢复副本保留在本地。恢复使用既有的 `scripts/archive_action_response.py restore --index <parts.json> --target <new-file>`，禁止覆盖。先按上轮交付索引恢复模型来源的大文件，再运行只读复算入口；来源哈希必须保持一致。

分析实现于 `790c6bb` 冻结。分析命令为 `scripts/analyze_history_response_failure_v1.py`，然后 `scripts/audit_history_response_failure_v1.py`、`scripts/report_history_response_failure_v1.py`。默认输出已存在时不能重跑覆盖；复算应显式指定新的目录。补充算术、传输和绘图也拒绝覆盖现有输出。

新 17 项纯数组测试通过，原 1,489 项回执核对 879 个原源码后沿用。最初 NumPy 测试辅助模块的延迟导入被严格网络隔离误拦截，失败日志保留；在进入隔离前预加载测试辅助模块后通过，没有放宽隔离或改动科学数据。后续独立审计还核对全部 84,672 个诊断单元；本目录的补充算术审计与其范围分别披露。

本轮没有新训练或采集协议进入执行。后续设计需隔离旧 TEST、单列训练与物理预算，满足强基线及完整任务收益条件。当前交付不是论文贡献或 CCF A 目标完成证明。
