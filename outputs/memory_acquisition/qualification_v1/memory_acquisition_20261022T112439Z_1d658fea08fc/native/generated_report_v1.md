# 保留任务记忆的真实获取与继续：原生软件资格

本轮软件契约：**PASSED**。54项完整分配，三个任务、三个介入时点、不变／变化两条件、三个固定获取程序。它们是工程接口验证，不是训练／校准／独立算法评价；没有新模型、新参数采用或任务收益晋级。

RAW_TASK_PI_T0.5从初始状态开始，普通任务步每步查询固定策略一次。CONTINUE直接继续；VALIDATE8实际执行至多8个正常任务PI步并提交积分；MOVE_MEASURE8在任务积分冻结期间最多64步移动、8步新测量，返回最后实际状态后保留原纠正与原任务积分继续。未到位置、测量不完整、提前成功均保留，不重置撤销位移。

中途窗口明确是未资格的WarmWindow，未送入仅适用于初始重置的ColdPrefix/C8辨识器。没有重辨识或新参数采用。获取分配是预先声明的确定性程序，记录one-hot行为概率；尾部只有KEEP，不能把这批记录冒称为具有全动作支持的随机策略价值学习数据。

冻结提交`1d658fea08fcfab01768d0dfc71974f2ea6cccca`。实际控制步8,836，全部重置2,754（含54次受控初始重置及工厂目标生成），物理帧1,421,180；固定策略查询7,975次。采集284.693秒，记录审计54.573秒。审计额外策略复算单列，不新增环境交互。新参数／响应模型拟合、策略训练和在线LLM API全部0。

独立部分重建重置／帧账本、float32仿射→XYZ实际噪声→最终裁剪、时钟／噪声游标、先保存后执行及积分更新与移动命令；另用保存观测回放程序。记录审计依赖可信采集器和保存的见证，不是外部物理真值认证或安全保证。

## 全部任务与条件

|任务|条件|程序|成功/分配|平均截止损失|实际步|移动步|探测步|完整窗口|
|---|---|---|---:|---:|---:|---:|---:|---:|
|push-v3|UNCHANGED|CONTINUE|3/3|94.333|283|0|0|0|
|push-v3|UNCHANGED|VALIDATE8|3/3|94.333|283|0|0|0|
|push-v3|UNCHANGED|MOVE_MEASURE8|3/3|135.333|406|98|8|1|
|push-v3|CHANGED|CONTINUE|2/3|227.000|681|0|0|0|
|push-v3|CHANGED|VALIDATE8|2/3|227.000|681|0|0|0|
|push-v3|CHANGED|MOVE_MEASURE8|3/3|145.333|436|128|0|0|
|reach-v3|UNCHANGED|CONTINUE|3/3|71.667|215|0|0|0|
|reach-v3|UNCHANGED|VALIDATE8|3/3|71.667|215|0|0|0|
|reach-v3|UNCHANGED|MOVE_MEASURE8|3/3|125.667|377|99|16|2|
|reach-v3|CHANGED|CONTINUE|3/3|75.000|225|0|0|0|
|reach-v3|CHANGED|VALIDATE8|3/3|75.000|225|0|0|0|
|reach-v3|CHANGED|MOVE_MEASURE8|3/3|128.333|385|128|0|0|
|door-open-v3|UNCHANGED|CONTINUE|2/3|228.333|685|0|0|0|
|door-open-v3|UNCHANGED|VALIDATE8|2/3|228.333|685|0|0|0|
|door-open-v3|UNCHANGED|MOVE_MEASURE8|2/3|296.333|889|192|0|0|
|door-open-v3|CHANGED|CONTINUE|2/3|224.333|673|0|0|0|
|door-open-v3|CHANGED|VALIDATE8|2/3|224.333|673|0|0|0|
|door-open-v3|CHANGED|MOVE_MEASURE8|2/3|273.000|819|192|0|0|

本表全部为事后描述，没有统计功效或预登记的任务优越性结论；三个介入层只有三个独立种子组，不能把54次程序执行或相关步数当54个独立样本。DIRECT_C8、积分补偿及后续强获取参考未在本软件人口上比较，所以本结果不能用于声明胜过它们。

## 所有提前结束、未完成获取与任务失败

|种子|任务|条件|程序|介入步|操作结果|任务成功|截止损失|
|---|---|---|---|---:|---|---|---:|
|65000|push-v3|CHANGED|MOVE_MEASURE8|16|ANCHOR_NOT_REACHED|True|196|
|65001|reach-v3|CHANGED|MOVE_MEASURE8|16|ANCHOR_NOT_REACHED|True|218|
|65002|door-open-v3|UNCHANGED|MOVE_MEASURE8|16|ANCHOR_NOT_REACHED|True|156|
|65002|door-open-v3|CHANGED|MOVE_MEASURE8|16|ANCHOR_NOT_REACHED|True|152|
|65003|push-v3|UNCHANGED|MOVE_MEASURE8|32|ANCHOR_NOT_REACHED|True|188|
|65003|push-v3|CHANGED|CONTINUE|32|ZERO_ACQUISITION_CONTINUE|False|500|
|65003|push-v3|CHANGED|VALIDATE8|32|VALIDATION_EXECUTED|False|500|
|65003|push-v3|CHANGED|MOVE_MEASURE8|32|ANCHOR_NOT_REACHED|True|177|
|65004|reach-v3|CHANGED|MOVE_MEASURE8|32|ANCHOR_NOT_REACHED|True|127|
|65005|door-open-v3|UNCHANGED|MOVE_MEASURE8|32|ANCHOR_NOT_REACHED|True|233|
|65005|door-open-v3|CHANGED|MOVE_MEASURE8|32|ANCHOR_NOT_REACHED|True|167|
|65006|push-v3|UNCHANGED|CONTINUE|64|None|True|63|
|65006|push-v3|UNCHANGED|VALIDATE8|64|None|True|63|
|65006|push-v3|UNCHANGED|MOVE_MEASURE8|64|None|True|63|
|65006|push-v3|CHANGED|CONTINUE|64|None|True|63|
|65006|push-v3|CHANGED|VALIDATE8|64|None|True|63|
|65006|push-v3|CHANGED|MOVE_MEASURE8|64|None|True|63|
|65007|reach-v3|UNCHANGED|CONTINUE|64|None|True|40|
|65007|reach-v3|UNCHANGED|VALIDATE8|64|None|True|40|
|65007|reach-v3|UNCHANGED|MOVE_MEASURE8|64|None|True|40|
|65007|reach-v3|CHANGED|CONTINUE|64|None|True|40|
|65007|reach-v3|CHANGED|VALIDATE8|64|None|True|40|
|65007|reach-v3|CHANGED|MOVE_MEASURE8|64|None|True|40|
|65008|door-open-v3|UNCHANGED|CONTINUE|64|ZERO_ACQUISITION_CONTINUE|False|500|
|65008|door-open-v3|UNCHANGED|VALIDATE8|64|VALIDATION_EXECUTED|False|500|
|65008|door-open-v3|UNCHANGED|MOVE_MEASURE8|64|ANCHOR_NOT_REACHED|False|500|
|65008|door-open-v3|CHANGED|CONTINUE|64|ZERO_ACQUISITION_CONTINUE|False|500|
|65008|door-open-v3|CHANGED|VALIDATE8|64|VALIDATION_EXECUTED|False|500|
|65008|door-open-v3|CHANGED|MOVE_MEASURE8|64|ANCHOR_NOT_REACHED|False|500|

## 来源与下一步

本轮RAW PI不消耗C8名义模型或响应模型，新采集费用独立于所有旧研究。此前任务PI开发／资格、物理重测资格、响应模型失败和任务记忆组件的完整历史费用继续保留，不能把此前开发成本抹去。新流程不调用旧失败ARX／F20评分器，不调旧人口。

[ASID作者项目页](https://weirdlabuw.github.io/asid/)已有信息驱动探索、辨识与任务策略训练流程；[SPI-Active官方摘要](https://proceedings.mlr.press/v305/sobanbabu25a.html)已有通过Fisher信息优化探索命令的路线。本轮只读项目页／摘要，不声称复现完整算法、审计其证明或获得新的研究区别。原五项查新仍保留，物理移动、积分记忆或标准信息指标本身不算创新。

下一阶段仍须明确可测量的机制差异、合格的新纠正／重辨识动作族以及独立训练／校准／自身历史评价。若没有合格新纠正，就不能提前训练一个“采用新纠正”的收益模型；没有观察到的采用分支不能用其他历史的终局填补。保留全部强对照和旧失败，CCF A目标继续开放。

## 复算

- manifest：`C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_acquisition/qualification_v1/memory_acquisition_20261022T112439Z_1d658fea08fc/manifest.json`
- 全部原始记录、费用及审计：`C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_acquisition/qualification_v1/memory_acquisition_20261022T112439Z_1d658fea08fc/native`
- 全部54案例另存all_cases.csv，全部18格另存task_condition_action.csv。
- 测试／编译／依赖／秘密／索引与差异检查由本轮冻结及交付回执绑定。
