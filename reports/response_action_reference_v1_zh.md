# 固定响应模型的有限命令控制参考：完整任务结果

**完整开发门槛未通过，按协议没有开始独立资格采集。本轮没有建立超过全部注册强对照的独立控制参考；保留负结果，停止给这一评分接口叠加权重、门控或样本修补。**

本轮完整DEV中，所选F20（λ=.1）为35/36成功、平均截止损失96.583步；直接C8为31/36、138.389步，移动积分为32/36、168.278步。F20在这两项上较好，但仍落后RAW PI的36/36、75.917步，也落后直接C8+PI的36/36、82.972步。相对RAW PI多20.667步的组bootstrap描述性95%区间为[9.111,32.222]；这是开发选择后的结果，不能称为独立证明。不能只报道胜过C8／积分而省略更强对照。

运行 `response_action_20261022T073655Z_401a7f2427df`；实现／协议冻结提交 `401a7f2427df7ab6b7c23a84561a1491f661fe72`。只在完整DEV上选择一个全局λ；原先各项资格、负结果及预留种子保持不变。

## 方法意思与研究边界

F20是使用20维公开特征的既有线性响应预测器，不是LLM。它对五个有限有界命令评分，选择一项实际执行，不作名义植物反演。C8是先实际探测8步后保存的基础纠正；PI是任务期间持续积分参考。底层三个Sawyer固定策略只查询一次／任务步，Z和夹爪发送命令不由排序器更改。

候选为C8有界基命令，以及XY分别加±0.25的四个命令；先裁剪、量化为真实float32，再预测。0.25是标准化发送命令偏移，**不是25%混合比例**。跟踪参考r=.01×clip(raw_policy).XY米，来自mocap命令尺度；它仍不是实测无扰动手部位移。分数为||预测XY位移−r||²+λ×(.01米)²×||候选−基命令||²。λ=.1／1／10控制偏离基命令的惩罚；并列时BASELINE优先。

运动学评分使用完全相同候选／参考／消费接口，固定λ=1，预测改为.01×sentXY米。它也是代理，不能声称物理准确。全部八个既有程序、四个既有锁定PI参数、三条F20开发参数均保留。保存的计划真实驱动连续执行；没有把旧轨迹上的离线建议填成新控制器结局。

数值合法、当前预测能力、包含获取与失败费用的任务收益分别评价。模型分数降低不等于任务改善；本轮没有新的响应模型／策略训练、在线LLM API或安全证明。研究仍未完成移动前获取、获取后采用／拒绝的具体新机制、最终独立部署和消融，不能视为CCF A目标完成。

## 实际人口和完整费用

| 阶段 | 执行 | 控制步 | 全部重置 | 物理帧 | C4/C8估计 | 独立复算 |
|---|---:|---:|---:|---:|---:|---:|
| SOFTWARE_NATIVE | 36 | 8,888 | 1,836 | 962,440 | 60 | 60 |
| DEV | 432 | 58,685 | 22,032 | 11,309,425 | 720 | 720 |
| 总实际值 | 468 | 67,573 | 23,868 | 12,271,865 | 780 | 780 |

所有程序每次最多500个总控制步，仅一次受控初始重置。工厂50次目标生成重置完整收费。探测和移动已计入每次任务截止损失；失败／无效估计为500。真实费用与预留上限分开，未启动的QUAL不产生样本或环境费用。原生软件案例只验证执行契约，不参与开发选λ或独立科学比较。

收集中的F20前向实际154,090次，运动学代理57,480次；每实际排序步分别包含5次建计划与5次保存计划重算。独立审计的程序重放与原系数计算另见费用回执。分析／审计不推进环境，C4/C8只读复算已单列；不能把“没有新响应训练”写成“全部拟合为零”。所有阶段的新响应训练、策略训练和在线LLM API调用均为0。

首轮DEV审计发生一次可复现的浮点算术失败：第64步运动学候选分数用点积与平方后sum计算时相差一个float64末位，造成精确并列判断不同。控制器与记录保持原字节；独立v2仅对齐点积语义，不增加容差，不改变选择或门槛。失败的v1另消耗340次C4/C8只读复算；完成审计的780次与失败尝试合计1,120次，均不属于新响应训练。修复重放的额外预算在执行前单列，不能隐藏在一次成功审计的预算内。失败审计缺少原始单调计时回执，耗时标缺失；定位扫描的前向数量与耗时另存。

历史来源不是免费：C8银行480执行／3,840步／24,480重置／12,259,200帧；F20完整数据父来源756执行／71,773步／38,556重置／19,636,865帧。随后训练对照研究复用该数据，训练162个模型／720,000优化更新；父研究另有30个响应拟合／60,000更新，均在来源总账保留。144条FIT属于旧TRAIN216子集，不能重复计物理费。更早270次响应资格研究也单列保留，但没有给本次F20提供拟合数据。既有PI参数的完整旧DEV费用、本轮F20选λ所用的全部DEV费用、共享软件费用与每程序使用的来源费用分别披露；不能把同一银行在方法间的重复使用当作新收集。

若QUAL未运行，按54个资格单元的来源摊销只是潜在部署口径，不能称为已观测独立净收益。即使线上截止损失改善，仍需与完整训练／开发来源费用分别核对；不将来源费用再次重复加到已计费的线上探测或移动步。

## 完整程序比较与冻结选择

全局锁定程序：`F20_RANK_W0.1`，λ=0.1。开发规则是完整36单元截止损失总和最小，并列取最大λ；必须严格低于八个既有程序及运动学评分，才允许QUAL。实际开发判定：`FAILED_STOP_NO_QUALIFICATION`。没有逐任务选参数、换主方法、丢难例、重采旧人口或追加样本。

### DEV

| 程序 | 成功／全部 | 平均截止损失（步）↓ | 真实控制步 |
|---|---:|---:|---:|
| NO_PROBE | 30/36 | 161.000000 | 5,796 |
| DIRECT_C8 | 31/36 | 138.388889 | 4,982 |
| MOVE_KEEP_C8 | 28/36 | 210.388889 | 7,574 |
| MOVE_INTEGRAL | 32/36 | 168.277778 | 6,058 |
| RAW_TASK_PI_T0.5 | 36/36 | 75.916667 | 2,733 |
| DIRECT_TASK_PI_T0.5 | 36/36 | 82.972222 | 2,987 |
| MOVE_KEEP_TASK_PI_T0.5 | 35/36 | 136.583333 | 4,917 |
| MOVE_INTEGRAL_TASK_PI_T2.0 | 35/36 | 144.694444 | 5,209 |
| F20_RANK_W0.1 | 35/36 | 96.583333 | 3,477 |
| F20_RANK_W1.0 | 31/36 | 138.694444 | 4,993 |
| F20_RANK_W10.0 | 31/36 | 138.361111 | 4,981 |
| KINEMATIC_RANK_W1.0 | 31/36 | 138.277778 | 4,978 |

![DEV全部程序结果](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/figures/dev_all_programs.png)

完整三任务×两条件如下。括号中是成功／全部；CHANGED是计划变化条件，提前成功而未发生变化仍保留在完整分母中。UNCHANGED仍包含初始偏置[.12,−.08]，不是无扰动。

| 程序 | Push不变 | Push变化 | Reach不变 | Reach变化 | Door不变 | Door变化 |
|---|---:|---:|---:|---:|---:|---:|
| NO_PROBE | 354.17 (2/6) | 277.17 (4/6) | 103.50 (6/6) | 54.00 (6/6) | 88.50 (6/6) | 88.67 (6/6) |
| DIRECT_C8 | 71.67 (6/6) | 217.67 (4/6) | 62.67 (6/6) | 279.67 (3/6) | 98.33 (6/6) | 100.33 (6/6) |
| MOVE_KEEP_C8 | 107.33 (6/6) | 366.17 (2/6) | 87.50 (6/6) | 300.67 (3/6) | 174.83 (6/6) | 225.83 (5/6) |
| MOVE_INTEGRAL | 108.50 (6/6) | 115.33 (6/6) | 100.83 (6/6) | 235.00 (4/6) | 223.50 (5/6) | 226.50 (5/6) |
| RAW_TASK_PI_T0.5 | 78.83 (6/6) | 77.33 (6/6) | 59.33 (6/6) | 62.67 (6/6) | 88.17 (6/6) | 89.17 (6/6) |
| DIRECT_TASK_PI_T0.5 | 76.83 (6/6) | 89.67 (6/6) | 65.83 (6/6) | 76.33 (6/6) | 94.67 (6/6) | 94.50 (6/6) |
| MOVE_KEEP_TASK_PI_T0.5 | 105.83 (6/6) | 132.33 (6/6) | 84.00 (6/6) | 111.67 (6/6) | 168.67 (6/6) | 217.00 (5/6) |
| MOVE_INTEGRAL_TASK_PI_T2.0 | 107.33 (6/6) | 114.33 (6/6) | 90.33 (6/6) | 156.50 (6/6) | 174.83 (6/6) | 224.83 (5/6) |
| F20_RANK_W0.1 | 71.33 (6/6) | 112.50 (6/6) | 62.17 (6/6) | 127.67 (5/6) | 105.33 (6/6) | 100.50 (6/6) |
| F20_RANK_W1.0 | 71.67 (6/6) | 217.67 (4/6) | 62.67 (6/6) | 279.67 (3/6) | 98.17 (6/6) | 102.33 (6/6) |
| F20_RANK_W10.0 | 71.67 (6/6) | 217.67 (4/6) | 62.67 (6/6) | 279.67 (3/6) | 98.33 (6/6) | 100.17 (6/6) |
| KINEMATIC_RANK_W1.0 | 71.67 (6/6) | 217.50 (4/6) | 63.17 (6/6) | 279.83 (3/6) | 97.83 (6/6) | 99.67 (6/6) |

![DEV完整任务条件分层](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/figures/dev_all_task_conditions.png)

四个共同主要对照的损失差如下。DEV区间是在开发选择后计算的描述性区间，不是独立资格；QUAL须四个上界全<0，并且点均值低于全部九个对照。每个边界层内重采完整组10,000次，不把相关时间步或任务单元当独立组。

| 所选F20减去对照 | 均值差（步） | 组bootstrap 95%区间 |
|---|---:|---|
| F20_RANK_W0.1_MINUS_DIRECT_C8 | -41.805556 | [-61.444444, -22.166667] |
| F20_RANK_W0.1_MINUS_MOVE_INTEGRAL | -71.694444 | [-104.555556, -38.833333] |
| F20_RANK_W0.1_MINUS_RAW_TASK_PI_T0.5 | +20.666667 | [+9.111111, +32.222222] |
| F20_RANK_W0.1_MINUS_KINEMATIC_RANK_W1.0 | -41.694444 | [-61.055556, -22.333333] |

![DEV完整组与共同主要比较](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/figures/dev_primary_group_contrasts.png)

## 不利完整程序与全部失败

以下是所选F20与全部其他程序的实际配对完整程序比较；DEV也包含未选的备选λ，QUAL只有九个对照。正损失差称为不利完整程序，不能把它归因于某一个命令。尤其RAW PI没有相同初始探测，不能把其差异当成一次更新的因果效应。全部失败清单和完整原始轨迹保留。

| 阶段／其他程序 | 不利 | 改善 | 持平 | 其他成功→F20失败 | 其他失败→F20成功 | 分母 |
|---|---:|---:|---:|---:|---:|---:|
| DEV / NO_PROBE | 21 | 15 | 0 | 1 | 6 | 36 |
| DEV / DIRECT_C8 | 8 | 19 | 9 | 0 | 4 | 36 |
| DEV / MOVE_KEEP_C8 | 0 | 35 | 1 | 0 | 7 | 36 |
| DEV / MOVE_INTEGRAL | 1 | 34 | 1 | 0 | 3 | 36 |
| DEV / RAW_TASK_PI_T0.5 | 29 | 6 | 1 | 1 | 0 | 36 |
| DEV / DIRECT_TASK_PI_T0.5 | 22 | 10 | 4 | 1 | 0 | 36 |
| DEV / MOVE_KEEP_TASK_PI_T0.5 | 2 | 34 | 0 | 1 | 1 | 36 |
| DEV / MOVE_INTEGRAL_TASK_PI_T2.0 | 2 | 34 | 0 | 1 | 1 | 36 |
| DEV / F20_RANK_W1.0 | 7 | 20 | 9 | 0 | 4 | 36 |
| DEV / F20_RANK_W10.0 | 8 | 19 | 9 | 0 | 4 | 36 |
| DEV / KINEMATIC_RANK_W1.0 | 9 | 21 | 6 | 0 | 4 | 36 |

全部468次实际执行中保留54个失败；没有发生计划边界的原因及数量：`{'EARLY_SUCCESS': 6}`。无效拟合、提前结束与不经过某阶段均保留原因，不填成零误差，也不补未执行未来。失败者的截止损失与实际消耗步数分别报告。

## 真实所选命令的预测诊断（事后描述）

以下只分析实际排序阶段已执行命令的一步XY位移。预测误差包含实际噪声和未建模物理影响，不称为无噪声物理误差。先在每条轨迹内平均，再在组内可用轨迹等权，最后组等权。未执行候选保留为模型查询，不能生成它们的机器人未来或任务结局。

| 阶段／程序 | 完整轨迹 | 有排序轨迹 | 可用组 | 所选预测MSE（mm²） | 改变命令／排序步 |
|---|---:|---:|---:|---:|---:|
| DEV / F20_RANK_W0.1 | 36 | 36 | 6 | 0.290813 | 1,705/3,189 |
| DEV / F20_RANK_W1.0 | 36 | 36 | 6 | 0.472134 | 228/4,705 |
| DEV / F20_RANK_W10.0 | 36 | 36 | 6 | 0.365199 | 38/4,693 |
| DEV / KINEMATIC_RANK_W1.0 | 36 | 36 | 6 | 11.027644 | 383/4,690 |

命令变化次数是描述性计数，不是独立统计样本或“正确更新”标签。数值合法、预测准确与完整任务收益仍须分别判断；不利用这些诊断重新选λ或改变原门槛。

## 查新与后续判断

有限命令预测评分属于既有预测控制路线。新增一手查新还确认，[Dual-gatekeeper](https://arxiv.org/html/2604.15507v1)已将探索、任务成本预算和备份联合处理；[OCSP](https://arxiv.org/html/2609.25889v1)研究动作／查询联合选择与选择性反馈；[Dual MPC](https://arxiv.org/html/2511.08542v2)考虑未来控制与非参数模型不确定性。阅读范围、假设及不可直接继承的保证另列，不把“有益才探索”或门控视为新颖性。

完整开发门槛未通过，按协议没有开始独立资格采集。本轮没有建立超过全部注册强对照的独立控制参考；保留负结果，停止给这一评分接口叠加权重、门控或样本修补。

若本规则不具竞争力，封存其负结果，后续不在这版F20评分上改网格、加选择规则或补样本。保留所有竞争性C8、移动积分和锁定任务PI参考。获取主线仍需具体建模获取后的真实状态、模型适用性及采用／拒绝后的完整任务成本，并独立分配训练／校准／最终时序评价，补齐标准变化检测、历史辨识、始终获取、获取不更新、任务相关获取和消融。这里只比较注册的工程参考集合，不能声称已超过所有已有算法。

## 复算与来源

初始冻结35项数组测试通过，1,668项旧测试按对应源码哈希复用。交付导出另有3项纯数组测试，审计v2另有3项保存数组回归，独立CSV审计检查470,847个字段。全部真实案例经记录审计；DEV有效审计明确采用上述v2修订，原生软件回执仍保留原v1。科学阶段的选择、完整成对统计与门槛有独立矩阵复算。测试／自重放／状态见证只说明各自契约，不能代替物理控制收益、概率安全或论文贡献。

主入口：`python -B scripts/run_response_action_v1.py`；冻结v1记录审计为`scripts/audit_response_action_v1.py`。本次DEV实际通过的有效版本是本目录下`run_record_audit_v2.py`（修订来源与3项回归见下）；不把原v1首轮失败写成通过。数值审计入口为`python -B scripts/audit_response_action_statistics_v1.py --manifest <路径> --cohort DEV`。已有阶段和成功审计不能覆盖重跑。

- [冻结配置、源码、运行时、模型和来源哈希](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/manifest.json)
- [完整开发选择与门槛记录](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/selection.json)
- [全部实际执行](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/all_case_results.csv)
- [全部失败清单](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/all_failures.csv)
- [所有任务条件格](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/all_task_context_cells.csv)
- [全部成对程序差异](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/all_paired_task_contrasts.csv)
- [全部轨迹及缺失阶段](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/all_trajectory_rank_metrics.csv)
- [独立导出复核](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/csv_independent_audit.json)
- [实际费用与历史来源](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/costs_and_provenance.json)
- [保留原失败的独立审计v2修订](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/audit_amendment_v2_zh.md)
- [额外只读修复重放的执行前预算](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/audit_v2_pre_execution_budget.json)
- [新增获取决策查新与阅读范围](C:/Users/Administrator/Desktop/embodied-agent-projects/docs/research/acquisition_prior_art_20261022_v1_zh.md)
- [最终原件／分片恢复／扫描／差异闭合回执](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/response_action/development_v1/response_action_20261022T073655Z_401a7f2427df/result_delivery/closure.json)

完整原始日志、分片、失败及实际恢复副本保留。大文件在Git中提交索引与原字节分片，原件继续留本地；没有推送或合并。
