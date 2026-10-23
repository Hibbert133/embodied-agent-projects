# 本阶段交付索引

所有新增分析为事后描述，零新增环境交互、模型拟合及在线LLM／控制API。旧资格失败保持。

- 中文主报告：reports/response_qualification_failure_analysis_v1_zh.md。
- 新假设、证据反证及原始文献：docs/research/response_failure_hypotheses_prior_art_v1_zh.md。
- 独立设计稿：docs/protocols/observable_history_transfer_design_v1_zh.md，对应JSON明确execute=false。
- 原始逐步复算、完整分段／缺失／来源：analysis_v1/；独立审计同目录。
- 导出修复记录：reporting_v1/；最终图形：reporting_v2/（图例移出柱图，初稿仍保留）。初始v1局部变量冲突保留，当前导出入口为
  scripts/report_response_qualification_failure_v2.py；不改任何数值输出或旧源文件。
- 新增14项纯数组／保存记录测试：validation_v1/。原1450项测试凭原源码哈希复用，
  未运行原生仿真测试；编译、依赖与秘密扫描另有回执。

复算用新输出目录运行 analyze_response_qualification_failure_v1.py；独立审计支持目录参数。
现有结果不覆盖。所有步、分段、真实初始历史与未执行的阶段均保留；不填零、不筛任务。
相关性与联合设计几何只是可能原因的证据，不是新的模型适用域、在线门槛或安全证明。
后继756次的预算只是完整列出的设计上限，没有新种子清单或收集许可；当前不得执行。
