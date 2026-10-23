# 任务 PI 与响应模型：零新增交互诊断报告

2026-10-22。**本报告全部新增分析为事后描述性分析**。旧人口只用于诊断，不用于重新选择参数、主程序或资格门槛。原始任务结果、全部失败与负结果保持不变。

**结论：暂不采集增量控制或移动前获取的新数据，先制定控制响应接口的独立资格协议。** 两套来源银行下，简单增量与单位增益上步残差延续在八个资格程序的总体预测中均未超过原 F20；这不是实际部署增量控制器的任务结论。任务 PI 提供了有竞争力的被动参考，但锁定主方法仍未通过同时超过两个强对照的资格门槛。

## 方法名字与三个不同判断

| 名字 | 本仓库中的意思 |
|---|---|
| C8 | 实际执行到第8个探测命令后，保留该次估计形成的基础纠正；C4/C8估计费用在原试验中单列。 |
| DIRECT / MOVE | 直接继续任务／先执行原冻结的移动过程再继续；MOVE费用不从任务截止损失中扣除。 |
| PI / Ti | 在任务期间持续累积瞬时策略参考误差；Ti是积分时间常数。0.5秒／2秒来自开发选择，本次不调整。 |
| RAW_TASK_PI | 不做C8探测，从原始基础策略命令开始持续积分；不是F20的RAW预测量。 |
| F20 / H10 / F43 | 已冻结线性预测器使用的20／10／43维特征；两套训练来源银行和全部模型均保留。 |
| RAW预测 | 原保存条件模型对当前真实历史和本步真实发送命令的一步预测。它不是已合格名义植物。 |

数值合法性只说明参数或命令符合计算约束；预测能力检验实际下一步位移；任务收益检验含获取成本和失败惩罚的完整程序。三者不能替代。固定策略只提供当前瞬时参考，raw/P不是最终任务误差。初始所有程序均有输入偏置[0.12,−0.08]；“不变”不是“无扰动”。

## 全部来源与成本

| 来源阶段 | 实际执行 | 独立组 | 用途 |
|---|---:|---:|---|
| 原生软件契约 | 36 | 1 | 单列，不能充当独立科学评价 |
| 开发 DEV | 720 | 6 | 全部程序与已选Ti来源，不再调参 |
| 独立资格 QUAL | 432 | 9 | 八程序×三任务×两计划条件 |

本诊断登记全部1,188次执行（含83个失败），核对全部153,045个真实保存步；其中149,481步具备共同所需的四个真实观测。每条轨迹最早三步共3,564步只登记缺少历史，不伪造零位移。没有短于四步的轨迹；缺少边界的案例保留原因，不能把未发生的变化或移动补成效果。

本次新增环境创建／重置／控制步／物理帧／模型拟合／策略查询／在线LLM API调用全部为0。分析主进程耗时119.374秒，独立记录审计135.871秒；表格、作图、软件检查另有回执，不将分析耗时计作物理交互。三次论文HTTP存档另记于literature_sources.json，与在线LLM调用分开。

历史任务试验实际费用仍为153,045控制步、60,588全部重置、31,059,225物理帧；在线C4/C8估计1,782次，历史独立记录审计另复算1,782次。本次不再拟合它们。C8来源银行、完整DEV调参及历史响应训练费用沿用原报告单列，不能因本次读取旧记录重新计费或隐去。

## 原独立资格结果保持不变

| 完整程序 | 成功／全部 | 平均截止损失（步）↓ |
|---|---:|---:|
| NO_PROBE | 41/54 | 196.574074 |
| DIRECT_C8 | 46/54 | 138.870370 |
| MOVE_KEEP_C8 | 46/54 | 167.500000 |
| MOVE_INTEGRAL | 54/54 | 114.925926 |
| RAW_TASK_PI_T0.5 | 53/54 | 83.037037 |
| DIRECT_TASK_PI_T0.5 | 53/54 | 101.962963 |
| MOVE_KEEP_TASK_PI_T0.5 | 54/54 | 113.407407 |
| MOVE_INTEGRAL_TASK_PI_T2.0 | 54/54 | 111.740741 |

主程序DIRECT_TASK_PI_T0.5相对DIRECT_C8：−36.907407步，九组95%区间[−70.333333,−3.387037]；相对MOVE_INTEGRAL：−12.962963步，[−32.703704,4.925926]。第二个上界跨零，共同资格仍为**NOT_PASSED**。RAW的较低次要均值不能替代主程序。主程序相对DIRECT_C8：26例损失增加、23例降低、5例持平；1例成功转失败、8例失败转成功，分母54不删减。

三个任务×两条件的完整任务表如下，每格9例；括号中为成功数。其余四个程序与全部DEV分层也在原报告和全量导出中，不省略失败。

| 任务／条件 | DIRECT_C8 | MOVE_INTEGRAL | DIRECT_TASK_PI_T0.5 | RAW_TASK_PI_T0.5 |
|---|---:|---:|---:|---:|
| push-v3 / UNCHANGED | 72.778（9/9） | 112.000（9/9） | 149.111（8/9） | 75.667（9/9） |
| push-v3 / CHANGED | 263.444（5/9） | 112.333（9/9） | 104.889（9/9） | 130.222（8/9） |
| reach-v3 / UNCHANGED | 57.111（9/9） | 73.444（9/9） | 85.111（9/9） | 66.667（9/9） |
| reach-v3 / CHANGED | 253.778（5/9） | 87.222（9/9） | 82.000（9/9） | 54.667（9/9） |
| door-open-v3 / UNCHANGED | 92.778（9/9） | 149.556（9/9） | 96.222（9/9） | 85.556（9/9） |
| door-open-v3 / CHANGED | 93.333（9/9） | 155.000（9/9） | 94.444（9/9） | 85.444（9/9） |

## 响应预测：增量捷径没有得到支持

对共同的实际步n≥3，只用o[n−3:n]四个真实观测、已经选择的本步命令u[n]和上步命令u[n−1]。目标o[n+1]仅用于评估，绝不进入预测查询。每步保留零响应、上步响应延续以及18个冻结模型的四种变体，共26个预测量：

- 原预测：m(h[n],u[n])。
- XY增量：d[n−1] + Jxy·(u[n]xy−u[n−1]xy)。
- 四维增量：d[n−1] + J4·(u[n]−u[n−1])；Z／夹爪方向没有取得原局部XY命令差资格。
- 上步残差延续：m当前 + d[n−1] − m上步；固定单位增益，没有重新拟合。

d为实际XY位移。指标为两坐标平均平方误差，先轨迹内取均值，再组内对案例取均值，最后独立组等权；不把相邻步当独立样本。下表为主程序全部六个任务条件，FEEDBACK8来源F20，单位mm²（m²乘10⁶）。两银行、H10/F20/F43及全部程序／阶段的完整结果在CSV中；图只突出原先已经关注的F20，不据本次结果重新选模型。

| 任务／条件 | 上步延续 | 原F20 | XY增量 | 四维增量 | 上步残差 |
|---|---:|---:|---:|---:|---:|
| push-v3 / UNCHANGED | 0.27028 | 0.08007 | 0.26460 | 0.26326 | 0.10926 |
| push-v3 / CHANGED | 0.25054 | 0.06786 | 0.24669 | 0.24351 | 0.12608 |
| reach-v3 / UNCHANGED | 0.13976 | 0.02462 | 0.14702 | 0.14667 | 0.03011 |
| reach-v3 / CHANGED | 0.15625 | 0.03044 | 0.16374 | 0.16351 | 0.03300 |
| door-open-v3 / UNCHANGED | 1.25369 | 0.46893 | 1.24086 | 1.24283 | 0.77349 |
| door-open-v3 / CHANGED | 1.28056 | 0.53438 | 1.27198 | 1.27486 | 0.93106 |

![八程序两银行的F20预测比较](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/figures/prediction_variants.png)

两套F20银行在八程序完整资格均值上均显示：简单增量接近上步延续，且劣于原预测；单位增益残差延续也劣于原预测。这说明当前捷径尚不适合直接作为已合格接口。反证和限制：部分局部阶段可能不同；不能以总体均值否定所有增量模型；模型使用保存历史和当前命令，仍可能受来源策略分布影响。没有部署这些预测规则来产生自身历史，不能宣称它们任务失败，更不能宣称原F20控制任务成功。

可能解释包括状态项变化、物理／执行器延迟和噪声时间结构，但本数据没有分离它们。已通过的局部静态XY命令差资格只覆盖该成分，不能证明当前F20的截距是正常无扰动响应，也不能允许直接反演成名义植物。

## 输入映射：PI没有始终更接近原策略

逐步独立复算float32链：仿射／死区 → XYZ加入保存实际噪声 → 最终裁剪，全部153,045步与保存executed_action_oracle逐值相同。真参数和噪声仅用于评估。输入偏差比较是在同一实际PI观测与raw动作上，将实际PI发送命令和该控制器保存的有界基命令分别通过同一注入映射；参考为原策略有界命令通过恒等输入映射。

“零噪声输入映射”不是物理无噪声位移；“同保存噪声”是代数影子输入比较，基命令没有实际执行，也不产生反事实机器人未来。下表先轨迹均值、再九组均值，仅包含实际有PI命令的状态，不能与全部任务54例的损失当作相同加权人口。单位为命令单位²，负数表示更接近该输入参考。

| 程序 | PI−基命令：零噪声输入MSE | PI−基命令：同保存噪声输入MSE |
|---|---:|---:|
| RAW_TASK_PI | +0.009965591 | +0.009892395 |
| DIRECT_TASK_PI | +0.008951642 | +0.008959301 |
| MOVE_KEEP_TASK_PI | +0.002082731 | +0.002172514 |
| MOVE_INTEGRAL_TASK_PI | -0.001822818 | -0.001734084 |

![全部任务条件的输入偏差与各组离散程度](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/figures/input_map_by_task_condition.png)

输入更接近原策略不是任务收益保证。三个PI总体输入偏差均值增加，但各自完整任务均值仍较对应基程序低；这是不同指标与不同实际状态人口，不能直接解释因果。移动积分+PI的总体输入均值改善也不能覆盖全部组。图中展示全部九组，没有剔除离群不利案例；各分图纵轴范围不同。

初始C8只按DIRECT_C8规范来源计一次：93个独立单元的保存估计全部数值有效，其他相同单元C8参数逐份一致，没有重新估计。资格54单元相对真实初始注入映射的误差如下。这是输入参数误差，不是物理模型误差或失败原因：

| 任务 | 单元数 | 矩阵相对Frobenius误差均值 | 偏置误差范数均值 |
|---|---:|---:|---:|
| push-v3 | 18 | 0.125425 | 0.025489 |
| reach-v3 | 18 | 0.094560 | 0.023044 |
| door-open-v3 | 18 | 0.100731 | 0.027819 |

## 共同移动与失败轨迹

共同移动采用MOVE_KEEP_C8规范来源，登记93个单元，实际可用移动83个；核对594条MOVE程序移动轨迹的命令、真实观测、施加输入和噪声游标完全相同。64条程序没有发生移动，不补零为有效移动。重复程序仍计实际物理费用，但不作为额外独立移动证据。

移动按抬升／抬升后和第1–8、9–16、17–32、33–64步交叉展示。canonical_movement_cross_cells.csv完整保留原生／DEV／QUAL×三任务×两条件×四段×两阶段共144格；无分配或短移动没有经过的阶段保留空值与原因。主表另保留所有程序自身实际访问窗口，不跨程序拼接状态。

| 资格PI失败 | 实际PI步 | 配对实际基线 | 策略XY／基命令XY／PI发送限幅 | 最终执行器裁剪步 | 下降阶段代理步 |
|---|---:|---|---|---:|---:|
| QUAL/04/push-v3/UNCHANGED/DIRECT_TASK_PI_T0.5 | 492 | DIRECT_C8，78步成功 | 0 / 0 / 0 | 10 | 475 |
| QUAL/06/push-v3/CHANGED/RAW_TASK_PI_T0.5 | 500 | NO_PROBE，60步成功 | 0 / 0 / 0 | 17 | 471 |

![两个资格PI失败与实际基线的完整轨迹](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/figures/all_qualification_pi_failures.png)

两例均500步超时失败；不是软件执行失败。它们未触发PI发送限幅，第二例输入偏差相对影子基命令反而降低（同保存噪声均值−0.013632587）。这反驳“发送限幅或输入偏差增加是所有失败的必要解释”。长期下降阶段代理与物体至任务目标距离未下降相伴，但不能确定接触故障、唯一参数原因或下一步可恢复性。原记录没有逐步接触力／接触对。参考跳变仅在连续策略查询间计算，跨探测／移动缺口不补参考。图中物体距离为实际步后info，策略参考为该步命令前观测；各基线在真实成功处结束，不延长到500步。

## 后续判断与查新

建议先独立冻结控制接口：明确目标响应单位、时延、历史状态、输入与观测对齐、允许发送的XY候选和失败处理；若需新训练，单独列人口与全部成本。再以新控制器自身生成的独立历史检验含获取成本的任务损失，保留C8、移动积分及所有有竞争力的锁定被动PI。当前没有预留种子或启动新采集。

已有[执行器动态下的增量反演研究](https://arxiv.org/html/2201.09805v2)、[自适应INDI](https://research.tudelft.nl/en/publications/adaptive-incremental-nonlinear-dynamic-inversion-for-attitude-con-2/)与[接触相关增量MPC](https://arxiv.org/html/2609.11661v1)明确限制了新颖性；阅读范围与版本快照另列于查新文档。本文数据不足以唯一认定带宽失配，也未复现上述系统。移动前获取仍需建立在有效控制基线上，完成变化检测、历史辨识、任务相关获取等强对照、独立部署和消融。标准PI、增量公式、诊断和测试通过均不视为CCF A目标完成，也没有安全保证。

## 复算、审计与来源

独立记录审计逐条重建全部预测及输入比较，检查5,184,349个数值字段；CSV展示另检查2,314,018个字段。新纯数组／保存记录测试24项通过；1644项旧测试仅在926份对应源码与原回执哈希完全匹配后复用，没有重复运行旧仿真。编译、依赖、秘密扫描、暂存字节、普通／暂存差异与实际分片恢复由交付闭合回执逐项约束。

复算命令（只读，默认新建独立分析目录）：`python -B scripts/analyze_task_passive_diagnosis_v1.py`；独立审计：`python -B scripts/audit_task_passive_diagnosis_v1.py <分析目录>`。所有新增测试禁止环境创建、重置、推进、在线调用和拟合；诊断与主审计真实进程都有拒绝调用计数回执。

分析manifest ID：`d5a0a2218eca79c988b600c474490533f15e2070d0b2105e174b81b870350093`。来源结果提交：`4dcacc870c47cb3a842471159990daddac58936b`；来源资格统计SHA256：`fcc38e47151d380bee3adf780e4e1b15179826b64ffea6cfb6e71494acb0c822`。全部输入与18份模型哈希逐项见manifest；原始大文件和实际恢复副本留本地，大文件提交原字节分片及索引。没有推送或合并。

- [来源及分析源码哈希清单](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/manifest.json)
- [独立记录审计](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/audit.json)
- [全部1,188个执行登记与失败](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/all_registered_executions.csv)
- [全部11,155个轨迹窗口与缺失原因](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/all_trajectory_windows.csv)
- [全部5,170个分层汇总格](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/all_grouped_cells.csv)
- [全部36,938个组级指标行](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/all_group_values.csv)
- [完整共同移动交叉分层](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/canonical_movement_cross_cells.csv)
- [93个规范初始C8单元](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/initial_C8_parameters.csv)
- [CSV独立展示审计](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/csv_independent_audit.json)
- [软件与源码回执](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/validation_v1/complete.json)
- [最终交付、恢复、扫描与差异闭合回执](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/task_passive_diagnosis/analysis_v1/passive_diagnosis_20261022T060222Z_4dcacc870c47/result_delivery/closure.json)
- [后续进入条件](C:/Users/Administrator/Desktop/embodied-agent-projects/docs/research/task_passive_diagnosis_decision_v1_zh.md)
- [新查新与阅读范围](C:/Users/Administrator/Desktop/embodied-agent-projects/docs/research/novelty_update_20261022_incremental_v1_zh.md)
