# 中途干预执行资格 v2

日志完整性：**PASSED**；按新登记的状态见证合同，资格：**QUALIFIED**。
本轮只验证连续执行与可检查的状态比对，没有在线决策器或LLM，不是算法收益研究。旧v1结论仍为NOT_QUALIFIED，不用新标准回改旧数据。

提交：`1ba6b7b81e559f3a4de55189e61ef579f4920b9c`；清单：`ae549ee2e9cfdcac76a8f565db1f04321c22f6ebaac93d18694eec783aee6b6a`。

## 状态证据

保存并重建45份私有状态图，分别在初始、16步边界及结束时落盘。完整指纹保留；比较指纹仅规范化准确类型统计包装器的episode_start_time和time_queue中的计时值，保留初始化标志、队列长度/容量及全部其他状态。
公开准备器和干预器不接收状态图。独立日志审计检查原始完整指纹绑定、组件哈希、投影、双日志时间顺序和物理费用；共享序列化/投影数学已披露。主机状态见证不是外部真实性或通用行为等价证明。

|任务|全部边界可用|前缀及比较见证匹配|普通循环一致|三种首命令不同|停止后零步|
|---|---|---|---|---|---|
|push-v3|是|是|是|是|是|
|reach-v3|是|是|是|是|是|
|door-open-v3|是|是|是|是|是|

完整指纹差异仍逐项保存在record_audit.json的legacy_full_fingerprint_checks和witness_pair_diagnostics中；没有删除不一致字段来隐藏差异。

## 全部任务结果

|任务|种子|操作|成功|停止|边界可用|实际步数|截止损失|
|---|---:|---|---|---|---|---:|---:|
|push-v3|21600|CONTINUE_CURRENT|True|False|True|83|83|
|push-v3|21600|SWITCH_SAVED|True|False|True|86|86|
|push-v3|21600|RUN_UNCORRECTED|True|False|True|85|85|
|push-v3|21600|STOP|False|True|True|16|500|
|push-v3|21600|DIRECT_CURRENT|True|False|True|83|83|
|reach-v3|21601|CONTINUE_CURRENT|True|False|True|65|65|
|reach-v3|21601|SWITCH_SAVED|True|False|True|65|65|
|reach-v3|21601|RUN_UNCORRECTED|False|False|True|500|500|
|reach-v3|21601|STOP|False|True|True|16|500|
|reach-v3|21601|DIRECT_CURRENT|True|False|True|65|65|
|door-open-v3|21602|CONTINUE_CURRENT|True|False|True|86|86|
|door-open-v3|21602|SWITCH_SAVED|True|False|True|86|86|
|door-open-v3|21602|RUN_UNCORRECTED|True|False|True|87|87|
|door-open-v3|21602|STOP|False|True|True|16|500|
|door-open-v3|21602|DIRECT_CURRENT|True|False|True|86|86|

|操作|成功/分母|停止|实际控制步|平均截止损失|
|---|---:|---:|---:|---:|
|CONTINUE_CURRENT|3/3|0|234|78.000000|
|SWITCH_SAVED|3/3|0|237|79.000000|
|RUN_UNCORRECTED|2/3|0|672|224.000000|
|STOP|0/3|3|48|500.000000|
|DIRECT_CURRENT|3/3|0|234|78.000000|

失败、停止及边界不可用均保留；三个资格状态不能支持方法优越性、等效或非劣结论。

## 完整费用

本次控制步1425，尝试/返回1425/1425，政策查询1305，参数拟合尝试/完成30/30，nfev 30。
受控初始重置15次，全部重置765次，请求/完成帧389625/389625。
采集主体58.832919秒，其中状态见证构建19.272858秒；只读审计主体6.335758秒。进程启动费用见单独进程回执。
只读审计另付1305次策略查询、30次拟合、30次nfev和45份状态图重建，不产生新环境步骤。
各变体都计完整历史名义数据3840控制步、480受控重置、24480全部重置、12259200帧，按各自3个单元摊销为1280控制步/单元。历史设计3次枚举/432候选。
先前v1资格实际花费1377控制步、15受控重置、765全部重置、389385帧，作为历史开发费用另外保留，不重复收集。软件物理夹具费用见冻结前软件回执；新增API、名义训练、选择器拟合、策略更新均为0。

## 结论范围

C4是同一任务内保存但此前未用于任务动作的参数。切换保存参数不代表恢复物理状态或跨任务记忆；本轮也不进行中途重新辨识。资格即使通过，仍需新的合法历史决策方法、强基线、独立任务验证、消融和完整论文，不能作为CCF A发表证据。
