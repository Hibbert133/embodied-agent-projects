# 获取位置失败诊断：完整54例的事后描述性分析

**全部新增分析均为事后描述性分析。没有新增环境交互、重置、物理帧、模型拟合、在线LLM API或未执行轨迹；不修改移动参数、进入阈值、旧结论或失败分母。**

完整核对54次执行、8,836个保存步和全部8个任务失败。18例分配MOVE，14例实际移动，3例完整窗口、11例达到移动上限、4例介入前成功。分析耗时4.969秒；独立审计4.480秒，核对468,194个字段。

新增13项数组检查在环境/拟合/网络守卫下通过；旧1,759项按源码哈希和回执复用。开发首次有2项数值类型错误：代数参考返回NumPy标量，不符合普通JSON数字接口；冻结前转成Python float，原日志保留，未改数值、容差或采集记录。

## 卡在哪些进入条件

沿用原程序的四个条件：至少4个真实移动观测；手位置距固定目标(0,0.6,0.25)的最大轴误差≤15mm；手与物体距离≥100mm；最近三段真实移动的最大轴位移≤3mm。首段历史不足时运动量缺失，不能填零。四个条件均通过才开始8步新测量。

实际移动结束时的完整条件组合计数：`{'READY': 3, 'position': 7, 'position+motion': 2, 'position+clearance': 2}`。下面保留全部18例；没有移动的4例标缺失原因，不画成零误差。

|任务|条件|介入|实际移动|抬升/横移|位置误差mm|近期运动mm|手物间距mm|未过条件|窗口|
|---|---|---:|---:|---:|---:|---:|---:|---|---|
|push-v3|UNCHANGED|16|34|12/22|13.006|2.894|255.901|均通过|True|
|push-v3|CHANGED|16|64|12/52|22.680|0.561|247.906|position|False|
|reach-v3|UNCHANGED|16|46|0/46|14.809|0.476|250.113|均通过|True|
|reach-v3|CHANGED|16|64|0/64|21.821|0.429|238.355|position|False|
|door-open-v3|UNCHANGED|16|64|25/39|25.215|1.719|214.015|position|False|
|door-open-v3|CHANGED|16|64|25/39|31.333|1.354|236.460|position|False|
|push-v3|UNCHANGED|32|64|32/32|19.180|0.543|236.099|position|False|
|push-v3|CHANGED|32|64|31/33|15.199|0.467|234.498|position|False|
|reach-v3|UNCHANGED|32|53|0/53|14.969|1.817|250.401|均通过|True|
|reach-v3|CHANGED|32|64|0/64|16.412|1.007|242.515|position|False|
|door-open-v3|UNCHANGED|32|64|38/26|174.300|3.874|100.939|position+motion|False|
|door-open-v3|CHANGED|32|64|38/26|108.243|6.434|154.032|position+motion|False|
|push-v3|UNCHANGED|64|0|0/0|缺失|缺失|缺失|EARLY_SUCCESS_NO_ACQUISITION|False|
|push-v3|CHANGED|64|0|0/0|缺失|缺失|缺失|EARLY_SUCCESS_NO_ACQUISITION|False|
|reach-v3|UNCHANGED|64|0|0/0|缺失|缺失|缺失|EARLY_SUCCESS_NO_ACQUISITION|False|
|reach-v3|CHANGED|64|0|0/0|缺失|缺失|缺失|EARLY_SUCCESS_NO_ACQUISITION|False|
|door-open-v3|UNCHANGED|64|64|64/0|108.248|1.599|75.412|position+clearance|False|
|door-open-v3|CHANGED|64|64|64/0|104.444|1.617|75.628|position+clearance|False|

## 全部阶段与步段

先在每条真实轨迹内计算，再按组组织。全部54例×抬升/横移两阶段×1–8、9–16、17–32、33–64四段，共432个登记行；非移动、短段和未到阶段保留缺失原因。分段在本次分析冻结前声明，是对已完成采集的事后规定，不冒称采集前预注册，也不选择最后“表现较好”的片段。

|任务|条件|阶段|有观测的轨迹/分配MOVE|逐轨迹平均位置误差mm|
|---|---|---|---:|---:|
|push-v3|UNCHANGED|LIFT|2/3|91.198|
|push-v3|UNCHANGED|LATERAL|2/3|46.178|
|push-v3|CHANGED|LIFT|2/3|93.057|
|push-v3|CHANGED|LATERAL|2/3|48.188|
|reach-v3|UNCHANGED|LIFT|0/3|缺失|
|reach-v3|UNCHANGED|LATERAL|2/3|83.461|
|reach-v3|CHANGED|LIFT|0/3|缺失|
|reach-v3|CHANGED|LATERAL|2/3|90.748|
|door-open-v3|UNCHANGED|LIFT|3/3|169.466|
|door-open-v3|UNCHANGED|LATERAL|2/3|148.039|
|door-open-v3|CHANGED|LIFT|3/3|162.867|
|door-open-v3|CHANGED|LATERAL|2/3|130.242|

这些均值不把长轨迹或时间步充作额外独立样本；每格只有三个介入组，缺失阶段不填零。完整432行、组标签及实际步数在stage_diagnostics.json。

抬升阶段控制目标保留起始XY；进入条件始终比较最终固定目标。上表位置误差对应最终进入目标，不能把它称为抬升控制器的主动目标跟踪误差。后表另列主动目标误差，二者语义分开。

## 发送指令、噪声与代数参考

每个已执行步独立复核float32仿射/死区变换→XYZ实际噪声→最终裁剪，并与原executed_action_oracle一致。分别保留策略动作裁剪、任务纠正发送裁剪、移动PD的±0.5限幅及执行器最终裁剪。控制器第一移动步按注册程序将导数项置0；诊断把该位移标为未测得，不能据此伪造历史。

|任务|条件|介入|末8个实际移动步数|平均主动目标误差XY mm|真参数零输入参考XY mm|末段实际噪声均值XYZ|任务纠正发送限幅步|执行器最终裁剪步|
|---|---|---:|---:|---|---|---|---:|---:|
|push-v3|UNCHANGED|16|8|5.638, -26.249|-15.000, 10.000|0.022125, 0.004331, 0.003514|22|15|
|push-v3|CHANGED|16|8|17.528, -24.921|13.733, -21.242|0.021425, -0.004600, 0.003179|18|20|
|reach-v3|UNCHANGED|16|8|-16.494, 2.414|-15.000, 10.000|-0.039682, 0.031675, 0.043201|14|1|
|reach-v3|CHANGED|16|8|16.638, -23.842|13.733, -21.242|-0.020521, -0.020580, 0.005824|10|7|
|door-open-v3|UNCHANGED|16|8|-32.787, 6.573|-15.000, 10.000|-0.046249, -0.004424, 0.000261|85|55|
|door-open-v3|CHANGED|16|8|12.511, -37.430|13.733, -21.242|-0.046249, -0.004424, 0.000261|77|84|
|push-v3|UNCHANGED|32|8|-21.413, 2.052|-15.000, 10.000|-0.006679, 0.006169, -0.005364|16|24|
|push-v3|CHANGED|32|8|-3.908, -17.315|-3.914, -10.842|-0.006679, 0.006169, -0.005364|14|37|
|reach-v3|UNCHANGED|32|8|-15.136, -11.609|-15.000, 10.000|-0.010858, 0.004487, -0.014634|23|1|
|reach-v3|CHANGED|32|8|1.215, -20.883|-3.914, -10.842|0.009560, 0.004490, -0.014223|20|17|
|door-open-v3|UNCHANGED|32|8|-191.624, -8.867|-15.000, 10.000|-0.007391, 0.007879, -0.005588|95|107|
|door-open-v3|CHANGED|32|8|-135.677, -32.777|-3.914, -10.842|-0.007391, 0.007879, -0.005588|70|86|
|push-v3|UNCHANGED|64|0|缺失|缺失|缺失|18|12|
|push-v3|CHANGED|64|0|缺失|缺失|缺失|18|12|
|reach-v3|UNCHANGED|64|0|缺失|缺失|缺失|9|0|
|reach-v3|CHANGED|64|0|缺失|缺失|缺失|9|0|
|door-open-v3|UNCHANGED|64|8|2.190, 8.178|-15.000, 10.000|-0.004278, 0.006583, -0.002687|401|417|
|door-open-v3|CHANGED|64|8|5.851, 16.118|8.596, 18.772|-0.004278, 0.006583, -0.002687|402|419|

代数参考e=−M⁻¹b/8只对应：原发送纠正是恒等、死区为0、测得运动为0且PD输入未限幅时，使无噪声施加XY命令为0的目标误差。它使用评估端真实扰动，不是拟合、部署估计或物理稳态证明；低噪声输入参考也不是物理无噪声响应。接触、内部mocap/机器人动力学、尚在移动、限幅及有限64步都可能破坏解释。不能仅因末段接近参考就断言唯一原因。

任务积分在移动中保留于任务记忆，原固定PD移动器仅使用恒等纠正，不使用任务积分，也没有独立的移动积分。保持记忆不能自动补偿移动器的常值输入误差。是否需要已有标准PID、局部目标或其他获取控制，必须由新的独立资格验证；本轮不生成那些未执行轨迹，也不调旧增益。

## 完整任务损失及可解释范围

|组|实际配对单元|平均移动减继续损失|平均真实移动/测量步|
|---|---:|---:|---:|
|0|6|+62.500000|58.666667|
|1|6|+29.166667|63.500000|
|2|6|+0.000000|21.333333|

全部18个配对：截止损失差总和+550步=实际移动/测量861步+其后剩余损失差-311步；这是已观察完整程序损失的恒等分解，不把任何阶段收益解释成独立因果效应。成功转失败0例，失败转成功1例。原程序均值、8个失败和全部对照保持原样。

手/物体位置、物体位移和抓取开合观测仅是代理；没有逐步接触力/接触对，不能唯一分离接触、状态改变、指令失配与噪声。相关轨迹步也不能充作独立样本来给显著性。

## 判断与后续

本轮给出可见进入条件、真实控制阶段、裁剪、噪声、指令跳变及完整费用的证据；反证和无法区分的因素也保留。若位置条件失败，不能归结为“测量需要更久”而擅自延长64步；若运动或间距条件失败，也不能放宽阈值。所有控制参数和54例保持冻结。

推荐先独立资格获取控制与中途辨识/新纠正接口，而不是对这3个完整窗口直接训练收益选择器。已有FIXED_PID、LOCAL_PD、LOCAL_PID等标准参考及RAW PI、C8、积分补偿、始终探测/探测不更新应保留，不能把本固定PD弱覆盖当作新方法优势。新训练、校准和自身历史评价需要单独种子与完整预算。

[MathWorks官方PID设计说明](https://www.mathworks.com/help/slcontrol/ug/baseline-pid-and-available-tuning-tools.html)将PID作为工作条件下的标准控制基线，并要求建模/调节后验证性能。这里只读该说明的控制项和设计流程；不继承其机器人保证，不以积分控制或静态平衡公式主张创新。原五项查新继续保留；获取改变状态及适用性时的具体新机制、强对照、独立部署和消融仍未完成。

## 复算与来源

- [冻结manifest与全部来源哈希](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_anchor_diagnosis/analysis_v1/anchor_diagnosis_20261022T120639Z_d2e04db2d872/manifest.json)
- [全部8,836个保存步的诊断](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_anchor_diagnosis/analysis_v1/anchor_diagnosis_20261022T120639Z_d2e04db2d872/step_diagnostics.jsonl.gz)
- [全部54条轨迹及缺失原因](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_anchor_diagnosis/analysis_v1/anchor_diagnosis_20261022T120639Z_d2e04db2d872/trajectory_diagnostics.json)
- [全部432条阶段/步段登记](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_anchor_diagnosis/analysis_v1/anchor_diagnosis_20261022T120639Z_d2e04db2d872/stage_diagnostics.json)
- [全部18个分配移动案例](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_anchor_diagnosis/analysis_v1/anchor_diagnosis_20261022T120639Z_d2e04db2d872/move_cases.csv)
- [禁用主诊断函数的独立审计](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_anchor_diagnosis/analysis_v1/anchor_diagnosis_20261022T120639Z_d2e04db2d872/audit.json)
- [原采集及历史来源费用，未重复计费](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_acquisition/qualification_v1/memory_acquisition_20261022T112439Z_1d658fea08fc/native/historical_costs.json)

![全部18个分配移动案例](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_anchor_diagnosis/analysis_v1/anchor_diagnosis_20261022T120639Z_d2e04db2d872/figures/all_18_assigned_moves.png)

全部新增分析为事后描述性分析。仅本地提交，不推送合并；CCF A目标仍未完成。

## 结果交付解读：证据、反证与下一步

11个未达到测量位置的案例中，7个只差位置，2个还差稳定运动，2个还差手物间距。全18面板图显示不同的真实过程，不应把它们压成一个“需要更多探测”的标签。

开门32步两例先抬升38步，只余26步横移，最终位置误差174.300/108.243mm，近期最大轴位移3.874/6.434mm，仍在移动。开门64步两例全部64步都在抬升，没有进入横移；最终手物间距75.412/75.628mm，未达100mm。位置/运动/间距都只是可见条件，不能从间距不足直接证明真实接触或唯一物理阻碍。

变化条件第0组的真参数零输入参考最大轴误差约21.242mm，超出15mm位置带；该组推物/到达最终误差22.680/21.821mm，且近期运动已小于3mm。这支持对常值输入误差的工程检查。反证是：变化第1组参考最大轴约10.842mm、在位置带内，推物/到达仍未到位；开门的明显移动/抬升问题也不由这个XY静态式解释。代数参考不等于物理稳态，不能据此推出“加积分必定解决”。

下表把全轨迹裁剪与移动阶段裁剪分开。前面的轨迹表任务纠正/执行器裁剪数覆盖完整任务，不能把任务段的裁剪归因到移动器。这里只对已审计逐步字段求和，并用原记录交叉核对阶段步数，不新增拟合或任务资格。

|阶段|实际步|策略动作裁剪步|任务纠正发送限幅步|PD限幅步|执行器最终裁剪步|
|---|---:|---:|---:|---:|---:|
|PREFIX_TASK|1866|834|774|0|690|
|TAIL_TASK|5997|1229|3349|0|3212|
|VALIDATE_TASK|112|58|48|0|64|
|REPOSITION|837|0|0|451|0|
|WARM_PROBE|24|0|0|0|0|

后续判断：先独立资格获取动作与中途辨识/新纠正，再学习采用价值。至少保留已有固定/局部目标与PD/PID对照，全部组/任务/条件、失败和完整费用；不在这54例上搜索新增益、放宽位置带或延长64步。没有实际执行过的PID/局部目标轨迹不能从当前PD记录推断任务结局。

软件执行、模型当前预测能力与包含获取成本的任务收益继续分别验证。当前诊断未获得合格的新参数采用接口、学习出的获取机制、强对照上的独立自身历史收益或消融；CCF A目标仍未完成。
