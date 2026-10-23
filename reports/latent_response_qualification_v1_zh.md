# 已声明命令的多步响应模型资格 v1

这是公开历史初始化、多步响应预测及摘要消融的组件研究。没有训练获取决策或执行新的任务纠正；预测误差不等于任务收益，CCF A目标未完成。

执行冻结 `e4410b8985e383f8429e00bb9e577c99df129ea8`；运行 `latent_response_20261022T190735Z_e4410b8985e3`；清单 `f2bd7849340ebd46a45ab45fce1dcd39c9aa85818b014b18c6a1fa79696c7650`。

## 方法与可用信息

SS表示由公开历史初始化的8维隐状态，并在入口已声明的命令上逐步展开。SENT加入公开名义目标与手部的差；NO_SENT将相同结构的三个摘要输入通道置零；CURRENT_SENT只保留当前真实帧及摘要。DIRECT_MLP直接输出八步位移，参数数略多；DIRECT_RIDGE是同信息直接岭回归；PERSIST_ZERO是零位移参考。H10/F20保留为新同数据训练的强单步形式，不复活其旧控制选择器。

所有模型只接收真实过去观测/发送命令及入口已知的未来八步命令。mocap、真扰动、实际噪声及施加动作仅评估；不作特权训练标签。名义摘要不是实际状态或概率均值。网络/历史编码均为既有辨识路线，本轮不声称算法新颖性。

## 全部物理人口与费用

|阶段|冻结分配|实际完整执行|实际控制步|全部重置|物理帧|完整首8步|状态|
|---|---:|---:|---:|---:|---:|---:|---|
|SOFTWARE|36|36|2456|1836|930280|26|COLLECTED_FOR_INDEPENDENT_AUDIT|
|TRAIN|216|216|18600|11016|5601000|168|COLLECTED_FOR_INDEPENDENT_AUDIT|
|CAL|108|108|7454|5508|2791270|80|COLLECTED_FOR_INDEPENDENT_AUDIT|
|QUAL|432|432|30758|22032|11169790|348|COLLECTED_FOR_INDEPENDENT_AUDIT|

新物理费用合计：792次完整执行、59268控制步、40392全部重置、20492340物理帧。失败/部分尝试的费用也在各阶段账本中，不补采。训练/资格在响应包结束时停止，success_at_response_horizon=False不能当成完整500步任务失败。

每阶段原始cases/events/private_targets/public_trajectories/public_packet_metadata保留全部案例、未到边界、未到锚点、短包和早成功原因。原生数值每步记录，完整原生签名只在初末/变化边界记录，避免把未记录的逐步RNG状态称为已逐步测得。世界地址、时钟、噪声游标、实际动作与目标累计及全部重置/帧仍独立核对。

## 训练与模型审计

|任务|有实际响应轨迹|完整首包|无响应轨迹|
|---|---:|---:|---:|
|push-v3|61|61|11|
|reach-v3|44|44|28|
|door-open-v3|63|63|9|

模型状态：TWENTY_ONE_MODELS_SAVED_TRAIN_ONLY。21个拟合模型（12神经网络训练、30个闭式岭回归线性系统）加3个确定性零参考，共24个保存对象。每个神经模型5000更新，共60000更新，单个固定初值；同结构消融同初值、同采样。没有CAL/QUAL选模型、早停或改门槛。

独立模型审计：PASSED，重算30个岭回归系统，神经优化器重训0；另写特征、前向公式和采样日程，并在隔离Torch double核对16744个窗口。它不等于独立重演优化器。

## 独立资格结果

预定主候选SS_SENT资格：**NOT_QUALIFIED**。不把较好的次要模型替换为主候选，不追加样本。

|方法|完整分配|完整实际包|无效预测|完整分配H8损失m↓|完整分配H1损失m↓|
|---|---:|---:|---:|---:|---:|
|SS_SENT|432|348|0|0.197250184|0.195088610|
|SS_NO_SENT|432|348|0|0.197671128|0.195204012|
|SS_CURRENT_SENT|432|348|0|0.197647119|0.195247209|
|DIRECT_MLP_H8|432|348|0|0.197538597|0.195158233|
|DIRECT_RIDGE_H8|432|348|0|0.195850013|0.194603006|
|PERSIST_ZERO|432|348|0|0.197567829|0.194994523|
|HISTORY_LINEAR10|432|348|0|不适用|0.194537522|
|QUADRATIC_STATE20|432|348|0|不适用|0.194626925|

|方法|有效H8分母|有效H8原始均值m|H8截断次数|有效H1分母|有效H1原始均值m|
|---|---:|---:|---:|---:|---:|
|SS_SENT|348|0.003482987|0|348|0.000799654|
|SS_NO_SENT|348|0.004005538|0|348|0.000942912|
|SS_CURRENT_SENT|348|0.003975734|0|348|0.000996535|
|DIRECT_MLP_H8|348|0.003841018|0|348|0.000886082|
|DIRECT_RIDGE_H8|348|0.001744844|0|348|0.000196835|
|PERSIST_ZERO|348|0.003877305|0|348|0.000682857|
|HISTORY_LINEAR10|0|不适用/缺失|0|348|0.000115545|
|QUADRATIC_STATE20|0|不适用/缺失|0|348|0.000226528|

未测量/短包/预测失败使用预登记1m损失，实际RMSE截断于1m，统计以Decimal80半偶舍入的整数纳米计算；原始未截断误差和缺失原因另存case_losses。这不是用户最终任务的截止步损失，也不是物理误差上界或安全保证。

|SS_SENT减对照|完整分配均差m|整组95%区间m|上界严格<0|
|---|---:|---|---|
|SS_NO_SENT|-0.000420944|[-0.000739853, -0.000095010]|True|
|DIRECT_MLP_H8|-0.000288414|[-0.000629071, 0.000030676]|False|

18个独立组、三个时点分层整组重采样10000次，保留组内24单元相关性。区间条件于本次TRAIN源和单个固定网络初值，没有把相关时间步、重叠训练窗口或模型数当作独立样本，也不承诺充分统计功效。

|预登记门|结果|
|---|---|
|both_co_primary_intervals_pass|False|
|H8_all_point_controls_pass|False|
|H1_both_strong_controls_pass|False|
|all_24_cells_at_least_three_complete|True|
|all_18_groups_have_complete|True|
|no_invalid_saved_forecast|True|

|任务/初始/变化/命令包|完整包/18|
|---|---:|
|push-v3/NOMINAL/UNCHANGED/FIXED8|18/18|
|push-v3/NOMINAL/UNCHANGED/RANDOM8|18/18|
|push-v3/NOMINAL/CHANGED/FIXED8|18/18|
|push-v3/NOMINAL/CHANGED/RANDOM8|18/18|
|push-v3/BIASED/UNCHANGED/FIXED8|15/18|
|push-v3/BIASED/UNCHANGED/RANDOM8|15/18|
|push-v3/BIASED/CHANGED/FIXED8|15/18|
|push-v3/BIASED/CHANGED/RANDOM8|15/18|
|reach-v3/NOMINAL/UNCHANGED/FIXED8|10/18|
|reach-v3/NOMINAL/UNCHANGED/RANDOM8|10/18|
|reach-v3/NOMINAL/CHANGED/FIXED8|11/18|
|reach-v3/NOMINAL/CHANGED/RANDOM8|11/18|
|reach-v3/BIASED/UNCHANGED/FIXED8|13/18|
|reach-v3/BIASED/UNCHANGED/RANDOM8|13/18|
|reach-v3/BIASED/CHANGED/FIXED8|12/18|
|reach-v3/BIASED/CHANGED/RANDOM8|12/18|
|door-open-v3/NOMINAL/UNCHANGED/FIXED8|13/18|
|door-open-v3/NOMINAL/UNCHANGED/RANDOM8|13/18|
|door-open-v3/NOMINAL/CHANGED/FIXED8|17/18|
|door-open-v3/NOMINAL/CHANGED/RANDOM8|17/18|
|door-open-v3/BIASED/UNCHANGED/FIXED8|16/18|
|door-open-v3/BIASED/UNCHANGED/RANDOM8|16/18|
|door-open-v3/BIASED/CHANGED/FIXED8|16/18|
|door-open-v3/BIASED/CHANGED/RANDOM8|16/18|

## 限制与后续判断

数值合法、当前预测能力和包含获取费用的任务收益分别判断。本轮固定RAW PI/附近PID/外生命令源策略，预测不选动作，不能当作新方法自身历史的任务部署。即使所有预测门通过，也须另行冻结有效纠正与完整任务比较，保留RAW PI、DIRECT_C8、积分、始终获取/不更新、标准检测/历史辨识和任务相关获取强对照及消融。

若未通过，保留这个版本负结果，不围绕其添加逆控制/选择规则，不交换主次模型或修补资格人口。下一步必须针对证据重新提出可证伪解释和独立协议。新颖性仍需围绕获取动作改变状态、模型适用性及采用/拒绝后继行为的具体机制；旧来源上的离线建议不能代替独立自身时序评价。

参考边界：[SUBNET 2021](https://proceedings.mlr.press/v144/beintema21a.html)及[在线ANN-SS 2026](https://arxiv.org/html/2607.17614v2)提供已有历史初始化/多步展开思路；输出误差噪声假设不能直接转为本环境执行输入噪声保证。原模型适用范围、Residual RL、OCCAM、GAUGE、Poke and Strike及双重控制比较继续保留。CCF A目标未完成。
