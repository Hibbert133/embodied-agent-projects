# 早期八步后的继续测量：中文完整结果

本轮八流／三任务／四噪声实现，共 96 单元、八方法、768 次真实方法执行。主目标 POINT16_CYCLE 对 POINT8 的重复性门未通过。目标是判断早期实际测量之后额外八步的任务作用；不是已确认的新停止算法或 CCF A 方法贡献。

运行 `early_evidence_20261015T015710Z_a9ec09feaf24`；冻结源 `a9ec09feaf2499420a17015f3aed379d14199de0`；清单 `35439398e20fc761b51355c6b9833aad899c1dff4aa9fd4d27a778a46ddbb414`。新种子 11500–11523；11524–11799 和所有旧保留范围未执行。API、经验记忆写入与策略权重更新为零。

[冻结协议](../docs/protocols/early_evidence_development_v1.md) · [原始文献边界](../docs/research/gaussian_reference_prior_art_v1.md) · [执行与费用审计](../outputs/early_evidence/analysis_v1/audit.json) · [清单与原始分流轨迹](../outputs/early_evidence/development_v1/early_evidence_20261015T015710Z_a9ec09feaf24/manifest.json)

## 全部八方法

每方法完整分母 96。成功用实际总步，失败或停止的截止损失为 500。实际物理步另外报告，不能把未执行任务的低步数当作效率改善。

| 方法 | 成功 / 96 | 停止 | 平均在线步 | 平均探测步 | 平均截止损失 | 平均含完整来源步 | 无效拟合检查 |
|---|---:|---:|---:|---:|---:|---:|---:|
| POINT8 | 86 | 5 | 101.8958 | 8.0000 | 127.5208 | 320.7500 | 5 |
| POINT16_CYCLE | 92 | 0 | 102.5208 | 16.0000 | 102.5208 | 321.3750 | 0 |
| POINT16_WIDE | 92 | 0 | 105.6771 | 16.0000 | 105.6771 | 324.5312 | 0 |
| GAUSS8 | 92 | 0 | 97.6354 | 8.0000 | 97.6354 | 316.4896 | 5 |
| GAUSS16_CYCLE | 93 | 0 | 100.5000 | 16.0000 | 100.5000 | 319.3542 | 0 |
| IVR_GLOBAL16 | 93 | 0 | 100.5000 | 16.0000 | 100.5000 | 319.3542 | 5 |
| IVR_TASK16 | 95 | 0 | 92.5833 | 16.0000 | 92.5833 | 311.4375 | 9 |
| NO_PROBE | 44 | 0 | 317.6875 | 0.0000 | 317.6875 | 317.6875 | 0 |

所有名义模型方法完整承担 21,010 个旧控制步／288 次控制重置，按 96 单元摊销（218.8542 步／3 次重置）。物理源只采集一次。名义 TASK 分布只取旧 TRAIN 的 POLICY_ONLY 原政策 xy 命令；不使用资格检验结局或当前任务结果。

POINT16_CYCLE 是两次宽八，POINT16_WIDE 是四方向各四步；二者真实运动顺序不同，后者作为总体强固定基线保留。GAUSS 与 IVR 为标准近似参考：条件于名义模型、经验 RMS 和局部 Jacobian，没有已验证的物理似然或概率／安全资格。Gaussian 构建可以使用有限但逆不稳定的点参数；无效拟合检查计数不等于停止数或案例数。

## 主任务收益重复性

| 指标 | 结果 |
|---|---:|
| contexts | 24 |
| fully_matched_contexts | 24 |
| non_tie_contexts | 24 |
| sign_reversal_contexts | 8 |
| sign_reversal_fraction | 0.3333333333333333 |
| leave_one_out_checked | 84 |
| leave_one_out_correct | 73 |
| leave_one_out_abstained | 4 |
| leave_one_out_agreement | 0.8690476190476191 |
| leave_one_out_coverage | 0.9545454545454546 |
| passed | False |

四次噪声实现从初始状态开始，前八步可见轨迹可能不同；这是名义上下文重复性，不能声称完全固定状态的条件收益分布。+1 为继续八步后截止损失改善，−1 为恶化，0 为相同。其余三重复的符号和预测当前非零方向，和零弃权。

| 流 | 任务 | 四符号 | 共享八步完整 | 反转 | 留一正确 / 已预测 |
|---:|---|---|---|---|---|
| 0 | push-v3 | [-1, 1, -1, -1] | True | True | 3 / 4 |
| 0 | reach-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 0 | door-open-v3 | [1, 1, 1, 1] | True | False | 4 / 4 |
| 1 | push-v3 | [0, -1, -1, 0] | True | False | 2 / 2 |
| 1 | reach-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 1 | door-open-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 2 | push-v3 | [0, -1, 1, -1] | True | True | 0 / 1 |
| 2 | reach-v3 | [-1, -1, 1, -1] | True | True | 3 / 4 |
| 2 | door-open-v3 | [1, -1, 1, 1] | True | True | 3 / 4 |
| 3 | push-v3 | [-1, 0, -1, -1] | True | False | 3 / 3 |
| 3 | reach-v3 | [1, 1, -1, -1] | True | True | 0 / 4 |
| 3 | door-open-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 4 | push-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 4 | reach-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 4 | door-open-v3 | [1, 1, 1, -1] | True | True | 3 / 4 |
| 5 | push-v3 | [-1, -1, 0, -1] | True | False | 3 / 3 |
| 5 | reach-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 5 | door-open-v3 | [0, 0, -1, -1] | True | False | 2 / 2 |
| 6 | push-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 6 | reach-v3 | [-1, -1, 1, 0] | True | True | 0 / 1 |
| 6 | door-open-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 7 | push-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 7 | reach-v3 | [-1, -1, -1, -1] | True | False | 4 / 4 |
| 7 | door-open-v3 | [1, -1, 1, 1] | True | True | 3 / 4 |

## 完整分层

| 方法 | 分层 | 成功 / 分母 | 停止 | 平均截止损失 |
|---|---|---|---:|---:|
| GAUSS16_CYCLE | replicate:0 | 23 / 24 | 0 | 103.7500 |
| GAUSS16_CYCLE | replicate:1 | 23 / 24 | 0 | 105.8750 |
| GAUSS16_CYCLE | replicate:2 | 24 / 24 | 0 | 89.5000 |
| GAUSS16_CYCLE | replicate:3 | 23 / 24 | 0 | 102.8750 |
| GAUSS16_CYCLE | stream:0 | 12 / 12 | 0 | 90.6667 |
| GAUSS16_CYCLE | stream:1 | 12 / 12 | 0 | 86.9167 |
| GAUSS16_CYCLE | stream:2 | 12 / 12 | 0 | 100.3333 |
| GAUSS16_CYCLE | stream:3 | 12 / 12 | 0 | 82.5000 |
| GAUSS16_CYCLE | stream:4 | 12 / 12 | 0 | 78.5000 |
| GAUSS16_CYCLE | stream:5 | 9 / 12 | 0 | 191.2500 |
| GAUSS16_CYCLE | stream:6 | 12 / 12 | 0 | 89.6667 |
| GAUSS16_CYCLE | stream:7 | 12 / 12 | 0 | 84.1667 |
| GAUSS16_CYCLE | task:door-open-v3 | 29 / 32 | 0 | 159.3750 |
| GAUSS16_CYCLE | task:push-v3 | 32 / 32 | 0 | 73.5000 |
| GAUSS16_CYCLE | task:reach-v3 | 32 / 32 | 0 | 68.6250 |
| GAUSS8 | replicate:0 | 23 / 24 | 0 | 99.3750 |
| GAUSS8 | replicate:1 | 22 / 24 | 0 | 114.1250 |
| GAUSS8 | replicate:2 | 23 / 24 | 0 | 97.2500 |
| GAUSS8 | replicate:3 | 24 / 24 | 0 | 79.7917 |
| GAUSS8 | stream:0 | 12 / 12 | 0 | 85.9167 |
| GAUSS8 | stream:1 | 12 / 12 | 0 | 74.5000 |
| GAUSS8 | stream:2 | 12 / 12 | 0 | 91.5833 |
| GAUSS8 | stream:3 | 11 / 12 | 0 | 112.2500 |
| GAUSS8 | stream:4 | 12 / 12 | 0 | 72.8333 |
| GAUSS8 | stream:5 | 9 / 12 | 0 | 186.8333 |
| GAUSS8 | stream:6 | 12 / 12 | 0 | 81.3333 |
| GAUSS8 | stream:7 | 12 / 12 | 0 | 75.8333 |
| GAUSS8 | task:door-open-v3 | 30 / 32 | 0 | 138.3750 |
| GAUSS8 | task:push-v3 | 31 / 32 | 0 | 80.5625 |
| GAUSS8 | task:reach-v3 | 31 / 32 | 0 | 73.9688 |
| IVR_GLOBAL16 | replicate:0 | 23 / 24 | 0 | 103.7500 |
| IVR_GLOBAL16 | replicate:1 | 23 / 24 | 0 | 105.8750 |
| IVR_GLOBAL16 | replicate:2 | 24 / 24 | 0 | 89.5000 |
| IVR_GLOBAL16 | replicate:3 | 23 / 24 | 0 | 102.8750 |
| IVR_GLOBAL16 | stream:0 | 12 / 12 | 0 | 90.6667 |
| IVR_GLOBAL16 | stream:1 | 12 / 12 | 0 | 86.9167 |
| IVR_GLOBAL16 | stream:2 | 12 / 12 | 0 | 100.3333 |
| IVR_GLOBAL16 | stream:3 | 12 / 12 | 0 | 82.5000 |
| IVR_GLOBAL16 | stream:4 | 12 / 12 | 0 | 78.5000 |
| IVR_GLOBAL16 | stream:5 | 9 / 12 | 0 | 191.2500 |
| IVR_GLOBAL16 | stream:6 | 12 / 12 | 0 | 89.6667 |
| IVR_GLOBAL16 | stream:7 | 12 / 12 | 0 | 84.1667 |
| IVR_GLOBAL16 | task:door-open-v3 | 29 / 32 | 0 | 159.3750 |
| IVR_GLOBAL16 | task:push-v3 | 32 / 32 | 0 | 73.5000 |
| IVR_GLOBAL16 | task:reach-v3 | 32 / 32 | 0 | 68.6250 |
| IVR_TASK16 | replicate:0 | 24 / 24 | 0 | 89.1667 |
| IVR_TASK16 | replicate:1 | 24 / 24 | 0 | 90.0833 |
| IVR_TASK16 | replicate:2 | 24 / 24 | 0 | 89.2083 |
| IVR_TASK16 | replicate:3 | 23 / 24 | 0 | 101.8750 |
| IVR_TASK16 | stream:0 | 12 / 12 | 0 | 90.4167 |
| IVR_TASK16 | stream:1 | 12 / 12 | 0 | 86.2500 |
| IVR_TASK16 | stream:2 | 12 / 12 | 0 | 100.5000 |
| IVR_TASK16 | stream:3 | 12 / 12 | 0 | 86.5000 |
| IVR_TASK16 | stream:4 | 12 / 12 | 0 | 78.6667 |
| IVR_TASK16 | stream:5 | 11 / 12 | 0 | 125.6667 |
| IVR_TASK16 | stream:6 | 12 / 12 | 0 | 90.1667 |
| IVR_TASK16 | stream:7 | 12 / 12 | 0 | 82.5000 |
| IVR_TASK16 | task:door-open-v3 | 31 / 32 | 0 | 135.6562 |
| IVR_TASK16 | task:push-v3 | 32 / 32 | 0 | 73.0938 |
| IVR_TASK16 | task:reach-v3 | 32 / 32 | 0 | 69.0000 |
| NO_PROBE | replicate:0 | 11 / 24 | 0 | 325.2083 |
| NO_PROBE | replicate:1 | 11 / 24 | 0 | 313.2500 |
| NO_PROBE | replicate:2 | 11 / 24 | 0 | 318.2917 |
| NO_PROBE | replicate:3 | 11 / 24 | 0 | 314.0000 |
| NO_PROBE | stream:0 | 12 / 12 | 0 | 98.0000 |
| NO_PROBE | stream:1 | 0 / 12 | 0 | 500.0000 |
| NO_PROBE | stream:2 | 8 / 12 | 0 | 220.0000 |
| NO_PROBE | stream:3 | 0 / 12 | 0 | 500.0000 |
| NO_PROBE | stream:4 | 12 / 12 | 0 | 67.5000 |
| NO_PROBE | stream:5 | 0 / 12 | 0 | 500.0000 |
| NO_PROBE | stream:6 | 12 / 12 | 0 | 156.0000 |
| NO_PROBE | stream:7 | 0 / 12 | 0 | 500.0000 |
| NO_PROBE | task:door-open-v3 | 16 / 32 | 0 | 304.4062 |
| NO_PROBE | task:push-v3 | 12 / 32 | 0 | 338.5000 |
| NO_PROBE | task:reach-v3 | 16 / 32 | 0 | 310.1562 |
| POINT16_CYCLE | replicate:0 | 22 / 24 | 0 | 118.3750 |
| POINT16_CYCLE | replicate:1 | 23 / 24 | 0 | 103.2083 |
| POINT16_CYCLE | replicate:2 | 24 / 24 | 0 | 86.8750 |
| POINT16_CYCLE | replicate:3 | 23 / 24 | 0 | 101.6250 |
| POINT16_CYCLE | stream:0 | 12 / 12 | 0 | 91.4167 |
| POINT16_CYCLE | stream:1 | 12 / 12 | 0 | 77.0833 |
| POINT16_CYCLE | stream:2 | 11 / 12 | 0 | 130.6667 |
| POINT16_CYCLE | stream:3 | 12 / 12 | 0 | 81.1667 |
| POINT16_CYCLE | stream:4 | 12 / 12 | 0 | 78.1667 |
| POINT16_CYCLE | stream:5 | 9 / 12 | 0 | 190.9167 |
| POINT16_CYCLE | stream:6 | 12 / 12 | 0 | 89.9167 |
| POINT16_CYCLE | stream:7 | 12 / 12 | 0 | 80.8333 |
| POINT16_CYCLE | task:door-open-v3 | 29 / 32 | 0 | 153.3125 |
| POINT16_CYCLE | task:push-v3 | 31 / 32 | 0 | 86.2812 |
| POINT16_CYCLE | task:reach-v3 | 32 / 32 | 0 | 67.9688 |
| POINT16_WIDE | replicate:0 | 23 / 24 | 0 | 104.7083 |
| POINT16_WIDE | replicate:1 | 23 / 24 | 0 | 106.7500 |
| POINT16_WIDE | replicate:2 | 23 / 24 | 0 | 107.6250 |
| POINT16_WIDE | replicate:3 | 23 / 24 | 0 | 103.6250 |
| POINT16_WIDE | stream:0 | 12 / 12 | 0 | 92.7500 |
| POINT16_WIDE | stream:1 | 12 / 12 | 0 | 90.2500 |
| POINT16_WIDE | stream:2 | 12 / 12 | 0 | 101.6667 |
| POINT16_WIDE | stream:3 | 12 / 12 | 0 | 82.7500 |
| POINT16_WIDE | stream:4 | 12 / 12 | 0 | 80.5833 |
| POINT16_WIDE | stream:5 | 8 / 12 | 0 | 219.5000 |
| POINT16_WIDE | stream:6 | 12 / 12 | 0 | 94.6667 |
| POINT16_WIDE | stream:7 | 12 / 12 | 0 | 83.2500 |
| POINT16_WIDE | task:door-open-v3 | 28 / 32 | 0 | 173.1562 |
| POINT16_WIDE | task:push-v3 | 32 / 32 | 0 | 76.9375 |
| POINT16_WIDE | task:reach-v3 | 32 / 32 | 0 | 66.9375 |
| POINT8 | replicate:0 | 20 / 24 | 2 | 145.8333 |
| POINT8 | replicate:1 | 22 / 24 | 0 | 124.4167 |
| POINT8 | replicate:2 | 21 / 24 | 2 | 140.7500 |
| POINT8 | replicate:3 | 23 / 24 | 1 | 99.0833 |
| POINT8 | stream:0 | 11 / 12 | 1 | 156.4167 |
| POINT8 | stream:1 | 12 / 12 | 0 | 70.4167 |
| POINT8 | stream:2 | 6 / 12 | 4 | 286.0833 |
| POINT8 | stream:3 | 11 / 12 | 0 | 110.9167 |
| POINT8 | stream:4 | 12 / 12 | 0 | 82.5833 |
| POINT8 | stream:5 | 10 / 12 | 0 | 157.3333 |
| POINT8 | stream:6 | 12 / 12 | 0 | 80.5833 |
| POINT8 | stream:7 | 12 / 12 | 0 | 75.8333 |
| POINT8 | task:door-open-v3 | 26 / 32 | 2 | 201.6562 |
| POINT8 | task:push-v3 | 30 / 32 | 2 | 93.5312 |
| POINT8 | task:reach-v3 | 30 / 32 | 1 | 87.3750 |

## 全部失败／停止

| 方法 | 流 | 任务 | 重复 | 种子 | 停止 | 实际步 | 截止损失 |
|---|---:|---|---:|---:|---|---:|---:|
| POINT8 | 0 | door-open-v3 | 0 | 11502 | True | 8 | 500 |
| NO_PROBE | 1 | push-v3 | 0 | 11503 | False | 500 | 500 |
| NO_PROBE | 1 | push-v3 | 1 | 11503 | False | 500 | 500 |
| NO_PROBE | 1 | push-v3 | 2 | 11503 | False | 500 | 500 |
| NO_PROBE | 1 | push-v3 | 3 | 11503 | False | 500 | 500 |
| NO_PROBE | 1 | reach-v3 | 0 | 11504 | False | 500 | 500 |
| NO_PROBE | 1 | reach-v3 | 1 | 11504 | False | 500 | 500 |
| NO_PROBE | 1 | reach-v3 | 2 | 11504 | False | 500 | 500 |
| NO_PROBE | 1 | reach-v3 | 3 | 11504 | False | 500 | 500 |
| NO_PROBE | 1 | door-open-v3 | 0 | 11505 | False | 500 | 500 |
| NO_PROBE | 1 | door-open-v3 | 1 | 11505 | False | 500 | 500 |
| NO_PROBE | 1 | door-open-v3 | 2 | 11505 | False | 500 | 500 |
| NO_PROBE | 1 | door-open-v3 | 3 | 11505 | False | 500 | 500 |
| POINT8 | 2 | push-v3 | 0 | 11506 | True | 8 | 500 |
| POINT16_CYCLE | 2 | push-v3 | 0 | 11506 | False | 500 | 500 |
| NO_PROBE | 2 | push-v3 | 0 | 11506 | False | 500 | 500 |
| NO_PROBE | 2 | push-v3 | 1 | 11506 | False | 500 | 500 |
| POINT8 | 2 | push-v3 | 2 | 11506 | True | 8 | 500 |
| NO_PROBE | 2 | push-v3 | 2 | 11506 | False | 500 | 500 |
| NO_PROBE | 2 | push-v3 | 3 | 11506 | False | 500 | 500 |
| POINT8 | 2 | reach-v3 | 2 | 11507 | True | 8 | 500 |
| POINT8 | 2 | door-open-v3 | 0 | 11508 | False | 500 | 500 |
| POINT8 | 2 | door-open-v3 | 2 | 11508 | False | 500 | 500 |
| POINT8 | 2 | door-open-v3 | 3 | 11508 | True | 8 | 500 |
| NO_PROBE | 3 | push-v3 | 0 | 11509 | False | 500 | 500 |
| NO_PROBE | 3 | push-v3 | 1 | 11509 | False | 500 | 500 |
| NO_PROBE | 3 | push-v3 | 2 | 11509 | False | 500 | 500 |
| NO_PROBE | 3 | push-v3 | 3 | 11509 | False | 500 | 500 |
| NO_PROBE | 3 | reach-v3 | 0 | 11510 | False | 500 | 500 |
| POINT8 | 3 | reach-v3 | 1 | 11510 | False | 500 | 500 |
| GAUSS8 | 3 | reach-v3 | 1 | 11510 | False | 500 | 500 |
| NO_PROBE | 3 | reach-v3 | 1 | 11510 | False | 500 | 500 |
| NO_PROBE | 3 | reach-v3 | 2 | 11510 | False | 500 | 500 |
| NO_PROBE | 3 | reach-v3 | 3 | 11510 | False | 500 | 500 |
| NO_PROBE | 3 | door-open-v3 | 0 | 11511 | False | 500 | 500 |
| NO_PROBE | 3 | door-open-v3 | 1 | 11511 | False | 500 | 500 |
| NO_PROBE | 3 | door-open-v3 | 2 | 11511 | False | 500 | 500 |
| NO_PROBE | 3 | door-open-v3 | 3 | 11511 | False | 500 | 500 |
| NO_PROBE | 5 | push-v3 | 0 | 11515 | False | 500 | 500 |
| NO_PROBE | 5 | push-v3 | 1 | 11515 | False | 500 | 500 |
| GAUSS8 | 5 | push-v3 | 2 | 11515 | False | 500 | 500 |
| NO_PROBE | 5 | push-v3 | 2 | 11515 | False | 500 | 500 |
| NO_PROBE | 5 | push-v3 | 3 | 11515 | False | 500 | 500 |
| NO_PROBE | 5 | reach-v3 | 0 | 11516 | False | 500 | 500 |
| NO_PROBE | 5 | reach-v3 | 1 | 11516 | False | 500 | 500 |
| NO_PROBE | 5 | reach-v3 | 2 | 11516 | False | 500 | 500 |
| NO_PROBE | 5 | reach-v3 | 3 | 11516 | False | 500 | 500 |
| POINT8 | 5 | door-open-v3 | 0 | 11517 | False | 500 | 500 |
| POINT16_CYCLE | 5 | door-open-v3 | 0 | 11517 | False | 500 | 500 |
| POINT16_WIDE | 5 | door-open-v3 | 0 | 11517 | False | 500 | 500 |
| GAUSS8 | 5 | door-open-v3 | 0 | 11517 | False | 500 | 500 |
| GAUSS16_CYCLE | 5 | door-open-v3 | 0 | 11517 | False | 500 | 500 |
| IVR_GLOBAL16 | 5 | door-open-v3 | 0 | 11517 | False | 500 | 500 |
| NO_PROBE | 5 | door-open-v3 | 0 | 11517 | False | 500 | 500 |
| POINT8 | 5 | door-open-v3 | 1 | 11517 | False | 500 | 500 |
| POINT16_CYCLE | 5 | door-open-v3 | 1 | 11517 | False | 500 | 500 |
| POINT16_WIDE | 5 | door-open-v3 | 1 | 11517 | False | 500 | 500 |
| GAUSS8 | 5 | door-open-v3 | 1 | 11517 | False | 500 | 500 |
| GAUSS16_CYCLE | 5 | door-open-v3 | 1 | 11517 | False | 500 | 500 |
| IVR_GLOBAL16 | 5 | door-open-v3 | 1 | 11517 | False | 500 | 500 |
| NO_PROBE | 5 | door-open-v3 | 1 | 11517 | False | 500 | 500 |
| POINT16_WIDE | 5 | door-open-v3 | 2 | 11517 | False | 500 | 500 |
| NO_PROBE | 5 | door-open-v3 | 2 | 11517 | False | 500 | 500 |
| POINT16_CYCLE | 5 | door-open-v3 | 3 | 11517 | False | 500 | 500 |
| POINT16_WIDE | 5 | door-open-v3 | 3 | 11517 | False | 500 | 500 |
| GAUSS16_CYCLE | 5 | door-open-v3 | 3 | 11517 | False | 500 | 500 |
| IVR_GLOBAL16 | 5 | door-open-v3 | 3 | 11517 | False | 500 | 500 |
| IVR_TASK16 | 5 | door-open-v3 | 3 | 11517 | False | 500 | 500 |
| NO_PROBE | 5 | door-open-v3 | 3 | 11517 | False | 500 | 500 |
| NO_PROBE | 7 | push-v3 | 0 | 11521 | False | 500 | 500 |
| NO_PROBE | 7 | push-v3 | 1 | 11521 | False | 500 | 500 |
| NO_PROBE | 7 | push-v3 | 2 | 11521 | False | 500 | 500 |
| NO_PROBE | 7 | push-v3 | 3 | 11521 | False | 500 | 500 |
| NO_PROBE | 7 | reach-v3 | 0 | 11522 | False | 500 | 500 |
| NO_PROBE | 7 | reach-v3 | 1 | 11522 | False | 500 | 500 |
| NO_PROBE | 7 | reach-v3 | 2 | 11522 | False | 500 | 500 |
| NO_PROBE | 7 | reach-v3 | 3 | 11522 | False | 500 | 500 |
| NO_PROBE | 7 | door-open-v3 | 0 | 11523 | False | 500 | 500 |
| NO_PROBE | 7 | door-open-v3 | 1 | 11523 | False | 500 | 500 |
| NO_PROBE | 7 | door-open-v3 | 2 | 11523 | False | 500 | 500 |
| NO_PROBE | 7 | door-open-v3 | 3 | 11523 | False | 500 | 500 |

## 全部新增初始化费用

新增登记控制 97,824 次 Env.step，控制初始重置 768 次。顶层重置入口实测 39,168，do_simulation 完成请求帧 20,073,120。

| 生命周期阶段 | 完成重置 | 完成模拟调用 | 完成请求帧 |
|---|---:|---:|---:|
| GOAL_GENERATION | 38400 | 3840000 | 19200000 |
| CONTROLLED_RESET | 768 | 76800 | 384000 |
| CONTROL | 0 | 97824 | 489120 |

临时目标工厂安置与当前在线轨迹的控制初始重置分列，没有探测后重置或 RNG 重播种。请求帧是 Python 模拟入口口径，不是全部 C 引擎计算、渲染或真实机器人费用。旧名义来源的内部初始化不由本轮仪器重新测量。

审计核对选择先于执行、真实注入／连续随机数、逐步政策／程序、全部费用及固定 Git 字节；拟合／Gaussian 数学、声明状态配对与重复公式明确复用。没有重仿真动力学或完整隐状态资格。

标准高斯控制、任务 IVR 或普通早停本身不是本项目的新颖性。主重复性门只支持判断后继研究设计，竞争性方法、独立确认与完整论文仍需完成。
