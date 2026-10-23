# 获取分支与完整任务价值：支持核查

**全部新增分析为事后描述性分析。没有训练或采集新数据，没有改变原资格／开发失败结论；本次不是新的获取方法或CCF A贡献。**

本次回答两件不同的事：已执行的完整程序还有多少事后选择空间；这些终局能否支持同一移动前历史处的获取／不获取、以及获取后采用／拒绝比较。利用全部未来结局挑最小损失不是可部署策略，也不是条件期望或总体性能界。

## 完整来源与费用

| 银行 | 执行 | 单元 | 独立组 | 程序 | 已发生控制步 | 失败 |
|---|---:|---:|---:|---:|---:|---:|
| PI_DEV | 720 | 36 | 6 | 20 | 90,626 | 45 |
| PI_QUAL | 432 | 54 | 9 | 8 | 55,513 | 31 |
| RANK_DEV | 432 | 36 | 6 | 12 | 58,685 | 41 |

完整登记1,584次科学执行、204,824个已发生控制步；三个银行分别计算，不合并组、不把相关时间步当独立样本。旧PI DEV用于选过参数，旧QUAL在本次被重新读作事后来源；它们都不是新方法的独立评价。新F20未运行QUAL。原生软件费用和所有历史训练／开发费用继续保留原账，本次不把读取旧记录重复计成机器人交互。

本次新增环境创建、重置、控制步、物理帧、模型拟合、策略训练和在线LLM API调用均为0。主分析耗时74.011秒；独立审计耗时96.955秒。审计逐字段复核840,672个CSV字段，并独立比较全部JSON汇总；守卫回执另列。

## 完整程序的事后选择空间

每单元最小损失使用该单元所有程序已经实际取得的终局；MOVE最小值只在已执行MOVE集合中取。二者均带有未来信息和选择乐观性，不能当作在线Oracle、方法收益、条件平均效果或总体价值界。即使某MOVE实现优于RAW PI，二者的前缀也可能不同，不能把差异直接归因于移动。

| 银行 | RAW PI(.5s)均值 | 全程序事后最小均值 | 事后选择差值 | MOVE事后最小均值 | MOVE较好／较差／持平 |
|---|---:|---:|---:|---:|---:|
| PI_DEV | 80.694 | 59.889 | 20.806 | 108.583 | 2/34/0 |
| PI_QUAL | 83.037 | 63.759 | 19.278 | 106.611 | 12/42/0 |
| RANK_DEV | 75.917 | 64.861 | 11.056 | 132.222 | 5/31/0 |

![完整程序集合的事后空间](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_support/analysis_v1/acquisition_support_20261022T094319Z_3fdf8c8aef8c/figures/portfolio_room.png)

以下保留全部三任务×不变／变化条件，括号是MOVE事后最小实现相对RAW PI较好／较差的完整单元计数。不变条件仍有初始偏置，不是无扰动。

| 银行／任务／条件 | 分母 | RAW PI | 全程序事后最小 | MOVE事后最小（较好／较差） |
|---|---:|---:|---:|---:|
| PI_DEV/push-v3/UNCHANGED | 6 | 170.000 | 62.333 | 106.000 (2/4) |
| PI_DEV/push-v3/CHANGED | 6 | 69.000 | 61.500 | 112.167 (0/6) |
| PI_DEV/reach-v3/UNCHANGED | 6 | 37.833 | 33.667 | 61.167 (0/6) |
| PI_DEV/reach-v3/CHANGED | 6 | 38.500 | 33.667 | 67.667 (0/6) |
| PI_DEV/door-open-v3/UNCHANGED | 6 | 85.500 | 85.500 | 146.000 (0/6) |
| PI_DEV/door-open-v3/CHANGED | 6 | 83.333 | 82.667 | 158.500 (0/6) |
| PI_QUAL/push-v3/UNCHANGED | 9 | 75.667 | 63.111 | 99.667 (3/6) |
| PI_QUAL/push-v3/CHANGED | 9 | 130.222 | 64.889 | 110.556 (4/5) |
| PI_QUAL/reach-v3/UNCHANGED | 9 | 66.667 | 45.778 | 62.556 (3/6) |
| PI_QUAL/reach-v3/CHANGED | 9 | 54.667 | 38.778 | 71.000 (2/7) |
| PI_QUAL/door-open-v3/UNCHANGED | 9 | 85.556 | 85.444 | 142.889 (0/9) |
| PI_QUAL/door-open-v3/CHANGED | 9 | 85.444 | 84.556 | 153.000 (0/9) |
| RANK_DEV/push-v3/UNCHANGED | 6 | 78.833 | 65.000 | 105.833 (2/4) |
| RANK_DEV/push-v3/CHANGED | 6 | 77.333 | 64.667 | 114.333 (1/5) |
| RANK_DEV/reach-v3/UNCHANGED | 6 | 59.333 | 42.833 | 83.833 (1/5) |
| RANK_DEV/reach-v3/CHANGED | 6 | 62.667 | 40.500 | 111.667 (1/5) |
| RANK_DEV/door-open-v3/UNCHANGED | 6 | 88.167 | 87.833 | 162.000 (0/6) |
| RANK_DEV/door-open-v3/CHANGED | 6 | 89.167 | 88.333 | 215.667 (0/6) |

## 同一物理前缀和候选后缀的支持

前三个节点以MOVE_KEEP_C8为规范来源：8步后、计划移动前、实际移动后。第四节点以RAW PI(.5s)在同一计划边界的自身历史为规范来源。没有合法规范节点时保留缺失，不替换规范来源。每个节点比较实际初始见证和已执行物理前缀，不仅比较当前位置；只移除原来源明确的计时字段，不忽略真实施加动作、噪声游标或物理时钟。

阶段标签和未发送的raw_policy不参与物理等价；控制程序的PI启动时间、控制器记忆语义另行核对。因此“物理前缀相同”不等于在线代理所有内部状态相同。完整初始与状态见证来源审计保持其原有局限，不声称独立重现物理或普适隐藏状态证明。

| 银行／节点 | 候选后缀 | 有支持／规范存活／完整分母 |
|---|---|---:|
| PI_DEV/AFTER8 | BEGIN_C8_PI_0.5_NOW | 36/36/36 |
| PI_DEV/BEFORE_MOVE | KEEP_C8 | 32/32/36 |
| PI_DEV/BEFORE_MOVE | BEGIN_C8_PI_0.5_NOW | 0/32/36 |
| PI_DEV/BEFORE_MOVE | MOVE_THEN_KEEP_C8_PI_0.5 | 32/32/36 |
| PI_DEV/BEFORE_MOVE | MOVE_THEN_INTEGRAL_PI_2.0 | 32/32/36 |
| PI_DEV/AFTER_MOVE | REJECT_KEEP_C8_AFTER_MOVE | 30/30/36 |
| PI_DEV/AFTER_MOVE | REJECT_KEEP_C8_PI_0.5_AFTER_MOVE | 30/30/36 |
| PI_DEV/AFTER_MOVE | REIDENTIFY_AFTER_MOVE | 0/30/36 |
| PI_DEV/AFTER_MOVE | SHORT_VALIDATION_RETURN_OLD | 0/30/36 |
| PI_DEV/RAW_PI_BEFORE_MOVE | CONTINUE_RAW_PI_0.5 | 28/28/36 |
| PI_DEV/RAW_PI_BEFORE_MOVE | MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY | 0/28/36 |
| PI_QUAL/AFTER8 | BEGIN_C8_PI_0.5_NOW | 54/54/54 |
| PI_QUAL/BEFORE_MOVE | KEEP_C8 | 48/48/54 |
| PI_QUAL/BEFORE_MOVE | BEGIN_C8_PI_0.5_NOW | 0/48/54 |
| PI_QUAL/BEFORE_MOVE | MOVE_THEN_KEEP_C8_PI_0.5 | 48/48/54 |
| PI_QUAL/BEFORE_MOVE | MOVE_THEN_INTEGRAL_PI_2.0 | 48/48/54 |
| PI_QUAL/AFTER_MOVE | REJECT_KEEP_C8_AFTER_MOVE | 44/44/54 |
| PI_QUAL/AFTER_MOVE | REJECT_KEEP_C8_PI_0.5_AFTER_MOVE | 44/44/54 |
| PI_QUAL/AFTER_MOVE | REIDENTIFY_AFTER_MOVE | 0/44/54 |
| PI_QUAL/AFTER_MOVE | SHORT_VALIDATION_RETURN_OLD | 0/44/54 |
| PI_QUAL/RAW_PI_BEFORE_MOVE | CONTINUE_RAW_PI_0.5 | 46/46/54 |
| PI_QUAL/RAW_PI_BEFORE_MOVE | MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY | 0/46/54 |
| RANK_DEV/AFTER8 | BEGIN_C8_PI_0.5_NOW | 36/36/36 |
| RANK_DEV/BEFORE_MOVE | KEEP_C8 | 36/36/36 |
| RANK_DEV/BEFORE_MOVE | BEGIN_C8_PI_0.5_NOW | 0/36/36 |
| RANK_DEV/BEFORE_MOVE | MOVE_THEN_KEEP_C8_PI_0.5 | 36/36/36 |
| RANK_DEV/BEFORE_MOVE | MOVE_THEN_INTEGRAL_PI_2.0 | 36/36/36 |
| RANK_DEV/AFTER_MOVE | REJECT_KEEP_C8_AFTER_MOVE | 34/34/36 |
| RANK_DEV/AFTER_MOVE | REJECT_KEEP_C8_PI_0.5_AFTER_MOVE | 34/34/36 |
| RANK_DEV/AFTER_MOVE | REIDENTIFY_AFTER_MOVE | 0/34/36 |
| RANK_DEV/AFTER_MOVE | SHORT_VALIDATION_RETURN_OLD | 0/34/36 |
| RANK_DEV/RAW_PI_BEFORE_MOVE | CONTINUE_RAW_PI_0.5 | 32/32/36 |
| RANK_DEV/RAW_PI_BEFORE_MOVE | MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY | 0/32/36 |

![后缀支持与缺失](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_support/analysis_v1/acquisition_support_20261022T094319Z_3fdf8c8aef8c/figures/suffix_support.png)

0条支持表示来源中没有相应已执行后缀，**不表示该动作收益为零或一定有害**。第8步就启动的DIRECT PI不能伪装成第16／32／64步才启动的PI；初始8步拟合不能伪装成移动后重新辨识；普通任务片段不能改名为短验证及回退。获取后的拒绝也要从已移动的状态继续，不能借用不移动分支的结局。

全部程序对按公共前缀匹配登记。只有两端都在规范节点存活且物理前缀相同时，才输出完整损失差和余下损失差，两者相等；否则保持缺失。它们只是实际单次耦合实现的配对差，不自动成为给定可见历史的条件期望。

## 完整程序表与缺失

### PI_DEV

| 程序 | 成功／全部 | 平均截止损失↓ |
|---|---:|---:|
| NO_PROBE | 29/36 | 164.555556 |
| DIRECT_C8 | 30/36 | 149.000000 |
| MOVE_KEEP_C8 | 30/36 | 181.111111 |
| MOVE_INTEGRAL | 34/36 | 140.333333 |
| RAW_TASK_PI_T0.125 | 34/36 | 96.527778 |
| RAW_TASK_PI_T0.5 | 35/36 | 80.694444 |
| RAW_TASK_PI_T2.0 | 34/36 | 101.277778 |
| RAW_TASK_PI_T8.0 | 32/36 | 140.694444 |
| DIRECT_TASK_PI_T0.125 | 34/36 | 111.083333 |
| DIRECT_TASK_PI_T0.5 | 36/36 | 78.666667 |
| DIRECT_TASK_PI_T2.0 | 35/36 | 102.083333 |
| DIRECT_TASK_PI_T8.0 | 32/36 | 134.166667 |
| MOVE_KEEP_TASK_PI_T0.125 | 34/36 | 139.194444 |
| MOVE_KEEP_TASK_PI_T0.5 | 36/36 | 112.750000 |
| MOVE_KEEP_TASK_PI_T2.0 | 35/36 | 139.777778 |
| MOVE_KEEP_TASK_PI_T8.0 | 32/36 | 167.250000 |
| MOVE_INTEGRAL_TASK_PI_T0.125 | 35/36 | 130.194444 |
| MOVE_INTEGRAL_TASK_PI_T0.5 | 36/36 | 114.500000 |
| MOVE_INTEGRAL_TASK_PI_T2.0 | 36/36 | 114.388889 |
| MOVE_INTEGRAL_TASK_PI_T8.0 | 36/36 | 119.138889 |

全部节点缺失原因：`{'DIFFERENT_PHYSICAL_PREFIX': 1196, 'SOURCE_TRAJECTORY_ENDED_BEFORE_NODE': 275, 'SOURCE_ALREADY_ENDED_AT_NODE': 29, 'CANONICAL_SOURCE_ALREADY_ENDED_AT_NODE': 40, 'CANONICAL_SOURCE_TRAJECTORY_ENDED_BEFORE_NODE': 40, 'CANONICAL_MOVEMENT_NOT_EXECUTED': 80}`。同一轨迹可以出现在多个节点，不能把节点数量当新的轨迹分母。

### PI_QUAL

| 程序 | 成功／全部 | 平均截止损失↓ |
|---|---:|---:|
| NO_PROBE | 41/54 | 196.574074 |
| DIRECT_C8 | 46/54 | 138.870370 |
| MOVE_KEEP_C8 | 46/54 | 167.500000 |
| MOVE_INTEGRAL | 54/54 | 114.925926 |
| RAW_TASK_PI_T0.5 | 53/54 | 83.037037 |
| DIRECT_TASK_PI_T0.5 | 53/54 | 101.962963 |
| MOVE_KEEP_TASK_PI_T0.5 | 54/54 | 113.407407 |
| MOVE_INTEGRAL_TASK_PI_T2.0 | 54/54 | 111.740741 |

全部节点缺失原因：`{'DIFFERENT_PHYSICAL_PREFIX': 695, 'SOURCE_TRAJECTORY_ENDED_BEFORE_NODE': 125, 'SOURCE_ALREADY_ENDED_AT_NODE': 38, 'CANONICAL_SOURCE_ALREADY_ENDED_AT_NODE': 10, 'CANONICAL_MOVEMENT_NOT_EXECUTED': 48, 'CANONICAL_SOURCE_TRAJECTORY_ENDED_BEFORE_NODE': 24}`。同一轨迹可以出现在多个节点，不能把节点数量当新的轨迹分母。

### RANK_DEV

| 程序 | 成功／全部 | 平均截止损失↓ |
|---|---:|---:|
| NO_PROBE | 30/36 | 161.000000 |
| DIRECT_C8 | 31/36 | 138.388889 |
| MOVE_KEEP_C8 | 28/36 | 210.388889 |
| MOVE_INTEGRAL | 32/36 | 168.277778 |
| RAW_TASK_PI_T0.5 | 36/36 | 75.916667 |
| DIRECT_TASK_PI_T0.5 | 36/36 | 82.972222 |
| MOVE_KEEP_TASK_PI_T0.5 | 35/36 | 136.583333 |
| MOVE_INTEGRAL_TASK_PI_T2.0 | 35/36 | 144.694444 |
| F20_RANK_W0.1 | 35/36 | 96.583333 |
| F20_RANK_W1.0 | 31/36 | 138.694444 |
| F20_RANK_W10.0 | 31/36 | 138.361111 |
| KINEMATIC_RANK_W1.0 | 31/36 | 138.277778 |

全部节点缺失原因：`{'DIFFERENT_PHYSICAL_PREFIX': 770, 'SOURCE_TRAJECTORY_ENDED_BEFORE_NODE': 120, 'CANONICAL_SOURCE_ALREADY_ENDED_AT_NODE': 2, 'SOURCE_ALREADY_ENDED_AT_NODE': 8, 'CANONICAL_SOURCE_TRAJECTORY_ENDED_BEFORE_NODE': 44}`。同一轨迹可以出现在多个节点，不能把节点数量当新的轨迹分母。

## 后续判断

现有数据能支持若干C8公共前缀上的已执行完整后缀比较，但缺少移动决策点才启动强PI、实际移动后重测及显式短验证返回的完整分支。RAW PI自身访问的历史也没有相应保留PI记忆的MOVE分支。故不能从这些来源直接训练／确认一个完整移动前获取决策器，更不能把事后最小值当成可达到收益。

不继续修补已封存的F20评分或ARX选择规则，不根据上述事后分层挑任务、调阈值或放大故障。下一机制设计必须先固定完整后缀效用、可获得反馈和控制器记忆语义；若需新数据，应单独冻结同历史不移动强PI／真实获取／获取后拒绝等分支，以及训练、校准、最终自身历史部署和费用。此报告没有启动新采集，也没有证明该候选数据设计必然产生正收益。

## 查新、边界与复算

[AA-POMDP](https://arxiv.org/html/2410.03892v1)已处理获取与任务的联合决策；[Poke and Strike](https://arxiv.org/html/2509.00178v1)已考虑探索扰动后的任务状态。动态规划、支持条件、收益预测及任务相关探索均不能直接算作新颖性。具体阅读范围和仍需区别的机制见[一手查新与问题定义](C:/Users/Administrator/Desktop/embodied-agent-projects/docs/research/acquisition_branch_support_prior_art_v1_zh.md)。

实现／分析协议冻结提交：`3fdf8c8aef8c04d8d34e47e21f55176eb2625864`。13项新增纯数组测试通过；旧检查按对应源码哈希复用。来源原统计、选择锁及原文件SHA256保持不变。主分析／独立审计均有阻断环境、拟合和网络的守卫；没有使用未执行轨迹填补标签。

- [分析manifest与全部来源哈希](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_support/analysis_v1/acquisition_support_20261022T094319Z_3fdf8c8aef8c/manifest.json)
- [全部执行与失败、首个PI时点](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_support/analysis_v1/acquisition_support_20261022T094319Z_3fdf8c8aef8c/all_cases.csv)
- [全部节点及缺失原因](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_support/analysis_v1/acquisition_support_20261022T094319Z_3fdf8c8aef8c/all_nodes.csv)
- [全部候选后缀支持](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_support/analysis_v1/acquisition_support_20261022T094319Z_3fdf8c8aef8c/all_requested_suffix_support.csv)
- [全部程序对及不可比较的原因](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_support/analysis_v1/acquisition_support_20261022T094319Z_3fdf8c8aef8c/all_node_program_pairs.csv)
- [逐单元事后空间及全部并列](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_support/analysis_v1/acquisition_support_20261022T094319Z_3fdf8c8aef8c/all_unit_portfolio_room.csv)
- [独立逐字段及原始前缀复核](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_support/analysis_v1/acquisition_support_20261022T094319Z_3fdf8c8aef8c/audit.json)
- [逐银行／组／任务条件汇总](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/acquisition_support/analysis_v1/acquisition_support_20261022T094319Z_3fdf8c8aef8c/results.json)

本次结果、标准公式和软件检查均不视为CCF A目标完成。原始记录、全部失败、原分片及恢复副本保留；只本地提交，不推送合并。
