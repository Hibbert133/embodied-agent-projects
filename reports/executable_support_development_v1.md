# 纠正后执行指令支持：完整中文开发结果

九方法、16 个算子流／三任务／两噪声实现，共 96 单元、864 次真实执行。预登记开发信号未成立；这不构成独立方法确认或算法新颖性。

IVR_EXEC16 将名义原政策指令经过当前有界纠正器，再对实际会发送的命令计算 IVR。IVR_EXEC_FIXED16 只在第八步映射一次，之后仅更新评分矩与最终控制器。两者都不是完整未来任务价值规划，也没有新停止规则。

运行 `executable_support_20261015T082955Z_48a3e433af85`；冻结源 `48a3e433af851fb8d477086bf508d072c02cdecd`；清单 `89e843c795d56e06577fa29504366d7023821180f850f0ecc608e84aaf349b78`。新种子 11800–11847；11848–12199 及全部旧保留种子未执行。API、自然经验记忆和策略权重更新为零。

[冻结协议](../docs/protocols/executable_support_development_v1.md) · [机制与原始文献边界](../docs/research/executable_support_mechanism_v1.md) · [执行审计](../outputs/executable_support/analysis_v1/audit.json) · [清单与原始数据](../outputs/executable_support/development_v1/executable_support_20261015T082955Z_48a3e433af85/manifest.json)

## 完整方法比较

每方法完整分母 96。截止损失为成功的实际总步，失败／停止取 500。停止保持失败分母，真实步另外报告。

| 方法 | 成功 / 96 | 停止 | 平均在线步 | 平均探测步 | 平均截止损失 | 含完整来源平均步 | 点逆无效检查 |
|---|---:|---:|---:|---:|---:|---:|---:|
| GAUSS8 | 96 | 0 | 86.1354 | 8.0000 | 86.1354 | 304.9896 | 2 |
| POINT16_CYCLE | 96 | 0 | 88.3542 | 16.0000 | 88.3542 | 307.2083 | 0 |
| POINT16_WIDE | 96 | 0 | 89.8125 | 16.0000 | 89.8125 | 308.6667 | 0 |
| GAUSS16_CYCLE | 95 | 0 | 92.3438 | 16.0000 | 92.3438 | 311.1979 | 0 |
| IVR_GLOBAL16 | 95 | 0 | 92.3438 | 16.0000 | 92.3438 | 311.1979 | 2 |
| IVR_TASK16 | 95 | 0 | 91.0521 | 16.0000 | 91.0521 | 309.9062 | 3 |
| IVR_EXEC16 | 95 | 0 | 90.8646 | 16.0000 | 90.8646 | 309.7188 | 2 |
| IVR_EXEC_FIXED16 | 95 | 0 | 91.0521 | 16.0000 | 91.0521 | 309.9062 | 2 |
| NO_PROBE | 35 | 0 | 352.1458 | 0.0000 | 352.1458 | 352.1458 | 0 |

全部八个名义模型方法完整承担旧 21,010 步／288 次控制重置，按 96 单元摊销为218.8542 步／3 次重置；物理来源只采集一次。点逆无效检查不等于无有限参数或 Gaussian 停止数。

## 候选减各对照的配对差

先在每流内平均三任务／两噪声，再在反射／非反射各八流内重采样。主比较为 IVR_EXEC16 对 IVR_TASK16；其余为已登记次级描述，不能更换主比较。区间为 10,000 次算子流分层配对 bootstrap 百分位 95% 区间，条件于固定名义来源和生成域。

| 对照 | 成功率差及区间 | 截止损失差及区间 | 实际步差及区间 |
|---|---|---|---|
| GAUSS8 | -0.0104 [-0.0312, 0.0000] | 4.7292 [-5.1042, 15.8766] | 4.7292 [-5.1042, 15.8766] |
| POINT16_CYCLE | -0.0104 [-0.0312, 0.0000] | 2.5104 [-3.6667, 11.6979] | 2.5104 [-3.6667, 11.6979] |
| POINT16_WIDE | -0.0104 [-0.0312, 0.0000] | 1.0521 [-4.9794, 10.7708] | 1.0521 [-4.9794, 10.7708] |
| GAUSS16_CYCLE | 0.0000 [0.0000, 0.0000] | -1.4792 [-3.1146, -0.2604] | -1.4792 [-3.1146, -0.2604] |
| IVR_GLOBAL16 | 0.0000 [0.0000, 0.0000] | -1.4792 [-3.1146, -0.2604] | -1.4792 [-3.1146, -0.2604] |
| IVR_TASK16 | 0.0000 [0.0000, 0.0000] | -0.1875 [-0.8125, 0.4167] | -0.1875 [-0.8125, 0.4167] |
| IVR_EXEC_FIXED16 | 0.0000 [0.0000, 0.0000] | -0.1875 [-0.6146, 0.0833] | -0.1875 [-0.6146, 0.0833] |
| NO_PROBE | 0.6250 [0.5312, 0.7292] | -261.2812 [-302.1701, -222.5409] | -261.2812 [-302.1701, -222.5409] |

## 预登记开发信号与实际程序

| 指标 | 值 |
|---|---|
| matched_initial_eight | 96 |
| required_pairs | 96 |
| primary_loss_interval_upper | 0.4166666666666667 |
| dominated_by | ['GAUSS8', 'POINT16_CYCLE', 'POINT16_WIDE'] |
| candidate_success_no_lower | True |
| selected_sequence_differences | 57 |
| passed | False |

| 方法 | 已保存并执行的两次四步程序序列 | 案例数 |
|---|---|---:|
| IVR_GLOBAL16 | X4/Y4 | 96 |
| IVR_TASK16 | Y4/X4 | 22 |
| IVR_TASK16 | Y4/Y4 | 32 |
| IVR_TASK16 | X4/X4 | 24 |
| IVR_TASK16 | X4/Y4 | 18 |
| IVR_EXEC16 | X4/Y4 | 60 |
| IVR_EXEC16 | X4/X4 | 19 |
| IVR_EXEC16 | Y4/X4 | 14 |
| IVR_EXEC16 | Y4/Y4 | 3 |
| IVR_EXEC_FIXED16 | X4/Y4 | 59 |
| IVR_EXEC_FIXED16 | X4/X4 | 20 |
| IVR_EXEC_FIXED16 | Y4/X4 | 13 |
| IVR_EXEC_FIXED16 | Y4/Y4 | 4 |

## 全部分层

| 方法 | 分层 | 成功 / 分母 | 停止 | 平均截止损失 |
|---|---|---|---:|---:|
| GAUSS16_CYCLE | replicate:0 | 47 / 48 | 0 | 96.0000 |
| GAUSS16_CYCLE | replicate:1 | 48 / 48 | 0 | 88.6875 |
| GAUSS16_CYCLE | stream:0 | 6 / 6 | 0 | 92.3333 |
| GAUSS16_CYCLE | stream:1 | 6 / 6 | 0 | 79.5000 |
| GAUSS16_CYCLE | stream:10 | 6 / 6 | 0 | 78.8333 |
| GAUSS16_CYCLE | stream:11 | 5 / 6 | 0 | 147.5000 |
| GAUSS16_CYCLE | stream:12 | 6 / 6 | 0 | 84.5000 |
| GAUSS16_CYCLE | stream:13 | 6 / 6 | 0 | 83.3333 |
| GAUSS16_CYCLE | stream:14 | 6 / 6 | 0 | 90.6667 |
| GAUSS16_CYCLE | stream:15 | 6 / 6 | 0 | 82.3333 |
| GAUSS16_CYCLE | stream:2 | 6 / 6 | 0 | 84.6667 |
| GAUSS16_CYCLE | stream:3 | 6 / 6 | 0 | 95.0000 |
| GAUSS16_CYCLE | stream:4 | 6 / 6 | 0 | 93.3333 |
| GAUSS16_CYCLE | stream:5 | 6 / 6 | 0 | 114.1667 |
| GAUSS16_CYCLE | stream:6 | 6 / 6 | 0 | 79.8333 |
| GAUSS16_CYCLE | stream:7 | 6 / 6 | 0 | 83.3333 |
| GAUSS16_CYCLE | stream:8 | 6 / 6 | 0 | 89.8333 |
| GAUSS16_CYCLE | stream:9 | 6 / 6 | 0 | 98.3333 |
| GAUSS16_CYCLE | task:door-open-v3 | 32 / 32 | 0 | 118.1562 |
| GAUSS16_CYCLE | task:push-v3 | 31 / 32 | 0 | 91.8438 |
| GAUSS16_CYCLE | task:reach-v3 | 32 / 32 | 0 | 67.0312 |
| GAUSS8 | replicate:0 | 48 / 48 | 0 | 82.6042 |
| GAUSS8 | replicate:1 | 48 / 48 | 0 | 89.6667 |
| GAUSS8 | stream:0 | 6 / 6 | 0 | 87.6667 |
| GAUSS8 | stream:1 | 6 / 6 | 0 | 72.3333 |
| GAUSS8 | stream:10 | 6 / 6 | 0 | 123.3333 |
| GAUSS8 | stream:11 | 6 / 6 | 0 | 72.8333 |
| GAUSS8 | stream:12 | 6 / 6 | 0 | 76.3333 |
| GAUSS8 | stream:13 | 6 / 6 | 0 | 79.1667 |
| GAUSS8 | stream:14 | 6 / 6 | 0 | 100.3333 |
| GAUSS8 | stream:15 | 6 / 6 | 0 | 76.0000 |
| GAUSS8 | stream:2 | 6 / 6 | 0 | 73.1667 |
| GAUSS8 | stream:3 | 6 / 6 | 0 | 83.5000 |
| GAUSS8 | stream:4 | 6 / 6 | 0 | 75.5000 |
| GAUSS8 | stream:5 | 6 / 6 | 0 | 106.1667 |
| GAUSS8 | stream:6 | 6 / 6 | 0 | 84.3333 |
| GAUSS8 | stream:7 | 6 / 6 | 0 | 76.3333 |
| GAUSS8 | stream:8 | 6 / 6 | 0 | 97.3333 |
| GAUSS8 | stream:9 | 6 / 6 | 0 | 93.8333 |
| GAUSS8 | task:door-open-v3 | 32 / 32 | 0 | 115.4062 |
| GAUSS8 | task:push-v3 | 32 / 32 | 0 | 80.4062 |
| GAUSS8 | task:reach-v3 | 32 / 32 | 0 | 62.5938 |
| IVR_EXEC16 | replicate:0 | 47 / 48 | 0 | 94.8333 |
| IVR_EXEC16 | replicate:1 | 48 / 48 | 0 | 86.8958 |
| IVR_EXEC16 | stream:0 | 6 / 6 | 0 | 92.3333 |
| IVR_EXEC16 | stream:1 | 6 / 6 | 0 | 79.1667 |
| IVR_EXEC16 | stream:10 | 6 / 6 | 0 | 77.6667 |
| IVR_EXEC16 | stream:11 | 5 / 6 | 0 | 149.3333 |
| IVR_EXEC16 | stream:12 | 6 / 6 | 0 | 84.5000 |
| IVR_EXEC16 | stream:13 | 6 / 6 | 0 | 82.5000 |
| IVR_EXEC16 | stream:14 | 6 / 6 | 0 | 88.6667 |
| IVR_EXEC16 | stream:15 | 6 / 6 | 0 | 82.3333 |
| IVR_EXEC16 | stream:2 | 6 / 6 | 0 | 84.6667 |
| IVR_EXEC16 | stream:3 | 6 / 6 | 0 | 95.3333 |
| IVR_EXEC16 | stream:4 | 6 / 6 | 0 | 92.5000 |
| IVR_EXEC16 | stream:5 | 6 / 6 | 0 | 112.1667 |
| IVR_EXEC16 | stream:6 | 6 / 6 | 0 | 74.1667 |
| IVR_EXEC16 | stream:7 | 6 / 6 | 0 | 81.6667 |
| IVR_EXEC16 | stream:8 | 6 / 6 | 0 | 89.8333 |
| IVR_EXEC16 | stream:9 | 6 / 6 | 0 | 87.0000 |
| IVR_EXEC16 | task:door-open-v3 | 32 / 32 | 0 | 114.4375 |
| IVR_EXEC16 | task:push-v3 | 31 / 32 | 0 | 91.5625 |
| IVR_EXEC16 | task:reach-v3 | 32 / 32 | 0 | 66.5938 |
| IVR_EXEC_FIXED16 | replicate:0 | 47 / 48 | 0 | 94.7708 |
| IVR_EXEC_FIXED16 | replicate:1 | 48 / 48 | 0 | 87.3333 |
| IVR_EXEC_FIXED16 | stream:0 | 6 / 6 | 0 | 92.3333 |
| IVR_EXEC_FIXED16 | stream:1 | 6 / 6 | 0 | 78.5000 |
| IVR_EXEC_FIXED16 | stream:10 | 6 / 6 | 0 | 78.1667 |
| IVR_EXEC_FIXED16 | stream:11 | 5 / 6 | 0 | 149.3333 |
| IVR_EXEC_FIXED16 | stream:12 | 6 / 6 | 0 | 84.5000 |
| IVR_EXEC_FIXED16 | stream:13 | 6 / 6 | 0 | 82.5000 |
| IVR_EXEC_FIXED16 | stream:14 | 6 / 6 | 0 | 88.6667 |
| IVR_EXEC_FIXED16 | stream:15 | 6 / 6 | 0 | 82.3333 |
| IVR_EXEC_FIXED16 | stream:2 | 6 / 6 | 0 | 84.6667 |
| IVR_EXEC_FIXED16 | stream:3 | 6 / 6 | 0 | 95.3333 |
| IVR_EXEC_FIXED16 | stream:4 | 6 / 6 | 0 | 92.5000 |
| IVR_EXEC_FIXED16 | stream:5 | 6 / 6 | 0 | 112.1667 |
| IVR_EXEC_FIXED16 | stream:6 | 6 / 6 | 0 | 74.1667 |
| IVR_EXEC_FIXED16 | stream:7 | 6 / 6 | 0 | 81.6667 |
| IVR_EXEC_FIXED16 | stream:8 | 6 / 6 | 0 | 93.0000 |
| IVR_EXEC_FIXED16 | stream:9 | 6 / 6 | 0 | 87.0000 |
| IVR_EXEC_FIXED16 | task:door-open-v3 | 32 / 32 | 0 | 114.4375 |
| IVR_EXEC_FIXED16 | task:push-v3 | 31 / 32 | 0 | 91.5625 |
| IVR_EXEC_FIXED16 | task:reach-v3 | 32 / 32 | 0 | 67.1562 |
| IVR_GLOBAL16 | replicate:0 | 47 / 48 | 0 | 96.0000 |
| IVR_GLOBAL16 | replicate:1 | 48 / 48 | 0 | 88.6875 |
| IVR_GLOBAL16 | stream:0 | 6 / 6 | 0 | 92.3333 |
| IVR_GLOBAL16 | stream:1 | 6 / 6 | 0 | 79.5000 |
| IVR_GLOBAL16 | stream:10 | 6 / 6 | 0 | 78.8333 |
| IVR_GLOBAL16 | stream:11 | 5 / 6 | 0 | 147.5000 |
| IVR_GLOBAL16 | stream:12 | 6 / 6 | 0 | 84.5000 |
| IVR_GLOBAL16 | stream:13 | 6 / 6 | 0 | 83.3333 |
| IVR_GLOBAL16 | stream:14 | 6 / 6 | 0 | 90.6667 |
| IVR_GLOBAL16 | stream:15 | 6 / 6 | 0 | 82.3333 |
| IVR_GLOBAL16 | stream:2 | 6 / 6 | 0 | 84.6667 |
| IVR_GLOBAL16 | stream:3 | 6 / 6 | 0 | 95.0000 |
| IVR_GLOBAL16 | stream:4 | 6 / 6 | 0 | 93.3333 |
| IVR_GLOBAL16 | stream:5 | 6 / 6 | 0 | 114.1667 |
| IVR_GLOBAL16 | stream:6 | 6 / 6 | 0 | 79.8333 |
| IVR_GLOBAL16 | stream:7 | 6 / 6 | 0 | 83.3333 |
| IVR_GLOBAL16 | stream:8 | 6 / 6 | 0 | 89.8333 |
| IVR_GLOBAL16 | stream:9 | 6 / 6 | 0 | 98.3333 |
| IVR_GLOBAL16 | task:door-open-v3 | 32 / 32 | 0 | 118.1562 |
| IVR_GLOBAL16 | task:push-v3 | 31 / 32 | 0 | 91.8438 |
| IVR_GLOBAL16 | task:reach-v3 | 32 / 32 | 0 | 67.0312 |
| IVR_TASK16 | replicate:0 | 47 / 48 | 0 | 94.9583 |
| IVR_TASK16 | replicate:1 | 48 / 48 | 0 | 87.1458 |
| IVR_TASK16 | stream:0 | 6 / 6 | 0 | 92.1667 |
| IVR_TASK16 | stream:1 | 6 / 6 | 0 | 77.0000 |
| IVR_TASK16 | stream:10 | 6 / 6 | 0 | 80.0000 |
| IVR_TASK16 | stream:11 | 5 / 6 | 0 | 149.1667 |
| IVR_TASK16 | stream:12 | 6 / 6 | 0 | 82.8333 |
| IVR_TASK16 | stream:13 | 6 / 6 | 0 | 84.3333 |
| IVR_TASK16 | stream:14 | 6 / 6 | 0 | 90.3333 |
| IVR_TASK16 | stream:15 | 6 / 6 | 0 | 83.0000 |
| IVR_TASK16 | stream:2 | 6 / 6 | 0 | 84.1667 |
| IVR_TASK16 | stream:3 | 6 / 6 | 0 | 94.5000 |
| IVR_TASK16 | stream:4 | 6 / 6 | 0 | 91.8333 |
| IVR_TASK16 | stream:5 | 6 / 6 | 0 | 112.1667 |
| IVR_TASK16 | stream:6 | 6 / 6 | 0 | 75.1667 |
| IVR_TASK16 | stream:7 | 6 / 6 | 0 | 81.0000 |
| IVR_TASK16 | stream:8 | 6 / 6 | 0 | 92.1667 |
| IVR_TASK16 | stream:9 | 6 / 6 | 0 | 87.0000 |
| IVR_TASK16 | task:door-open-v3 | 32 / 32 | 0 | 115.5000 |
| IVR_TASK16 | task:push-v3 | 31 / 32 | 0 | 91.0312 |
| IVR_TASK16 | task:reach-v3 | 32 / 32 | 0 | 66.6250 |
| NO_PROBE | replicate:0 | 17 / 48 | 0 | 357.0000 |
| NO_PROBE | replicate:1 | 18 / 48 | 0 | 347.2917 |
| NO_PROBE | stream:0 | 6 / 6 | 0 | 94.1667 |
| NO_PROBE | stream:1 | 0 / 6 | 0 | 500.0000 |
| NO_PROBE | stream:10 | 3 / 6 | 0 | 290.3333 |
| NO_PROBE | stream:11 | 0 / 6 | 0 | 500.0000 |
| NO_PROBE | stream:12 | 6 / 6 | 0 | 97.5000 |
| NO_PROBE | stream:13 | 0 / 6 | 0 | 500.0000 |
| NO_PROBE | stream:14 | 4 / 6 | 0 | 226.6667 |
| NO_PROBE | stream:15 | 0 / 6 | 0 | 500.0000 |
| NO_PROBE | stream:2 | 6 / 6 | 0 | 133.6667 |
| NO_PROBE | stream:3 | 0 / 6 | 0 | 500.0000 |
| NO_PROBE | stream:4 | 2 / 6 | 0 | 362.1667 |
| NO_PROBE | stream:5 | 0 / 6 | 0 | 500.0000 |
| NO_PROBE | stream:6 | 6 / 6 | 0 | 65.0000 |
| NO_PROBE | stream:7 | 0 / 6 | 0 | 500.0000 |
| NO_PROBE | stream:8 | 2 / 6 | 0 | 364.8333 |
| NO_PROBE | stream:9 | 0 / 6 | 0 | 500.0000 |
| NO_PROBE | task:door-open-v3 | 16 / 32 | 0 | 301.4062 |
| NO_PROBE | task:push-v3 | 11 / 32 | 0 | 355.1562 |
| NO_PROBE | task:reach-v3 | 8 / 32 | 0 | 399.8750 |
| POINT16_CYCLE | replicate:0 | 48 / 48 | 0 | 89.1250 |
| POINT16_CYCLE | replicate:1 | 48 / 48 | 0 | 87.5833 |
| POINT16_CYCLE | stream:0 | 6 / 6 | 0 | 92.1667 |
| POINT16_CYCLE | stream:1 | 6 / 6 | 0 | 79.1667 |
| POINT16_CYCLE | stream:10 | 6 / 6 | 0 | 79.3333 |
| POINT16_CYCLE | stream:11 | 6 / 6 | 0 | 85.5000 |
| POINT16_CYCLE | stream:12 | 6 / 6 | 0 | 84.3333 |
| POINT16_CYCLE | stream:13 | 6 / 6 | 0 | 82.8333 |
| POINT16_CYCLE | stream:14 | 6 / 6 | 0 | 107.1667 |
| POINT16_CYCLE | stream:15 | 6 / 6 | 0 | 81.8333 |
| POINT16_CYCLE | stream:2 | 6 / 6 | 0 | 83.8333 |
| POINT16_CYCLE | stream:3 | 6 / 6 | 0 | 93.5000 |
| POINT16_CYCLE | stream:4 | 6 / 6 | 0 | 88.0000 |
| POINT16_CYCLE | stream:5 | 6 / 6 | 0 | 114.3333 |
| POINT16_CYCLE | stream:6 | 6 / 6 | 0 | 75.1667 |
| POINT16_CYCLE | stream:7 | 6 / 6 | 0 | 79.8333 |
| POINT16_CYCLE | stream:8 | 6 / 6 | 0 | 89.3333 |
| POINT16_CYCLE | stream:9 | 6 / 6 | 0 | 97.3333 |
| POINT16_CYCLE | task:door-open-v3 | 32 / 32 | 0 | 118.2500 |
| POINT16_CYCLE | task:push-v3 | 32 / 32 | 0 | 80.0938 |
| POINT16_CYCLE | task:reach-v3 | 32 / 32 | 0 | 66.7188 |
| POINT16_WIDE | replicate:0 | 48 / 48 | 0 | 89.7917 |
| POINT16_WIDE | replicate:1 | 48 / 48 | 0 | 89.8333 |
| POINT16_WIDE | stream:0 | 6 / 6 | 0 | 97.1667 |
| POINT16_WIDE | stream:1 | 6 / 6 | 0 | 82.0000 |
| POINT16_WIDE | stream:10 | 6 / 6 | 0 | 83.0000 |
| POINT16_WIDE | stream:11 | 6 / 6 | 0 | 81.1667 |
| POINT16_WIDE | stream:12 | 6 / 6 | 0 | 84.5000 |
| POINT16_WIDE | stream:13 | 6 / 6 | 0 | 87.6667 |
| POINT16_WIDE | stream:14 | 6 / 6 | 0 | 89.8333 |
| POINT16_WIDE | stream:15 | 6 / 6 | 0 | 85.6667 |
| POINT16_WIDE | stream:2 | 6 / 6 | 0 | 89.3333 |
| POINT16_WIDE | stream:3 | 6 / 6 | 0 | 96.3333 |
| POINT16_WIDE | stream:4 | 6 / 6 | 0 | 87.8333 |
| POINT16_WIDE | stream:5 | 6 / 6 | 0 | 112.1667 |
| POINT16_WIDE | stream:6 | 6 / 6 | 0 | 87.5000 |
| POINT16_WIDE | stream:7 | 6 / 6 | 0 | 84.8333 |
| POINT16_WIDE | stream:8 | 6 / 6 | 0 | 90.6667 |
| POINT16_WIDE | stream:9 | 6 / 6 | 0 | 97.3333 |
| POINT16_WIDE | task:door-open-v3 | 32 / 32 | 0 | 120.8125 |
| POINT16_WIDE | task:push-v3 | 32 / 32 | 0 | 81.4688 |
| POINT16_WIDE | task:reach-v3 | 32 / 32 | 0 | 67.1562 |

## 全部失败与停止

| 方法 | 流 | 任务 | 重复 | 种子 | 停止 | 实际步 |
|---|---:|---|---:|---:|---|---:|
| NO_PROBE | 1 | push-v3 | 0 | 11803 | False | 500 |
| NO_PROBE | 1 | push-v3 | 1 | 11803 | False | 500 |
| NO_PROBE | 1 | reach-v3 | 0 | 11804 | False | 500 |
| NO_PROBE | 1 | reach-v3 | 1 | 11804 | False | 500 |
| NO_PROBE | 1 | door-open-v3 | 0 | 11805 | False | 500 |
| NO_PROBE | 1 | door-open-v3 | 1 | 11805 | False | 500 |
| NO_PROBE | 3 | push-v3 | 0 | 11809 | False | 500 |
| NO_PROBE | 3 | push-v3 | 1 | 11809 | False | 500 |
| NO_PROBE | 3 | reach-v3 | 0 | 11810 | False | 500 |
| NO_PROBE | 3 | reach-v3 | 1 | 11810 | False | 500 |
| NO_PROBE | 3 | door-open-v3 | 0 | 11811 | False | 500 |
| NO_PROBE | 3 | door-open-v3 | 1 | 11811 | False | 500 |
| NO_PROBE | 4 | push-v3 | 0 | 11812 | False | 500 |
| NO_PROBE | 4 | push-v3 | 1 | 11812 | False | 500 |
| NO_PROBE | 4 | reach-v3 | 0 | 11813 | False | 500 |
| NO_PROBE | 4 | reach-v3 | 1 | 11813 | False | 500 |
| NO_PROBE | 5 | push-v3 | 0 | 11815 | False | 500 |
| NO_PROBE | 5 | push-v3 | 1 | 11815 | False | 500 |
| NO_PROBE | 5 | reach-v3 | 0 | 11816 | False | 500 |
| NO_PROBE | 5 | reach-v3 | 1 | 11816 | False | 500 |
| NO_PROBE | 5 | door-open-v3 | 0 | 11817 | False | 500 |
| NO_PROBE | 5 | door-open-v3 | 1 | 11817 | False | 500 |
| NO_PROBE | 7 | push-v3 | 0 | 11821 | False | 500 |
| NO_PROBE | 7 | push-v3 | 1 | 11821 | False | 500 |
| NO_PROBE | 7 | reach-v3 | 0 | 11822 | False | 500 |
| NO_PROBE | 7 | reach-v3 | 1 | 11822 | False | 500 |
| NO_PROBE | 7 | door-open-v3 | 0 | 11823 | False | 500 |
| NO_PROBE | 7 | door-open-v3 | 1 | 11823 | False | 500 |
| NO_PROBE | 8 | push-v3 | 0 | 11824 | False | 500 |
| NO_PROBE | 8 | push-v3 | 1 | 11824 | False | 500 |
| NO_PROBE | 8 | reach-v3 | 0 | 11825 | False | 500 |
| NO_PROBE | 8 | reach-v3 | 1 | 11825 | False | 500 |
| NO_PROBE | 9 | push-v3 | 0 | 11827 | False | 500 |
| NO_PROBE | 9 | push-v3 | 1 | 11827 | False | 500 |
| NO_PROBE | 9 | reach-v3 | 0 | 11828 | False | 500 |
| NO_PROBE | 9 | reach-v3 | 1 | 11828 | False | 500 |
| NO_PROBE | 9 | door-open-v3 | 0 | 11829 | False | 500 |
| NO_PROBE | 9 | door-open-v3 | 1 | 11829 | False | 500 |
| NO_PROBE | 10 | push-v3 | 0 | 11830 | False | 500 |
| NO_PROBE | 10 | reach-v3 | 0 | 11831 | False | 500 |
| NO_PROBE | 10 | reach-v3 | 1 | 11831 | False | 500 |
| GAUSS16_CYCLE | 11 | push-v3 | 0 | 11833 | False | 500 |
| IVR_GLOBAL16 | 11 | push-v3 | 0 | 11833 | False | 500 |
| IVR_TASK16 | 11 | push-v3 | 0 | 11833 | False | 500 |
| IVR_EXEC16 | 11 | push-v3 | 0 | 11833 | False | 500 |
| IVR_EXEC_FIXED16 | 11 | push-v3 | 0 | 11833 | False | 500 |
| NO_PROBE | 11 | push-v3 | 0 | 11833 | False | 500 |
| NO_PROBE | 11 | push-v3 | 1 | 11833 | False | 500 |
| NO_PROBE | 11 | reach-v3 | 0 | 11834 | False | 500 |
| NO_PROBE | 11 | reach-v3 | 1 | 11834 | False | 500 |
| NO_PROBE | 11 | door-open-v3 | 0 | 11835 | False | 500 |
| NO_PROBE | 11 | door-open-v3 | 1 | 11835 | False | 500 |
| NO_PROBE | 13 | push-v3 | 0 | 11839 | False | 500 |
| NO_PROBE | 13 | push-v3 | 1 | 11839 | False | 500 |
| NO_PROBE | 13 | reach-v3 | 0 | 11840 | False | 500 |
| NO_PROBE | 13 | reach-v3 | 1 | 11840 | False | 500 |
| NO_PROBE | 13 | door-open-v3 | 0 | 11841 | False | 500 |
| NO_PROBE | 13 | door-open-v3 | 1 | 11841 | False | 500 |
| NO_PROBE | 14 | reach-v3 | 0 | 11843 | False | 500 |
| NO_PROBE | 14 | reach-v3 | 1 | 11843 | False | 500 |
| NO_PROBE | 15 | push-v3 | 0 | 11845 | False | 500 |
| NO_PROBE | 15 | push-v3 | 1 | 11845 | False | 500 |
| NO_PROBE | 15 | reach-v3 | 0 | 11846 | False | 500 |
| NO_PROBE | 15 | reach-v3 | 1 | 11846 | False | 500 |
| NO_PROBE | 15 | door-open-v3 | 0 | 11847 | False | 500 |
| NO_PROBE | 15 | door-open-v3 | 1 | 11847 | False | 500 |

## 完整新增费用与资格

新增 Env.step 103,114，控制初始重置 864；全部顶层完成重置 44,064，完成 do_simulation 请求帧 22,547,570。

| 阶段 | 完成重置 | 完成模拟调用 | 完成请求帧 |
|---|---:|---:|---:|
| GOAL_GENERATION | 43200 | 4320000 | 21600000 |
| CONTROLLED_RESET | 864 | 86400 | 432000 |
| CONTROL | 0 | 103114 | 515570 |

没有探测后重置、恢复或重播种；每 Env.step 五帧／0.0125 秒。请求帧不是所有 C 引擎计算或真实机器人费用。旧名义来源内部初始化未在本轮重新测量。

审计核对保存选择先于执行、支持映射摘要、逐步政策／程序、实际注入与随机数、全部费用和 Git 字节。Gaussian／点拟合／支持映射数学辅助函数、声明配对与统计公式明确复用，没有动力学重仿真或完整隐状态验证。

查询测度是当前纠正器的名义命令映射，不是未来物体状态或政策占用分布；方差减少不等于任务收益。Gaussian 局部矩、经验 RMS、饱和导数均未获物理、概率或安全资格。

有用的开发信号也不能替代新颖性、独立确认、多故障／变化场景和完整论文。若无信号，保留负结果，不调整本轮映射、超参数或种子。
