# 带任务记忆的获取后缀与完整价值：标准参考资格

**本轮完成20项数组测试和已知有限模型的40项标准恒等式核验；没有机器人任务执行、训练或收益资格。DR、PI记忆交接及这些数值反例均不是本项目的新算法或CCF A贡献。**

## 完成了什么

任务记忆组件在普通任务步复用原PI精确算术；移动中断冻结任务积分，返回时更新实际回执中的步数和观测。若验证执行正常任务PI，则每步照实际回执提交积分。CARRY和EXPLICIT_RESET是两个明确模式，不能悄悄清零；保持积分本身不保证无突跳或安全。原PI源码没有修改。

两阶段参考估计的是固定目标获取／采用策略的完整截止损失，而不是随机采用行为的边际均值。用实际第一选项成本C、剩余终局损失Y和已付前缀t，递推D2=V2+ρ2(Y−Q2)，D1=V1+ρ1(C+D2−Q1)，完整估计t+D1。选项内提前结束没有第二动作，按真实终止罚值处理；不编造KEEP，也不把同一成本收费两次。

CONTINUE直接完成整个继续任务，因此其第一选项成本可以包含全部实际任务步，不能把所有C都叫额外获取成本。失败即使提前停止，截止损失仍为500，实际消耗另列。DR估计可能超出[0,500]，本轮不裁剪；那是估计器取值，不是执行了负步数或超过控制预算。

## 资格人口与费用

固定全枚举44个正概率模型原子，4个第一目标策略×2个后继策略×6种误设，共2,112条估计、48个完整汇总。它们是已知离散模型的概率原子，**不是44次独立采样或机器人轨迹**，不计算机器人成功率、样本置信区间或统计功效。

冻结提交`a3d10e731af49956dd3cafbc1806d65d1f0066b3`。主枚举耗时0.412370秒；独立有理数审计耗时0.779366秒，检查101,190个字段。新环境创建、重置、控制步、物理帧、随机流、模型拟合、策略训练和在线LLM API均为0。模型里的步数是符号成本，不记作实际机器人交互。

冻结前已进行同一已知模型的完整均值算术开发核对（2,112次估计器调用）和20项单元测试；正式冻结测试另有守卫及调用计数。开发核对缺少原始专用耗时回执，标为缺失，不伪造计时。正式输出不是未见数据上的独立确认；独立审计指另外实现的有理数枚举与展开公式，而非独立数据。

正确Q由已知有限模型的条件均值构造，是评价端oracle测试夹具，不是新训练出的机器人价值模型；零／常数Q是固定误设夹具。报告概率数值合法不意味着等于真实行为概率，二者均错的偏差完整保留。

## 机会与代价的数值反例

固定目标后继规则在NEAR／FAR使用不同采用概率，行为规则随机采用。下表只比较这些预先定义规则的已知期望；不挑单次未来噪声结果，也不说明真实机器人会有同样收益。

| 可见前缀code | 第一选项 | 固定后继规则完整损失 | 行为边际完整损失 |
|---|---|---:|---:|
| 0 | CONTINUE | 84.480000 | 84.480000 |
| 0 | VALIDATE | 135.287200 | 155.236000 |
| 0 | MOVE_VALIDATE | 160.149200 | 164.378000 |
| 1 | CONTINUE | 117.920000 | 117.920000 |
| 1 | VALIDATE | 188.291500 | 214.357500 |
| 1 | MOVE_VALIDATE | 109.408100 | 128.012500 |

code=1是刻意构造的机会例：随机采用行为下的MOVE均值可能劣于CONTINUE，但固定后继规则的MOVE价值更好；code=0保留移动代价较高的反例。不能把随机采用均值直接作为另一个后继策略的监督，也不能把这个人工构造当成真实任务收益。

## 全部误设组合

五种按阶段正确的组合共40项，其加权均值恒等式通过；两者均错的8项全部保留，不按无偏性晋级。DR并不在每个误设下都比IS有更小方差或MSE；完整数值见下表和CSV。

| 第一／后继策略 | 误设条件 | 真值 | DR均值 | DR偏差 | IS偏差 | DR MSE | 超范围原子 |
|---|---|---:|---:|---:|---:|---:|---:|
| MIXED/POSTSTATE_ADAPTIVE | P_TRUE_Q_ZERO | 123.572650 | 123.572650 | +0.000000 | +0.000000 | 24600.904263 | 9 |
| MIXED/POSTSTATE_ADAPTIVE | P_TRUE_Q_WRONG | 123.572650 | 123.572650 | +0.000000 | +0.000000 | 22227.558966 | 10 |
| MIXED/POSTSTATE_ADAPTIVE | P_WRONG_Q_TRUE | 123.572650 | 123.572650 | +0.000000 | +62.226245 | 98341.126372 | 18 |
| MIXED/POSTSTATE_ADAPTIVE | P1_TRUE_Q2_TRUE | 123.572650 | 123.572650 | +0.000000 | +14.288245 | 40139.429677 | 13 |
| MIXED/POSTSTATE_ADAPTIVE | Q1_TRUE_P2_TRUE | 123.572650 | 123.572650 | +0.000000 | +37.354067 | 51823.487027 | 19 |
| MIXED/POSTSTATE_ADAPTIVE | BOTH_WRONG | 123.572650 | 128.419208 | +4.846558 | +62.226245 | 99304.204641 | 17 |
| MIXED/KEEP_ONLY | P_TRUE_Q_ZERO | 138.551225 | 138.551225 | +0.000000 | +0.000000 | 30730.365813 | 9 |
| MIXED/KEEP_ONLY | P_TRUE_Q_WRONG | 138.551225 | 138.551225 | +0.000000 | +0.000000 | 25423.797272 | 10 |
| MIXED/KEEP_ONLY | P_WRONG_Q_TRUE | 138.551225 | 138.551225 | +0.000000 | +8.195478 | 30574.394910 | 13 |
| MIXED/KEEP_ONLY | P1_TRUE_Q2_TRUE | 138.551225 | 138.551225 | +0.000000 | -24.946584 | 13603.220252 | 10 |
| MIXED/KEEP_ONLY | Q1_TRUE_P2_TRUE | 138.551225 | 138.551225 | +0.000000 | +50.623400 | 63434.173590 | 25 |
| MIXED/KEEP_ONLY | BOTH_WRONG | 138.551225 | 128.137328 | -10.413897 | +8.195478 | 36300.211649 | 20 |
| ONLY_CONTINUE/POSTSTATE_ADAPTIVE | P_TRUE_Q_ZERO | 101.200000 | 101.200000 | +0.000000 | +0.000000 | 30373.813333 | 2 |
| ONLY_CONTINUE/POSTSTATE_ADAPTIVE | P_TRUE_Q_WRONG | 101.200000 | 101.200000 | +0.000000 | +0.000000 | 17680.480000 | 3 |
| ONLY_CONTINUE/POSTSTATE_ADAPTIVE | P_WRONG_Q_TRUE | 101.200000 | 101.200000 | +0.000000 | -38.600000 | 4282.193067 | 2 |
| ONLY_CONTINUE/POSTSTATE_ADAPTIVE | P1_TRUE_Q2_TRUE | 101.200000 | 101.200000 | +0.000000 | +0.000000 | 17680.480000 | 3 |
| ONLY_CONTINUE/POSTSTATE_ADAPTIVE | Q1_TRUE_P2_TRUE | 101.200000 | 101.200000 | +0.000000 | -38.600000 | 4282.193067 | 2 |
| ONLY_CONTINUE/POSTSTATE_ADAPTIVE | BOTH_WRONG | 101.200000 | 112.600000 | +11.400000 | -38.600000 | 4632.960000 | 2 |
| ONLY_CONTINUE/KEEP_ONLY | P_TRUE_Q_ZERO | 101.200000 | 101.200000 | +0.000000 | +0.000000 | 30373.813333 | 2 |
| ONLY_CONTINUE/KEEP_ONLY | P_TRUE_Q_WRONG | 101.200000 | 101.200000 | +0.000000 | +0.000000 | 17680.480000 | 3 |
| ONLY_CONTINUE/KEEP_ONLY | P_WRONG_Q_TRUE | 101.200000 | 101.200000 | +0.000000 | -38.600000 | 4282.193067 | 2 |
| ONLY_CONTINUE/KEEP_ONLY | P1_TRUE_Q2_TRUE | 101.200000 | 101.200000 | +0.000000 | +0.000000 | 17680.480000 | 3 |
| ONLY_CONTINUE/KEEP_ONLY | Q1_TRUE_P2_TRUE | 101.200000 | 101.200000 | +0.000000 | -38.600000 | 4282.193067 | 2 |
| ONLY_CONTINUE/KEEP_ONLY | BOTH_WRONG | 101.200000 | 112.600000 | +11.400000 | -38.600000 | 4632.960000 | 2 |
| ONLY_VALIDATE/POSTSTATE_ADAPTIVE | P_TRUE_Q_ZERO | 161.789350 | 161.789350 | +0.000000 | +0.000000 | 171353.625327 | 8 |
| ONLY_VALIDATE/POSTSTATE_ADAPTIVE | P_TRUE_Q_WRONG | 161.789350 | 161.789350 | +0.000000 | +0.000000 | 120113.557993 | 16 |
| ONLY_VALIDATE/POSTSTATE_ADAPTIVE | P_WRONG_Q_TRUE | 161.789350 | 161.789350 | +0.000000 | +99.036603 | 492619.476048 | 17 |
| ONLY_VALIDATE/POSTSTATE_ADAPTIVE | P1_TRUE_Q2_TRUE | 161.789350 | 161.789350 | +0.000000 | +20.094619 | 223463.042117 | 14 |
| ONLY_VALIDATE/POSTSTATE_ADAPTIVE | Q1_TRUE_P2_TRUE | 161.789350 | 161.789350 | +0.000000 | +68.894675 | 260083.136769 | 16 |
| ONLY_VALIDATE/POSTSTATE_ADAPTIVE | BOTH_WRONG | 161.789350 | 184.669703 | +22.880353 | +99.036603 | 493108.429531 | 17 |
| ONLY_VALIDATE/KEEP_ONLY | P_TRUE_Q_ZERO | 171.463500 | 171.463500 | +0.000000 | +0.000000 | 194034.383501 | 9 |
| ONLY_VALIDATE/KEEP_ONLY | P_TRUE_Q_WRONG | 171.463500 | 171.463500 | +0.000000 | +0.000000 | 127978.716834 | 18 |
| ONLY_VALIDATE/KEEP_ONLY | P_WRONG_Q_TRUE | 171.463500 | 171.463500 | +0.000000 | +8.277281 | 115246.707461 | 14 |
| ONLY_VALIDATE/KEEP_ONLY | P1_TRUE_Q2_TRUE | 171.463500 | 171.463500 | -0.000000 | -43.636313 | 57592.109742 | 8 |
| ONLY_VALIDATE/KEEP_ONLY | Q1_TRUE_P2_TRUE | 171.463500 | 171.463500 | +0.000000 | +73.731750 | 273616.573418 | 20 |
| ONLY_VALIDATE/KEEP_ONLY | BOTH_WRONG | 171.463500 | 144.928281 | -26.535219 | +8.277281 | 145597.207339 | 18 |
| ONLY_MOVE/POSTSTATE_ADAPTIVE | P_TRUE_Q_ZERO | 134.778650 | 134.778650 | +0.000000 | +0.000000 | 85218.135104 | 8 |
| ONLY_MOVE/POSTSTATE_ADAPTIVE | P_TRUE_Q_WRONG | 134.778650 | 134.778650 | +0.000000 | +0.000000 | 61939.086104 | 13 |
| ONLY_MOVE/POSTSTATE_ADAPTIVE | P_WRONG_Q_TRUE | 134.778650 | 134.778650 | +0.000000 | +133.036569 | 264469.918304 | 16 |
| ONLY_MOVE/POSTSTATE_ADAPTIVE | P1_TRUE_Q2_TRUE | 134.778650 | 134.778650 | +0.000000 | +11.128959 | 68444.887536 | 13 |
| ONLY_MOVE/POSTSTATE_ADAPTIVE | Q1_TRUE_P2_TRUE | 134.778650 | 134.778650 | +0.000000 | +110.778650 | 238446.712576 | 16 |
| ONLY_MOVE/POSTSTATE_ADAPTIVE | BOTH_WRONG | 134.778650 | 121.690219 | -13.088431 | +133.036569 | 271739.074244 | 17 |
| ONLY_MOVE/KEEP_ONLY | P_TRUE_Q_ZERO | 164.464750 | 164.464750 | +0.000000 | +0.000000 | 120637.422257 | 8 |
| ONLY_MOVE/KEEP_ONLY | P_TRUE_Q_WRONG | 164.464750 | 164.464750 | +0.000000 | +0.000000 | 80198.284757 | 18 |
| ONLY_MOVE/KEEP_ONLY | P_WRONG_Q_TRUE | 164.464750 | 164.464750 | -0.000000 | +63.841188 | 139459.776784 | 14 |
| ONLY_MOVE/KEEP_ONLY | P1_TRUE_Q2_TRUE | 164.464750 | 164.464750 | +0.000000 | -38.311781 | 38036.801849 | 8 |
| ONLY_MOVE/KEEP_ONLY | Q1_TRUE_P2_TRUE | 164.464750 | 164.464750 | -0.000000 | +140.464750 | 308105.708419 | 19 |
| ONLY_MOVE/KEEP_ONLY | BOTH_WRONG | 164.464750 | 148.555937 | -15.908813 | +63.841188 | 170565.622577 | 18 |

P_TRUE_Q_ZERO／P_TRUE_Q_WRONG：两阶段报告概率正确，Q为0或常数；P_WRONG_Q_TRUE：报告概率错而两阶段Q正确；P1_TRUE_Q2_TRUE／Q1_TRUE_P2_TRUE：逐阶段混合正确；BOTH_WRONG：均错。正确模型要求针对同一个固定目标后继规则的条件价值，不能拿另一个策略的均值冒充。

## 查新与后续机制

[Jiang与Li原文](https://proceedings.mlr.press/v48/jiang16.pdf)已有序贯DR；[OCCAM](https://arxiv.org/html/2406.17620v1)已有控制器表现预测与在线参数优化；[官方PID切换示例](https://www.mathworks.com/help/simulink/slref/bumpless-control-transfer-between-manual-and-pid-control.html)已有积分跟踪。阅读范围和机制边界见[一手来源说明](C:/Users/Administrator/Desktop/embodied-agent-projects/docs/research/memory_terminal_reference_prior_art_v1_zh.md)。本轮没有复现这些完整系统或继承其机器人保证。

具体后继假说仍是：同时建模真实获取后状态、控制器记忆、模型适用性证据与保留／采用的完整尾部损失，再估计该后继规则的获取前价值。当前只把其中状态交接和标准估计底座做成可运行参考；纠正／重辨识动作族、学习模型、原生连续执行契约、同预算强对照、独立自身历史部署和消融仍未完成。

后续原生执行器必须验证环境、噪声、时钟和先保存后执行；本模块的公开回执不能自行证明物理连续。新的随机获取／采用数据必须记录真实选择概率，训练／校准／评价分离，拒绝后从实际状态继续。标准DR恒等式不保证有限数据学习出的策略更优、减少错误更新或保留所有适应机会。

旧PI资格与F20开发失败保持原样，全部旧记录、原分片、恢复及预留种子保留。不调旧权重或把本次合成结果用于替旧方法翻案。下一步需要把上述假说落实到已资格的真实动作族和独立研究协议，不能以20项测试或40条恒等式作为论文完成。

## 复算文件

- [冻结manifest与来源SHA256](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_terminal_reference/qualification_v1/memory_terminal_20261022T104925Z_a3d10e731af4/manifest.json)
- [全部44个合成模型原子和终止分支](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_terminal_reference/qualification_v1/memory_terminal_20261022T104925Z_a3d10e731af4/finite_atoms.jsonl)
- [全部2,112条输入、预测夹具及估计](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_terminal_reference/qualification_v1/memory_terminal_20261022T104925Z_a3d10e731af4/estimates.jsonl)
- [完整48组合、偏差、方差与MSE](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_terminal_reference/qualification_v1/memory_terminal_20261022T104925Z_a3d10e731af4/setting_summaries.csv)
- [禁用主函数的独立有理数／展开公式审计](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_terminal_reference/qualification_v1/memory_terminal_20261022T104925Z_a3d10e731af4/audit.json)
- [开发核对披露、20项测试与检查回执](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_terminal_reference/validation_v1)

仅本地提交，不推送或合并。CCF A目标仍未完成。

## 审计失败、修复与完整交付

首次独立审计在逐字段核对开始前退出：函数内局部列表rows与同名JSONL读取函数冲突，触发UnboundLocalError。原失败日志与冻结v1审计器均保留。v2只把读取函数及两处调用改名为read_rows，未改变模型、参数、输入、公式、比较或容差；正式主枚举没有重跑。

修复新增3项回归测试：重现原失败、逐字符核对只改这三个名称、禁用主估计器／世界真值函数后复核全部保存输出。回归测试先在临时副本审计一次，然后本地提交冻结v2，再对原输出完成正式独立审计。新测试共23项（原20项＋修复3项），1,722项既有测试按源码哈希复用；这些不是额外机器人试验或未见数据资格。

修复回归检查总耗时1.505619秒，含一次完整保存输出的有理数复核和一次预期的原失败重现；没有新调用主估计器。首次失败没有独立单调计时，原guard在异常退出时未写出结束回执，二者明确记为缺失。失败重现在回归测试的环境／拟合／网络守卫内完成。

计算费用分别保留：冻结前均值开发核对2,112次主估计器调用；冻结前20项开发单元测试有控制台记录但没有调用计数；冻结正式20项测试有1,851次尝试（1,849完成、2次预期拒绝）；正式输出2,112次主估计器调用；修复回归及独立审计仅作有理数算术。缺少的开发计数与耗时不补填为0。完整环境交互、物理帧、拟合和在线LLM API仍为0。

- [首次审计失败与缺失回执说明](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_terminal_reference/audit_repair_v2/failure_record.json)
- [原始失败日志](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_terminal_reference/audit_repair_v2/original_failure.log)
- [审计修复冻结与3项回归测试](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_terminal_reference/audit_repair_v2/complete.json)
- [原manifest与有效v2审计器绑定](C:/Users/Administrator/Desktop/embodied-agent-projects/outputs/memory_terminal_reference/qualification_v1/memory_terminal_20261022T104925Z_a3d10e731af4/audit_repair_binding_v2.json)
- [本轮判断与下一阶段进入条件](C:/Users/Administrator/Desktop/embodied-agent-projects/docs/research/memory_terminal_reference_decision_v1_zh.md)

本报告保留全部48种组合及8项有偏反例。标准组件通过不改变旧实验失败，也不表示已经减少机器人错误更新或达到CCF A目标。

封存附记：首次结果封存已通过秘密扫描，但在将相对路径转换成仓库相对索引路径时退出，尚未创建结果提交。失败脚本、控制台和当时回执保留在`outputs/memory_terminal_reference/delivery_tools_v1/failed_attempt_v1/`。封存v2将输入路径先解析为绝对路径，再完成扫描与暂存；数值结果、独立审计及科学判据均未重跑或修改。
