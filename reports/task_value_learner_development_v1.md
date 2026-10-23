# 两阶段任务分支收益学习：中文开发结果

两阶段候选成功 177/192，直接分支值基准 175/192，最强固定宽十六步 191/192。对强固定基线的描述性竞争条件不满足（成功不减少且截止损失不增大）；这不是预注册的独立确认门或显著性结论。

这是旧开发数据上的整流嵌套交叉拟合与真实旧分支回放，不是新在线执行。采用标准核岭回归，未确立新颖性、独立泛化或 CCF A 投稿资格。新仿真、API 与经验记忆写入均为零。

运行 `task_value_learner_20261014T180054Z_c7a33065b399`；冻结源 `c7a33065b399b014d5cc0fb3d6231f65bc30eaed`；清单 `6c5caa113d9ebe9ac27e8337d3cd3e515487b66e638e19bf504678201ae3bbbb`。

[冻结协议](../docs/protocols/task_value_learner_development_v1.md) · [原始文献边界](../docs/research/task_value_learner_prior_art_v1.md) · [独立方程与决策审计](../outputs/task_value_learner/analysis_v1/audit.json) · [全部数据及模型](../outputs/task_value_learner/development_v1/task_value_learner_20261014T180054Z_c7a33065b399/manifest.json)

## 全部结果与十二个原基线

每方法分母 192。截止损失为成功时的总步，失败或停止为 500；历史选定分支步数不是本轮新增交互。

| 方法 | 成功 / 192 | 停止 | 历史平均在线步 | 平均截止损失 |
|---|---:|---:|---:|---:|
| TWO_STAGE | 177 | 0 | 125.6927 | 125.6927 |
| DIRECT_VALUE | 175 | 7 | 112.2396 | 129.7917 |
| CACHE_CONTINUE | 129 | 0 | 223.1406 | 223.1406 |
| MID8 | 118 | 38 | 162.1771 | 258.3646 |
| MID16 | 158 | 26 | 115.9740 | 180.7031 |
| MID8_WIDE | 178 | 3 | 117.1458 | 124.7396 |
| MID16_WIDE | 181 | 4 | 110.5208 | 120.4792 |
| MID8_WIDE_KEEP | 133 | 0 | 221.2865 | 221.2865 |
| MID16_WIDE_KEEP | 136 | 0 | 220.6875 | 220.6875 |
| G_OPTIMAL | 153 | 27 | 121.7344 | 188.8281 |
| RESPONSE_SET | 165 | 14 | 127.0417 | 161.7292 |
| EARLY8_WIDE | 175 | 2 | 120.9635 | 126.0885 |
| EARLY16_WIDE | 191 | 0 | 92.5260 | 92.5260 |
| NO_PROBE | 76 | 0 | 336.8698 | 336.8698 |

## 真正使用的动作

| 候选 | 选定真实分支 | 次数 |
|---|---|---:|
| TWO_STAGE | MID8_WIDE | 85 |
| TWO_STAGE | MID8_WIDE_KEEP | 4 |
| TWO_STAGE | MID16_WIDE | 78 |
| TWO_STAGE | MID16_WIDE_KEEP | 15 |
| TWO_STAGE | CACHE_CONTINUE | 10 |
| DIRECT_VALUE | MID8_WIDE | 93 |
| DIRECT_VALUE | MID16_WIDE | 89 |
| DIRECT_VALUE | CACHE_CONTINUE | 10 |

前模型只读取六步可见历史，后模型只读取实际所选探测的证据。后模型估计 UPDATE 减 KEEP 的损失；无效拟合强制 KEEP。前训练目标来自内层未参与拟合流上的后选择，包括后选择犯错；未取两个结局的最小值作标签。直接值基准固定使用原 UPDATE 分支与停止语义。

## 八流、任务与情景分层

| 方法 | 分层 | 成功 / 分母 | 停止 | 平均截止损失 |
|---|---|---|---:|---:|
| DIRECT_VALUE | CHANGED | 85 / 96 | 5 | 147.5729 |
| DIRECT_VALUE | UNCHANGED | 90 / 96 | 2 | 112.0104 |
| DIRECT_VALUE | door-open-v3 | 61 / 64 | 0 | 139.4062 |
| DIRECT_VALUE | push-v3 | 63 / 64 | 0 | 83.7344 |
| DIRECT_VALUE | r0 | 42 / 48 | 3 | 141.6667 |
| DIRECT_VALUE | r1 | 44 / 48 | 1 | 130.0208 |
| DIRECT_VALUE | r2 | 45 / 48 | 2 | 121.8750 |
| DIRECT_VALUE | r3 | 44 / 48 | 1 | 125.6042 |
| DIRECT_VALUE | reach-v3 | 51 / 64 | 7 | 166.2344 |
| DIRECT_VALUE | s0 | 23 / 24 | 0 | 118.1667 |
| DIRECT_VALUE | s1 | 24 / 24 | 0 | 80.8750 |
| DIRECT_VALUE | s2 | 24 / 24 | 0 | 84.2500 |
| DIRECT_VALUE | s3 | 21 / 24 | 3 | 137.7500 |
| DIRECT_VALUE | s4 | 21 / 24 | 0 | 167.2083 |
| DIRECT_VALUE | s5 | 21 / 24 | 0 | 153.1667 |
| DIRECT_VALUE | s6 | 18 / 24 | 4 | 191.2500 |
| DIRECT_VALUE | s7 | 23 / 24 | 0 | 105.6667 |
| TWO_STAGE | CHANGED | 85 / 96 | 0 | 147.5729 |
| TWO_STAGE | UNCHANGED | 92 / 96 | 0 | 103.8125 |
| TWO_STAGE | door-open-v3 | 61 / 64 | 0 | 139.8750 |
| TWO_STAGE | push-v3 | 63 / 64 | 0 | 83.7969 |
| TWO_STAGE | r0 | 43 / 48 | 0 | 132.8958 |
| TWO_STAGE | r1 | 44 / 48 | 0 | 130.5417 |
| TWO_STAGE | r2 | 46 / 48 | 0 | 112.9792 |
| TWO_STAGE | r3 | 44 / 48 | 0 | 126.3542 |
| TWO_STAGE | reach-v3 | 53 / 64 | 0 | 153.4062 |
| TWO_STAGE | s0 | 23 / 24 | 0 | 119.4167 |
| TWO_STAGE | s1 | 24 / 24 | 0 | 83.4583 |
| TWO_STAGE | s2 | 24 / 24 | 0 | 84.2500 |
| TWO_STAGE | s3 | 21 / 24 | 0 | 137.7500 |
| TWO_STAGE | s4 | 21 / 24 | 0 | 167.2083 |
| TWO_STAGE | s5 | 21 / 24 | 0 | 153.1667 |
| TWO_STAGE | s6 | 20 / 24 | 0 | 154.6250 |
| TWO_STAGE | s7 | 23 / 24 | 0 | 105.6667 |

## 全部失败

| 方法 | 案例 | 真实选定分支 | 停止 | 历史步 | 截止损失 |
|---|---|---|---|---:|---:|
| TWO_STAGE | s0/reach-v3/CHANGED/r0 | MID16_WIDE | False | 500 | 500 |
| DIRECT_VALUE | s0/reach-v3/CHANGED/r0 | MID16_WIDE | False | 500 | 500 |
| TWO_STAGE | s3/reach-v3/CHANGED/r0 | MID8_WIDE_KEEP | False | 500 | 500 |
| DIRECT_VALUE | s3/reach-v3/CHANGED/r0 | MID8_WIDE | True | 14 | 500 |
| TWO_STAGE | s3/reach-v3/CHANGED/r1 | MID8_WIDE_KEEP | False | 500 | 500 |
| DIRECT_VALUE | s3/reach-v3/CHANGED/r1 | MID8_WIDE | True | 14 | 500 |
| TWO_STAGE | s3/reach-v3/CHANGED/r3 | MID8_WIDE_KEEP | False | 500 | 500 |
| DIRECT_VALUE | s3/reach-v3/CHANGED/r3 | MID8_WIDE | True | 14 | 500 |
| TWO_STAGE | s4/door-open-v3/UNCHANGED/r0 | MID16_WIDE | False | 500 | 500 |
| DIRECT_VALUE | s4/door-open-v3/UNCHANGED/r0 | MID16_WIDE | False | 500 | 500 |
| TWO_STAGE | s4/door-open-v3/UNCHANGED/r1 | MID16_WIDE_KEEP | False | 500 | 500 |
| DIRECT_VALUE | s4/door-open-v3/UNCHANGED/r1 | MID16_WIDE | False | 500 | 500 |
| TWO_STAGE | s4/door-open-v3/UNCHANGED/r3 | MID16_WIDE | False | 500 | 500 |
| DIRECT_VALUE | s4/door-open-v3/UNCHANGED/r3 | MID16_WIDE | False | 500 | 500 |
| TWO_STAGE | s5/reach-v3/CHANGED/r0 | MID8_WIDE | False | 500 | 500 |
| DIRECT_VALUE | s5/reach-v3/CHANGED/r0 | MID8_WIDE | False | 500 | 500 |
| TWO_STAGE | s5/reach-v3/CHANGED/r2 | MID8_WIDE | False | 500 | 500 |
| DIRECT_VALUE | s5/reach-v3/CHANGED/r2 | MID8_WIDE | False | 500 | 500 |
| TWO_STAGE | s5/reach-v3/CHANGED/r3 | MID8_WIDE | False | 500 | 500 |
| DIRECT_VALUE | s5/reach-v3/CHANGED/r3 | MID8_WIDE | False | 500 | 500 |
| DIRECT_VALUE | s6/reach-v3/UNCHANGED/r0 | MID16_WIDE | True | 22 | 500 |
| DIRECT_VALUE | s6/reach-v3/UNCHANGED/r2 | MID16_WIDE | True | 22 | 500 |
| TWO_STAGE | s6/reach-v3/CHANGED/r0 | MID16_WIDE_KEEP | False | 500 | 500 |
| DIRECT_VALUE | s6/reach-v3/CHANGED/r0 | MID16_WIDE | True | 22 | 500 |
| TWO_STAGE | s6/reach-v3/CHANGED/r1 | MID16_WIDE | False | 500 | 500 |
| DIRECT_VALUE | s6/reach-v3/CHANGED/r1 | MID16_WIDE | False | 500 | 500 |
| TWO_STAGE | s6/reach-v3/CHANGED/r2 | MID16_WIDE_KEEP | False | 500 | 500 |
| DIRECT_VALUE | s6/reach-v3/CHANGED/r2 | MID16_WIDE | True | 22 | 500 |
| TWO_STAGE | s6/reach-v3/CHANGED/r3 | MID16_WIDE | False | 500 | 500 |
| DIRECT_VALUE | s6/reach-v3/CHANGED/r3 | MID16_WIDE | False | 500 | 500 |
| TWO_STAGE | s7/push-v3/UNCHANGED/r1 | MID8_WIDE | False | 500 | 500 |
| DIRECT_VALUE | s7/push-v3/UNCHANGED/r1 | MID8_WIDE | False | 500 | 500 |

## 完整训练费用与边界

本轮复用的完整 paired 原数据收集费用为 378,637 登记控制步／2,328 次控制初始重置（其中冷源 384／24 已在内）。完整旧名义模型来源另为 21,010／288。原初始化仪器测得 61,257,185 请求帧，详见原中文报告。没有按被选分支隐藏训练采集费，也没有将八折当成八次物理采集。

上表只描述历史所选分支表现，不能据此宣称包含训练摊销后的部署效率。如果后续部署成立，学习方法仍需承担这笔完整训练来源费；摊销人口与实测在线表现须另行冻结。

独立审计核对 492 组核岭方程、384 个保存选择与对应实际旧结局。严格证据特征构造及原配对状态检查明确复用，未重新仿真动力学，也没有全隐状态或概率资格。

下一步需要相对于标准任务相关方法明确机制差异，并在独立新范围真实执行冻结模型。开发回放的好结果不能代替它；负结果也不能通过调整同批特征或核参数后重新命名为确认。
