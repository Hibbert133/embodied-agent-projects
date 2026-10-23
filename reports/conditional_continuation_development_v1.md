# 固定八步前缀后的继续策略：完整中文测量

本轮不是新在线 Agent 的成功率实验。七个固定分支各自真实执行，评价器随后用同一前缀的其他三个未来结果形成查询表，只在留出未来上评价所选分支。该查询表不可部署，也不是真正条件最优策略的上界。

24 个名义前缀上下文／四未来实现，96 单元、672 次实际执行；主查询表减 DIRECT_G8 的平均截止损失差 -34.4271，算子流分层配对 95% 区间 [-72.6562, -3.9268]。有利结果不证明新颖性或在线收益；无收益也不能证明条件最优策略不存在。

运行 `conditional_continuation_20261015T094531Z_784d65befd08`；冻结源 `784d65befd089da29f002869c38c9936b9b6ee02`；清单 `61d70c7c4fc14b2f0841bb8a549b2d2d320c828e14bd1c5328273b307dbdb46f`。12200–12223 实际执行；12224–12599 和全部旧保留范围未动。

[冻结协议](../docs/protocols/conditional_continuation_development_v1.md) · [问题与既有实验区别](../docs/research/conditional_continuation_question_v1.md) · [执行审计](../outputs/conditional_continuation/analysis_v1/audit.json) · [清单和原始轨迹](../outputs/conditional_continuation/development_v1/conditional_continuation_20261015T094531Z_784d65befd08/manifest.json)

## 全部固定方法

成功取实际总步；失败／停止截止损失取 500，始终保留完整分母。

| 方法 | 成功 / 96 | 停止 | 平均在线步 | 平均专门探测步 | 平均政策观测块步 | 平均截止损失 | 含完整名义来源平均步 |
|---|---:|---:|---:|---:|---:|---:|---:|
| DIRECT_G8 | 85 | 0 | 128.8333 | 8.0000 | 0.0000 | 128.8333 | 347.6875 |
| KEEP_G8_AFTER16 | 86 | 0 | 132.0521 | 16.0000 | 0.0000 | 132.0521 | 350.9062 |
| UPDATE_G16 | 92 | 0 | 103.7917 | 16.0000 | 0.0000 | 103.7917 | 322.6458 |
| POINT16_CYCLE | 92 | 0 | 103.6979 | 16.0000 | 0.0000 | 103.6979 | 322.5521 |
| PASSIVE_G16 | 88 | 0 | 113.2188 | 8.0000 | 8.0000 | 113.2188 | 332.0729 |
| POINT16_WIDE | 92 | 0 | 106.6354 | 16.0000 | 0.0000 | 106.6354 | 325.4896 |
| NO_PROBE | 33 | 0 | 364.5729 | 0.0000 | 0.0000 | 364.5729 | 364.5729 |

DIRECT_G8 为八步后直接控制；KEEP 额外探测后仍保留第八步纠正器；UPDATE 使用十六步数据。PASSIVE 用八步真实任务政策产生自然观测再更新，这些步是任务预算内的政策步，不能重复算成专门探测或免费交互。POINT16_CYCLE 是两次宽八，POINT16_WIDE 是四方向各四步；后者与 NO_PROBE 不属于同八步后的可行决策组合。

六个名义方法各完整承担旧 21,010 步／288 次控制重置，按 96 单元摊销 218.8542 步／3 次重置；物理源只计一次。旧来源内部初始化没有在本轮重新测量。Gaussian 参考、经验 RMS 与局部模型均没有物理／概率／安全资格。

## 固定前缀核查

| 指标 | 结果 |
|---|---:|
| cross_method_pairs | 480 |
| across_future_pairs | 504 |
| contexts | 24 |
| active_contexts | 24 |

独立环境真实重新执行初始八步；只有一次控制初始重置，没有状态复制、恢复或轨迹内重播种。所有噪声在交互前生成，日志的哈希只表示已消费噪声历史；未来噪声承诺是评价器字段，不进拟合。匹配可见前缀和声明见证，不证明所有相同观测隐状态的分布相同。

## 评价器跨未来查询表

该表依赖同一前缀的反事实训练结果，所有真实分支在分析之前已执行。纯选择函数只接收其他三个未来的损失；这不是物理执行前的 Agent 决策或自然在线经验。

| 指标 | 值 |
|---|---|
| cases | 96 |
| decision_required_cases | 96 |
| successes | 92 |
| mean_steps | 94.40625 |
| mean_deadline_loss | 94.40625 |
| mean_probe_steps | 8.25 |
| selected_counts | {'DIRECT_G8': 46, 'PASSIVE_G16': 47, 'POINT16_CYCLE': 0, 'UPDATE_G16': 3, 'KEEP_G8_AFTER16': 0} |
| operator_streams | 8 |
| strata_streams | [4, 4] |
| new_online_lookup_executions | 0 |

| 查询表减 DIRECT_G8 | 点差 | 算子流分层配对 95% 区间 |
|---|---:|---|
| success_rate | 0.0729 | [0.0, 0.16666666666666666] |
| deadline_loss | -34.4271 | [-72.65625, -3.926822916666671] |
| actual_steps | -34.4271 | [-72.65625, -3.926822916666671] |

独立单位为八个算子流，在反射／非反射各四流中重采样。查询表训练与留出重复的依赖都保留在流内；不能把 96 单元当成独立算子，也不能从四未来样本给出逐状态分布保证。

## 全部条件前缀与四未来损失

范围是四次实际结果的范围，不是置信区间。

| 流 | 任务 | 需要继续决策 | 方法 | 四未来截止损失 | 均值 | 比直接八步均值差 | 成功 / 4 |
|---:|---|---|---|---|---:|---:|---|
| 0 | push-v3 | True | DIRECT_G8 | [78, 79, 77, 79] | 78.2500 | 0.0000 | 4 |
| 0 | push-v3 | True | KEEP_G8_AFTER16 | [88, 90, 90, 88] | 89.0000 | 10.7500 | 4 |
| 0 | push-v3 | True | UPDATE_G16 | [89, 90, 91, 87] | 89.2500 | 11.0000 | 4 |
| 0 | push-v3 | True | POINT16_CYCLE | [89, 90, 90, 86] | 88.7500 | 10.5000 | 4 |
| 0 | push-v3 | True | PASSIVE_G16 | [78, 79, 78, 79] | 78.5000 | 0.2500 | 4 |
| 0 | push-v3 | True | POINT16_WIDE | [88, 89, 91, 91] | 89.7500 | 11.5000 | 4 |
| 0 | push-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 421.7500 | 0 |
| 0 | reach-v3 | True | DIRECT_G8 | [75, 83, 83, 77] | 79.5000 | 0.0000 | 4 |
| 0 | reach-v3 | True | KEEP_G8_AFTER16 | [79, 87, 88, 81] | 83.7500 | 4.2500 | 4 |
| 0 | reach-v3 | True | UPDATE_G16 | [77, 79, 81, 77] | 78.5000 | -1.0000 | 4 |
| 0 | reach-v3 | True | POINT16_CYCLE | [77, 79, 81, 77] | 78.5000 | -1.0000 | 4 |
| 0 | reach-v3 | True | PASSIVE_G16 | [68, 75, 68, 67] | 69.5000 | -10.0000 | 4 |
| 0 | reach-v3 | True | POINT16_WIDE | [78, 80, 83, 77] | 79.5000 | 0.0000 | 4 |
| 0 | reach-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 420.5000 | 0 |
| 0 | door-open-v3 | True | DIRECT_G8 | [101, 101, 101, 101] | 101.0000 | 0.0000 | 4 |
| 0 | door-open-v3 | True | KEEP_G8_AFTER16 | [108, 106, 107, 109] | 107.5000 | 6.5000 | 4 |
| 0 | door-open-v3 | True | UPDATE_G16 | [108, 105, 108, 109] | 107.5000 | 6.5000 | 4 |
| 0 | door-open-v3 | True | POINT16_CYCLE | [108, 105, 108, 109] | 107.5000 | 6.5000 | 4 |
| 0 | door-open-v3 | True | PASSIVE_G16 | [101, 101, 101, 101] | 101.0000 | 0.0000 | 4 |
| 0 | door-open-v3 | True | POINT16_WIDE | [110, 107, 107, 108] | 108.0000 | 7.0000 | 4 |
| 0 | door-open-v3 | True | NO_PROBE | [98, 98, 98, 98] | 98.0000 | -3.0000 | 4 |
| 1 | push-v3 | True | DIRECT_G8 | [74, 75, 75, 75] | 74.7500 | 0.0000 | 4 |
| 1 | push-v3 | True | KEEP_G8_AFTER16 | [83, 83, 83, 83] | 83.0000 | 8.2500 | 4 |
| 1 | push-v3 | True | UPDATE_G16 | [81, 83, 84, 83] | 82.7500 | 8.0000 | 4 |
| 1 | push-v3 | True | POINT16_CYCLE | [81, 83, 84, 82] | 82.5000 | 7.7500 | 4 |
| 1 | push-v3 | True | PASSIVE_G16 | [75, 76, 76, 75] | 75.5000 | 0.7500 | 4 |
| 1 | push-v3 | True | POINT16_WIDE | [86, 87, 87, 87] | 86.7500 | 12.0000 | 4 |
| 1 | push-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 425.2500 | 0 |
| 1 | reach-v3 | True | DIRECT_G8 | [48, 47, 49, 48] | 48.0000 | 0.0000 | 4 |
| 1 | reach-v3 | True | KEEP_G8_AFTER16 | [56, 57, 56, 57] | 56.5000 | 8.5000 | 4 |
| 1 | reach-v3 | True | UPDATE_G16 | [58, 59, 59, 59] | 58.7500 | 10.7500 | 4 |
| 1 | reach-v3 | True | POINT16_CYCLE | [57, 57, 58, 58] | 57.5000 | 9.5000 | 4 |
| 1 | reach-v3 | True | PASSIVE_G16 | [40, 40, 40, 40] | 40.0000 | -8.0000 | 4 |
| 1 | reach-v3 | True | POINT16_WIDE | [54, 53, 53, 58] | 54.5000 | 6.5000 | 4 |
| 1 | reach-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 452.0000 | 0 |
| 1 | door-open-v3 | True | DIRECT_G8 | [98, 98, 98, 98] | 98.0000 | 0.0000 | 4 |
| 1 | door-open-v3 | True | KEEP_G8_AFTER16 | [107, 107, 107, 107] | 107.0000 | 9.0000 | 4 |
| 1 | door-open-v3 | True | UPDATE_G16 | [108, 108, 109, 107] | 108.0000 | 10.0000 | 4 |
| 1 | door-open-v3 | True | POINT16_CYCLE | [108, 107, 109, 107] | 107.7500 | 9.7500 | 4 |
| 1 | door-open-v3 | True | PASSIVE_G16 | [98, 99, 99, 99] | 98.7500 | 0.7500 | 4 |
| 1 | door-open-v3 | True | POINT16_WIDE | [118, 116, 117, 117] | 117.0000 | 19.0000 | 4 |
| 1 | door-open-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 402.0000 | 0 |
| 2 | push-v3 | True | DIRECT_G8 | [79, 80, 81, 82] | 80.5000 | 0.0000 | 4 |
| 2 | push-v3 | True | KEEP_G8_AFTER16 | [90, 91, 89, 90] | 90.0000 | 9.5000 | 4 |
| 2 | push-v3 | True | UPDATE_G16 | [84, 84, 83, 83] | 83.5000 | 3.0000 | 4 |
| 2 | push-v3 | True | POINT16_CYCLE | [84, 83, 82, 83] | 83.0000 | 2.5000 | 4 |
| 2 | push-v3 | True | PASSIVE_G16 | [77, 78, 78, 78] | 77.7500 | -2.7500 | 4 |
| 2 | push-v3 | True | POINT16_WIDE | [84, 84, 83, 82] | 83.2500 | 2.7500 | 4 |
| 2 | push-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 419.5000 | 0 |
| 2 | reach-v3 | True | DIRECT_G8 | [75, 78, 116, 83] | 88.0000 | 0.0000 | 4 |
| 2 | reach-v3 | True | KEEP_G8_AFTER16 | [94, 95, 117, 84] | 97.5000 | 9.5000 | 4 |
| 2 | reach-v3 | True | UPDATE_G16 | [71, 71, 74, 73] | 72.2500 | -15.7500 | 4 |
| 2 | reach-v3 | True | POINT16_CYCLE | [70, 71, 74, 72] | 71.7500 | -16.2500 | 4 |
| 2 | reach-v3 | True | PASSIVE_G16 | [66, 69, 71, 62] | 67.0000 | -21.0000 | 4 |
| 2 | reach-v3 | True | POINT16_WIDE | [75, 74, 96, 80] | 81.2500 | -6.7500 | 4 |
| 2 | reach-v3 | True | NO_PROBE | [131, 105, 106, 128] | 117.5000 | 29.5000 | 4 |
| 2 | door-open-v3 | True | DIRECT_G8 | [104, 107, 108, 103] | 105.5000 | 0.0000 | 4 |
| 2 | door-open-v3 | True | KEEP_G8_AFTER16 | [113, 114, 114, 112] | 113.2500 | 7.7500 | 4 |
| 2 | door-open-v3 | True | UPDATE_G16 | [115, 112, 115, 109] | 112.7500 | 7.2500 | 4 |
| 2 | door-open-v3 | True | POINT16_CYCLE | [115, 113, 115, 113] | 114.0000 | 8.5000 | 4 |
| 2 | door-open-v3 | True | PASSIVE_G16 | [106, 106, 107, 106] | 106.2500 | 0.7500 | 4 |
| 2 | door-open-v3 | True | POINT16_WIDE | [117, 115, 118, 116] | 116.5000 | 11.0000 | 4 |
| 2 | door-open-v3 | True | NO_PROBE | [100, 99, 100, 99] | 99.5000 | -6.0000 | 4 |
| 3 | push-v3 | True | DIRECT_G8 | [500, 500, 500, 500] | 500.0000 | 0.0000 | 0 |
| 3 | push-v3 | True | KEEP_G8_AFTER16 | [500, 500, 500, 90] | 397.5000 | -102.5000 | 1 |
| 3 | push-v3 | True | UPDATE_G16 | [84, 85, 85, 85] | 84.7500 | -415.2500 | 4 |
| 3 | push-v3 | True | POINT16_CYCLE | [83, 84, 85, 84] | 84.0000 | -416.0000 | 4 |
| 3 | push-v3 | True | PASSIVE_G16 | [78, 77, 78, 78] | 77.7500 | -422.2500 | 4 |
| 3 | push-v3 | True | POINT16_WIDE | [86, 87, 87, 88] | 87.0000 | -413.0000 | 4 |
| 3 | push-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 0.0000 | 0 |
| 3 | reach-v3 | True | DIRECT_G8 | [69, 72, 64, 64] | 67.2500 | 0.0000 | 4 |
| 3 | reach-v3 | True | KEEP_G8_AFTER16 | [74, 76, 70, 76] | 74.0000 | 6.7500 | 4 |
| 3 | reach-v3 | True | UPDATE_G16 | [75, 81, 82, 78] | 79.0000 | 11.7500 | 4 |
| 3 | reach-v3 | True | POINT16_CYCLE | [75, 80, 82, 78] | 78.7500 | 11.5000 | 4 |
| 3 | reach-v3 | True | PASSIVE_G16 | [67, 67, 62, 60] | 64.0000 | -3.2500 | 4 |
| 3 | reach-v3 | True | POINT16_WIDE | [76, 76, 68, 76] | 74.0000 | 6.7500 | 4 |
| 3 | reach-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 432.7500 | 0 |
| 3 | door-open-v3 | True | DIRECT_G8 | [500, 500, 500, 500] | 500.0000 | 0.0000 | 0 |
| 3 | door-open-v3 | True | KEEP_G8_AFTER16 | [500, 500, 500, 500] | 500.0000 | 0.0000 | 0 |
| 3 | door-open-v3 | True | UPDATE_G16 | [500, 500, 500, 500] | 500.0000 | 0.0000 | 0 |
| 3 | door-open-v3 | True | POINT16_CYCLE | [500, 500, 500, 500] | 500.0000 | 0.0000 | 0 |
| 3 | door-open-v3 | True | PASSIVE_G16 | [500, 500, 500, 500] | 500.0000 | 0.0000 | 0 |
| 3 | door-open-v3 | True | POINT16_WIDE | [500, 500, 500, 500] | 500.0000 | 0.0000 | 0 |
| 3 | door-open-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 0.0000 | 0 |
| 4 | push-v3 | True | DIRECT_G8 | [500, 92, 500, 500] | 398.0000 | 0.0000 | 1 |
| 4 | push-v3 | True | KEEP_G8_AFTER16 | [99, 500, 500, 500] | 399.7500 | 1.7500 | 1 |
| 4 | push-v3 | True | UPDATE_G16 | [91, 92, 90, 92] | 91.2500 | -306.7500 | 4 |
| 4 | push-v3 | True | POINT16_CYCLE | [91, 92, 91, 92] | 91.5000 | -306.5000 | 4 |
| 4 | push-v3 | True | PASSIVE_G16 | [84, 86, 86, 85] | 85.2500 | -312.7500 | 4 |
| 4 | push-v3 | True | POINT16_WIDE | [91, 92, 94, 93] | 92.5000 | -305.5000 | 4 |
| 4 | push-v3 | True | NO_PROBE | [111, 197, 292, 500] | 275.0000 | -123.0000 | 3 |
| 4 | reach-v3 | True | DIRECT_G8 | [56, 57, 55, 59] | 56.7500 | 0.0000 | 4 |
| 4 | reach-v3 | True | KEEP_G8_AFTER16 | [64, 66, 64, 67] | 65.2500 | 8.5000 | 4 |
| 4 | reach-v3 | True | UPDATE_G16 | [66, 62, 60, 67] | 63.7500 | 7.0000 | 4 |
| 4 | reach-v3 | True | POINT16_CYCLE | [65, 61, 59, 65] | 62.5000 | 5.7500 | 4 |
| 4 | reach-v3 | True | PASSIVE_G16 | [53, 52, 51, 55] | 52.7500 | -4.0000 | 4 |
| 4 | reach-v3 | True | POINT16_WIDE | [71, 62, 57, 70] | 65.0000 | 8.2500 | 4 |
| 4 | reach-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 443.2500 | 0 |
| 4 | door-open-v3 | True | DIRECT_G8 | [125, 117, 130, 122] | 123.5000 | 0.0000 | 4 |
| 4 | door-open-v3 | True | KEEP_G8_AFTER16 | [133, 121, 127, 132] | 128.2500 | 4.7500 | 4 |
| 4 | door-open-v3 | True | UPDATE_G16 | [131, 152, 162, 134] | 144.7500 | 21.2500 | 4 |
| 4 | door-open-v3 | True | POINT16_CYCLE | [133, 123, 134, 148] | 134.5000 | 11.0000 | 4 |
| 4 | door-open-v3 | True | PASSIVE_G16 | [126, 116, 118, 124] | 121.0000 | -2.5000 | 4 |
| 4 | door-open-v3 | True | POINT16_WIDE | [131, 122, 126, 132] | 127.7500 | 4.2500 | 4 |
| 4 | door-open-v3 | True | NO_PROBE | [116, 120, 122, 123] | 120.2500 | -3.2500 | 4 |
| 5 | push-v3 | True | DIRECT_G8 | [77, 76, 77, 77] | 76.7500 | 0.0000 | 4 |
| 5 | push-v3 | True | KEEP_G8_AFTER16 | [85, 85, 86, 86] | 85.5000 | 8.7500 | 4 |
| 5 | push-v3 | True | UPDATE_G16 | [81, 82, 85, 81] | 82.2500 | 5.5000 | 4 |
| 5 | push-v3 | True | POINT16_CYCLE | [81, 82, 85, 80] | 82.0000 | 5.2500 | 4 |
| 5 | push-v3 | True | PASSIVE_G16 | [78, 76, 78, 77] | 77.2500 | 0.5000 | 4 |
| 5 | push-v3 | True | POINT16_WIDE | [88, 86, 88, 92] | 88.5000 | 11.7500 | 4 |
| 5 | push-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 423.2500 | 0 |
| 5 | reach-v3 | True | DIRECT_G8 | [84, 83, 87, 84] | 84.5000 | 0.0000 | 4 |
| 5 | reach-v3 | True | KEEP_G8_AFTER16 | [90, 103, 96, 149] | 109.5000 | 25.0000 | 4 |
| 5 | reach-v3 | True | UPDATE_G16 | [76, 70, 73, 74] | 73.2500 | -11.2500 | 4 |
| 5 | reach-v3 | True | POINT16_CYCLE | [74, 69, 72, 73] | 72.0000 | -12.5000 | 4 |
| 5 | reach-v3 | True | PASSIVE_G16 | [54, 53, 55, 55] | 54.2500 | -30.2500 | 4 |
| 5 | reach-v3 | True | POINT16_WIDE | [67, 62, 68, 67] | 66.0000 | -18.5000 | 4 |
| 5 | reach-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 415.5000 | 0 |
| 5 | door-open-v3 | True | DIRECT_G8 | [89, 89, 89, 89] | 89.0000 | 0.0000 | 4 |
| 5 | door-open-v3 | True | KEEP_G8_AFTER16 | [99, 99, 99, 99] | 99.0000 | 10.0000 | 4 |
| 5 | door-open-v3 | True | UPDATE_G16 | [100, 98, 99, 100] | 99.2500 | 10.2500 | 4 |
| 5 | door-open-v3 | True | POINT16_CYCLE | [108, 125, 104, 104] | 110.2500 | 21.2500 | 4 |
| 5 | door-open-v3 | True | PASSIVE_G16 | [93, 93, 93, 92] | 92.7500 | 3.7500 | 4 |
| 5 | door-open-v3 | True | POINT16_WIDE | [106, 107, 110, 105] | 107.0000 | 18.0000 | 4 |
| 5 | door-open-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 411.0000 | 0 |
| 6 | push-v3 | True | DIRECT_G8 | [67, 68, 68, 69] | 68.0000 | 0.0000 | 4 |
| 6 | push-v3 | True | KEEP_G8_AFTER16 | [78, 78, 78, 79] | 78.2500 | 10.2500 | 4 |
| 6 | push-v3 | True | UPDATE_G16 | [72, 74, 73, 74] | 73.2500 | 5.2500 | 4 |
| 6 | push-v3 | True | POINT16_CYCLE | [72, 74, 72, 74] | 73.0000 | 5.0000 | 4 |
| 6 | push-v3 | True | PASSIVE_G16 | [67, 66, 67, 68] | 67.0000 | -1.0000 | 4 |
| 6 | push-v3 | True | POINT16_WIDE | [76, 80, 77, 79] | 78.0000 | 10.0000 | 4 |
| 6 | push-v3 | True | NO_PROBE | [76, 67, 66, 189] | 99.5000 | 31.5000 | 4 |
| 6 | reach-v3 | True | DIRECT_G8 | [52, 53, 52, 50] | 51.7500 | 0.0000 | 4 |
| 6 | reach-v3 | True | KEEP_G8_AFTER16 | [63, 61, 60, 61] | 61.2500 | 9.5000 | 4 |
| 6 | reach-v3 | True | UPDATE_G16 | [74, 66, 62, 73] | 68.7500 | 17.0000 | 4 |
| 6 | reach-v3 | True | POINT16_CYCLE | [73, 66, 62, 72] | 68.2500 | 16.5000 | 4 |
| 6 | reach-v3 | True | PASSIVE_G16 | [500, 500, 500, 500] | 500.0000 | 448.2500 | 0 |
| 6 | reach-v3 | True | POINT16_WIDE | [84, 79, 77, 93] | 83.2500 | 31.5000 | 4 |
| 6 | reach-v3 | True | NO_PROBE | [82, 69, 65, 74] | 72.5000 | 20.7500 | 4 |
| 6 | door-open-v3 | True | DIRECT_G8 | [92, 92, 91, 91] | 91.5000 | 0.0000 | 4 |
| 6 | door-open-v3 | True | KEEP_G8_AFTER16 | [101, 101, 101, 100] | 100.7500 | 9.2500 | 4 |
| 6 | door-open-v3 | True | UPDATE_G16 | [100, 99, 100, 98] | 99.2500 | 7.7500 | 4 |
| 6 | door-open-v3 | True | POINT16_CYCLE | [100, 99, 100, 98] | 99.2500 | 7.7500 | 4 |
| 6 | door-open-v3 | True | PASSIVE_G16 | [98, 98, 97, 98] | 97.7500 | 6.2500 | 4 |
| 6 | door-open-v3 | True | POINT16_WIDE | [108, 108, 108, 108] | 108.0000 | 16.5000 | 4 |
| 6 | door-open-v3 | True | NO_PROBE | [97, 97, 96, 96] | 96.5000 | 5.0000 | 4 |
| 7 | push-v3 | True | DIRECT_G8 | [64, 65, 66, 65] | 65.0000 | 0.0000 | 4 |
| 7 | push-v3 | True | KEEP_G8_AFTER16 | [71, 72, 74, 73] | 72.5000 | 7.5000 | 4 |
| 7 | push-v3 | True | UPDATE_G16 | [74, 73, 75, 73] | 73.7500 | 8.7500 | 4 |
| 7 | push-v3 | True | POINT16_CYCLE | [74, 72, 75, 72] | 73.2500 | 8.2500 | 4 |
| 7 | push-v3 | True | PASSIVE_G16 | [64, 66, 67, 65] | 65.5000 | 0.5000 | 4 |
| 7 | push-v3 | True | POINT16_WIDE | [76, 73, 77, 74] | 75.0000 | 10.0000 | 4 |
| 7 | push-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 435.0000 | 0 |
| 7 | reach-v3 | True | DIRECT_G8 | [77, 65, 67, 67] | 69.0000 | 0.0000 | 4 |
| 7 | reach-v3 | True | KEEP_G8_AFTER16 | [80, 73, 73, 73] | 74.7500 | 5.7500 | 4 |
| 7 | reach-v3 | True | UPDATE_G16 | [78, 71, 73, 72] | 73.5000 | 4.5000 | 4 |
| 7 | reach-v3 | True | POINT16_CYCLE | [78, 70, 73, 72] | 73.2500 | 4.2500 | 4 |
| 7 | reach-v3 | True | PASSIVE_G16 | [59, 52, 53, 56] | 55.0000 | -14.0000 | 4 |
| 7 | reach-v3 | True | POINT16_WIDE | [73, 64, 71, 65] | 68.2500 | -0.7500 | 4 |
| 7 | reach-v3 | True | NO_PROBE | [500, 40, 500, 44] | 271.0000 | 202.0000 | 2 |
| 7 | door-open-v3 | True | DIRECT_G8 | [85, 126, 90, 89] | 97.5000 | 0.0000 | 4 |
| 7 | door-open-v3 | True | KEEP_G8_AFTER16 | [93, 95, 98, 96] | 95.5000 | -2.0000 | 4 |
| 7 | door-open-v3 | True | UPDATE_G16 | [95, 90, 89, 90] | 91.0000 | -6.5000 | 4 |
| 7 | door-open-v3 | True | POINT16_CYCLE | [95, 98, 98, 89] | 95.0000 | -2.5000 | 4 |
| 7 | door-open-v3 | True | PASSIVE_G16 | [90, 92, 95, 94] | 92.7500 | -4.7500 | 4 |
| 7 | door-open-v3 | True | POINT16_WIDE | [123, 119, 122, 126] | 122.5000 | 25.0000 | 4 |
| 7 | door-open-v3 | True | NO_PROBE | [500, 500, 500, 500] | 500.0000 | 402.5000 | 0 |

## 全部留出查询选择

| 流 | 任务 | 留出未来 | 训练未来 | 选择 | 选中分支留出损失 | 比直接八步损失差 |
|---:|---|---:|---|---|---:|---:|
| 0 | push-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 78 | 0 |
| 0 | push-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 79 | 0 |
| 0 | push-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 77 | 0 |
| 0 | push-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 79 | 0 |
| 0 | reach-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 68 | -7 |
| 0 | reach-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 75 | -8 |
| 0 | reach-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 68 | -15 |
| 0 | reach-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 67 | -10 |
| 0 | door-open-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 101 | 0 |
| 0 | door-open-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 101 | 0 |
| 0 | door-open-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 101 | 0 |
| 0 | door-open-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 101 | 0 |
| 1 | push-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 74 | 0 |
| 1 | push-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 75 | 0 |
| 1 | push-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 75 | 0 |
| 1 | push-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 75 | 0 |
| 1 | reach-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 40 | -8 |
| 1 | reach-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 40 | -7 |
| 1 | reach-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 40 | -9 |
| 1 | reach-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 40 | -8 |
| 1 | door-open-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 98 | 0 |
| 1 | door-open-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 98 | 0 |
| 1 | door-open-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 98 | 0 |
| 1 | door-open-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 98 | 0 |
| 2 | push-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 77 | -2 |
| 2 | push-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 78 | -2 |
| 2 | push-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 78 | -3 |
| 2 | push-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 78 | -4 |
| 2 | reach-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 66 | -9 |
| 2 | reach-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 69 | -9 |
| 2 | reach-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 71 | -45 |
| 2 | reach-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 62 | -21 |
| 2 | door-open-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 104 | 0 |
| 2 | door-open-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 107 | 0 |
| 2 | door-open-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 108 | 0 |
| 2 | door-open-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 103 | 0 |
| 3 | push-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 78 | -422 |
| 3 | push-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 77 | -423 |
| 3 | push-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 78 | -422 |
| 3 | push-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 78 | -422 |
| 3 | reach-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 67 | -2 |
| 3 | reach-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 67 | -5 |
| 3 | reach-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 62 | -2 |
| 3 | reach-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 60 | -4 |
| 3 | door-open-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 500 | 0 |
| 3 | door-open-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 500 | 0 |
| 3 | door-open-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 500 | 0 |
| 3 | door-open-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 500 | 0 |
| 4 | push-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 84 | -416 |
| 4 | push-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 86 | -6 |
| 4 | push-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 86 | -414 |
| 4 | push-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 85 | -415 |
| 4 | reach-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 53 | -3 |
| 4 | reach-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 52 | -5 |
| 4 | reach-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 51 | -4 |
| 4 | reach-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 55 | -4 |
| 4 | door-open-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 126 | 1 |
| 4 | door-open-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 116 | -1 |
| 4 | door-open-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 130 | 0 |
| 4 | door-open-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 124 | 2 |
| 5 | push-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 77 | 0 |
| 5 | push-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 76 | 0 |
| 5 | push-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 77 | 0 |
| 5 | push-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 77 | 0 |
| 5 | reach-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 54 | -30 |
| 5 | reach-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 53 | -30 |
| 5 | reach-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 55 | -32 |
| 5 | reach-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 55 | -29 |
| 5 | door-open-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 89 | 0 |
| 5 | door-open-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 89 | 0 |
| 5 | door-open-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 89 | 0 |
| 5 | door-open-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 89 | 0 |
| 6 | push-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 67 | 0 |
| 6 | push-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 66 | -2 |
| 6 | push-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 67 | -1 |
| 6 | push-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 68 | -1 |
| 6 | reach-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 52 | 0 |
| 6 | reach-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 53 | 0 |
| 6 | reach-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 52 | 0 |
| 6 | reach-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 50 | 0 |
| 6 | door-open-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 92 | 0 |
| 6 | door-open-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 92 | 0 |
| 6 | door-open-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 91 | 0 |
| 6 | door-open-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 91 | 0 |
| 7 | push-v3 | 0 | [1, 2, 3] | DIRECT_G8 | 64 | 0 |
| 7 | push-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 65 | 0 |
| 7 | push-v3 | 2 | [0, 1, 3] | DIRECT_G8 | 66 | 0 |
| 7 | push-v3 | 3 | [0, 1, 2] | DIRECT_G8 | 65 | 0 |
| 7 | reach-v3 | 0 | [1, 2, 3] | PASSIVE_G16 | 59 | -18 |
| 7 | reach-v3 | 1 | [0, 2, 3] | PASSIVE_G16 | 52 | -13 |
| 7 | reach-v3 | 2 | [0, 1, 3] | PASSIVE_G16 | 53 | -14 |
| 7 | reach-v3 | 3 | [0, 1, 2] | PASSIVE_G16 | 56 | -11 |
| 7 | door-open-v3 | 0 | [1, 2, 3] | UPDATE_G16 | 95 | 10 |
| 7 | door-open-v3 | 1 | [0, 2, 3] | DIRECT_G8 | 126 | 0 |
| 7 | door-open-v3 | 2 | [0, 1, 3] | UPDATE_G16 | 89 | -1 |
| 7 | door-open-v3 | 3 | [0, 1, 2] | UPDATE_G16 | 90 | 1 |

## 全部分层

| 方法 | 分层 | 成功 / 分母 | 停止 | 平均损失 |
|---|---|---|---:|---:|
| DIRECT_G8 | future:0 | 21 / 24 | 0 | 132.0417 |
| DIRECT_G8 | future:1 | 22 / 24 | 0 | 116.7917 |
| DIRECT_G8 | future:2 | 21 / 24 | 0 | 134.3333 |
| DIRECT_G8 | future:3 | 21 / 24 | 0 | 132.1667 |
| DIRECT_G8 | stream:0 | 12 / 12 | 0 | 86.2500 |
| DIRECT_G8 | stream:1 | 12 / 12 | 0 | 73.5833 |
| DIRECT_G8 | stream:2 | 12 / 12 | 0 | 91.3333 |
| DIRECT_G8 | stream:3 | 4 / 12 | 0 | 355.7500 |
| DIRECT_G8 | stream:4 | 9 / 12 | 0 | 192.7500 |
| DIRECT_G8 | stream:5 | 12 / 12 | 0 | 83.4167 |
| DIRECT_G8 | stream:6 | 12 / 12 | 0 | 70.4167 |
| DIRECT_G8 | stream:7 | 12 / 12 | 0 | 77.1667 |
| DIRECT_G8 | task:door-open-v3 | 28 / 32 | 0 | 150.7500 |
| DIRECT_G8 | task:push-v3 | 25 / 32 | 0 | 167.6562 |
| DIRECT_G8 | task:reach-v3 | 32 / 32 | 0 | 68.0938 |
| KEEP_G8_AFTER16 | future:0 | 22 / 24 | 0 | 122.8333 |
| KEEP_G8_AFTER16 | future:1 | 21 / 24 | 0 | 140.0000 |
| KEEP_G8_AFTER16 | future:2 | 21 / 24 | 0 | 140.7083 |
| KEEP_G8_AFTER16 | future:3 | 22 / 24 | 0 | 124.6667 |
| KEEP_G8_AFTER16 | stream:0 | 12 / 12 | 0 | 93.4167 |
| KEEP_G8_AFTER16 | stream:1 | 12 / 12 | 0 | 82.1667 |
| KEEP_G8_AFTER16 | stream:2 | 12 / 12 | 0 | 100.2500 |
| KEEP_G8_AFTER16 | stream:3 | 5 / 12 | 0 | 323.8333 |
| KEEP_G8_AFTER16 | stream:4 | 9 / 12 | 0 | 197.7500 |
| KEEP_G8_AFTER16 | stream:5 | 12 / 12 | 0 | 98.0000 |
| KEEP_G8_AFTER16 | stream:6 | 12 / 12 | 0 | 80.0833 |
| KEEP_G8_AFTER16 | stream:7 | 12 / 12 | 0 | 80.9167 |
| KEEP_G8_AFTER16 | task:door-open-v3 | 28 / 32 | 0 | 156.4062 |
| KEEP_G8_AFTER16 | task:push-v3 | 26 / 32 | 0 | 161.9375 |
| KEEP_G8_AFTER16 | task:reach-v3 | 32 / 32 | 0 | 77.8125 |
| NO_PROBE | future:0 | 8 / 24 | 0 | 367.1250 |
| NO_PROBE | future:1 | 9 / 24 | 0 | 349.6667 |
| NO_PROBE | future:2 | 8 / 24 | 0 | 372.7083 |
| NO_PROBE | future:3 | 8 / 24 | 0 | 368.7917 |
| NO_PROBE | stream:0 | 4 / 12 | 0 | 366.0000 |
| NO_PROBE | stream:1 | 0 / 12 | 0 | 500.0000 |
| NO_PROBE | stream:2 | 8 / 12 | 0 | 239.0000 |
| NO_PROBE | stream:3 | 0 / 12 | 0 | 500.0000 |
| NO_PROBE | stream:4 | 7 / 12 | 0 | 298.4167 |
| NO_PROBE | stream:5 | 0 / 12 | 0 | 500.0000 |
| NO_PROBE | stream:6 | 12 / 12 | 0 | 89.5000 |
| NO_PROBE | stream:7 | 2 / 12 | 0 | 423.6667 |
| NO_PROBE | task:door-open-v3 | 16 / 32 | 0 | 301.7812 |
| NO_PROBE | task:push-v3 | 7 / 32 | 0 | 421.8125 |
| NO_PROBE | task:reach-v3 | 10 / 32 | 0 | 370.1250 |
| PASSIVE_G16 | future:0 | 22 / 24 | 0 | 113.3333 |
| PASSIVE_G16 | future:1 | 22 / 24 | 0 | 113.2083 |
| PASSIVE_G16 | future:2 | 22 / 24 | 0 | 113.2500 |
| PASSIVE_G16 | future:3 | 22 / 24 | 0 | 113.0833 |
| PASSIVE_G16 | stream:0 | 12 / 12 | 0 | 83.0000 |
| PASSIVE_G16 | stream:1 | 12 / 12 | 0 | 71.4167 |
| PASSIVE_G16 | stream:2 | 12 / 12 | 0 | 83.6667 |
| PASSIVE_G16 | stream:3 | 8 / 12 | 0 | 213.9167 |
| PASSIVE_G16 | stream:4 | 12 / 12 | 0 | 86.3333 |
| PASSIVE_G16 | stream:5 | 12 / 12 | 0 | 74.7500 |
| PASSIVE_G16 | stream:6 | 8 / 12 | 0 | 221.5833 |
| PASSIVE_G16 | stream:7 | 12 / 12 | 0 | 71.0833 |
| PASSIVE_G16 | task:door-open-v3 | 28 / 32 | 0 | 151.2812 |
| PASSIVE_G16 | task:push-v3 | 32 / 32 | 0 | 75.5625 |
| PASSIVE_G16 | task:reach-v3 | 28 / 32 | 0 | 112.8125 |
| POINT16_CYCLE | future:0 | 23 / 24 | 0 | 103.7917 |
| POINT16_CYCLE | future:1 | 23 / 24 | 0 | 103.4583 |
| POINT16_CYCLE | future:2 | 23 / 24 | 0 | 103.8750 |
| POINT16_CYCLE | future:3 | 23 / 24 | 0 | 103.6667 |
| POINT16_CYCLE | stream:0 | 12 / 12 | 0 | 91.5833 |
| POINT16_CYCLE | stream:1 | 12 / 12 | 0 | 82.5833 |
| POINT16_CYCLE | stream:2 | 12 / 12 | 0 | 89.5833 |
| POINT16_CYCLE | stream:3 | 8 / 12 | 0 | 220.9167 |
| POINT16_CYCLE | stream:4 | 12 / 12 | 0 | 96.1667 |
| POINT16_CYCLE | stream:5 | 12 / 12 | 0 | 88.0833 |
| POINT16_CYCLE | stream:6 | 12 / 12 | 0 | 80.1667 |
| POINT16_CYCLE | stream:7 | 12 / 12 | 0 | 80.5000 |
| POINT16_CYCLE | task:door-open-v3 | 28 / 32 | 0 | 158.5312 |
| POINT16_CYCLE | task:push-v3 | 32 / 32 | 0 | 82.2500 |
| POINT16_CYCLE | task:reach-v3 | 32 / 32 | 0 | 70.3125 |
| POINT16_WIDE | future:0 | 23 / 24 | 0 | 106.9167 |
| POINT16_WIDE | future:1 | 23 / 24 | 0 | 105.0833 |
| POINT16_WIDE | future:2 | 23 / 24 | 0 | 106.8750 |
| POINT16_WIDE | future:3 | 23 / 24 | 0 | 107.6667 |
| POINT16_WIDE | stream:0 | 12 / 12 | 0 | 92.4167 |
| POINT16_WIDE | stream:1 | 12 / 12 | 0 | 86.0833 |
| POINT16_WIDE | stream:2 | 12 / 12 | 0 | 93.6667 |
| POINT16_WIDE | stream:3 | 8 / 12 | 0 | 220.3333 |
| POINT16_WIDE | stream:4 | 12 / 12 | 0 | 95.0833 |
| POINT16_WIDE | stream:5 | 12 / 12 | 0 | 87.1667 |
| POINT16_WIDE | stream:6 | 12 / 12 | 0 | 89.7500 |
| POINT16_WIDE | stream:7 | 12 / 12 | 0 | 88.5833 |
| POINT16_WIDE | task:door-open-v3 | 28 / 32 | 0 | 163.3438 |
| POINT16_WIDE | task:push-v3 | 32 / 32 | 0 | 85.0938 |
| POINT16_WIDE | task:reach-v3 | 32 / 32 | 0 | 71.4688 |
| UPDATE_G16 | future:0 | 23 / 24 | 0 | 103.6667 |
| UPDATE_G16 | future:1 | 23 / 24 | 0 | 103.5833 |
| UPDATE_G16 | future:2 | 23 / 24 | 0 | 104.6667 |
| UPDATE_G16 | future:3 | 23 / 24 | 0 | 103.2500 |
| UPDATE_G16 | stream:0 | 12 / 12 | 0 | 91.7500 |
| UPDATE_G16 | stream:1 | 12 / 12 | 0 | 83.1667 |
| UPDATE_G16 | stream:2 | 12 / 12 | 0 | 89.5000 |
| UPDATE_G16 | stream:3 | 8 / 12 | 0 | 221.2500 |
| UPDATE_G16 | stream:4 | 12 / 12 | 0 | 99.9167 |
| UPDATE_G16 | stream:5 | 12 / 12 | 0 | 84.9167 |
| UPDATE_G16 | stream:6 | 12 / 12 | 0 | 80.4167 |
| UPDATE_G16 | stream:7 | 12 / 12 | 0 | 79.4167 |
| UPDATE_G16 | task:door-open-v3 | 28 / 32 | 0 | 157.8125 |
| UPDATE_G16 | task:push-v3 | 32 / 32 | 0 | 82.5938 |
| UPDATE_G16 | task:reach-v3 | 32 / 32 | 0 | 70.9688 |

## 全部失败／停止

| 方法 | 流 | 任务 | 未来 | 种子 | 停止 | 实际步 |
|---|---:|---|---:|---:|---|---:|
| NO_PROBE | 0 | push-v3 | 0 | 12200 | False | 500 |
| NO_PROBE | 0 | push-v3 | 1 | 12200 | False | 500 |
| NO_PROBE | 0 | push-v3 | 2 | 12200 | False | 500 |
| NO_PROBE | 0 | push-v3 | 3 | 12200 | False | 500 |
| NO_PROBE | 0 | reach-v3 | 0 | 12201 | False | 500 |
| NO_PROBE | 0 | reach-v3 | 1 | 12201 | False | 500 |
| NO_PROBE | 0 | reach-v3 | 2 | 12201 | False | 500 |
| NO_PROBE | 0 | reach-v3 | 3 | 12201 | False | 500 |
| NO_PROBE | 1 | push-v3 | 0 | 12203 | False | 500 |
| NO_PROBE | 1 | push-v3 | 1 | 12203 | False | 500 |
| NO_PROBE | 1 | push-v3 | 2 | 12203 | False | 500 |
| NO_PROBE | 1 | push-v3 | 3 | 12203 | False | 500 |
| NO_PROBE | 1 | reach-v3 | 0 | 12204 | False | 500 |
| NO_PROBE | 1 | reach-v3 | 1 | 12204 | False | 500 |
| NO_PROBE | 1 | reach-v3 | 2 | 12204 | False | 500 |
| NO_PROBE | 1 | reach-v3 | 3 | 12204 | False | 500 |
| NO_PROBE | 1 | door-open-v3 | 0 | 12205 | False | 500 |
| NO_PROBE | 1 | door-open-v3 | 1 | 12205 | False | 500 |
| NO_PROBE | 1 | door-open-v3 | 2 | 12205 | False | 500 |
| NO_PROBE | 1 | door-open-v3 | 3 | 12205 | False | 500 |
| NO_PROBE | 2 | push-v3 | 0 | 12206 | False | 500 |
| NO_PROBE | 2 | push-v3 | 1 | 12206 | False | 500 |
| NO_PROBE | 2 | push-v3 | 2 | 12206 | False | 500 |
| NO_PROBE | 2 | push-v3 | 3 | 12206 | False | 500 |
| DIRECT_G8 | 3 | push-v3 | 0 | 12209 | False | 500 |
| KEEP_G8_AFTER16 | 3 | push-v3 | 0 | 12209 | False | 500 |
| NO_PROBE | 3 | push-v3 | 0 | 12209 | False | 500 |
| DIRECT_G8 | 3 | push-v3 | 1 | 12209 | False | 500 |
| KEEP_G8_AFTER16 | 3 | push-v3 | 1 | 12209 | False | 500 |
| NO_PROBE | 3 | push-v3 | 1 | 12209 | False | 500 |
| DIRECT_G8 | 3 | push-v3 | 2 | 12209 | False | 500 |
| KEEP_G8_AFTER16 | 3 | push-v3 | 2 | 12209 | False | 500 |
| NO_PROBE | 3 | push-v3 | 2 | 12209 | False | 500 |
| DIRECT_G8 | 3 | push-v3 | 3 | 12209 | False | 500 |
| NO_PROBE | 3 | push-v3 | 3 | 12209 | False | 500 |
| NO_PROBE | 3 | reach-v3 | 0 | 12210 | False | 500 |
| NO_PROBE | 3 | reach-v3 | 1 | 12210 | False | 500 |
| NO_PROBE | 3 | reach-v3 | 2 | 12210 | False | 500 |
| NO_PROBE | 3 | reach-v3 | 3 | 12210 | False | 500 |
| DIRECT_G8 | 3 | door-open-v3 | 0 | 12211 | False | 500 |
| KEEP_G8_AFTER16 | 3 | door-open-v3 | 0 | 12211 | False | 500 |
| UPDATE_G16 | 3 | door-open-v3 | 0 | 12211 | False | 500 |
| POINT16_CYCLE | 3 | door-open-v3 | 0 | 12211 | False | 500 |
| PASSIVE_G16 | 3 | door-open-v3 | 0 | 12211 | False | 500 |
| POINT16_WIDE | 3 | door-open-v3 | 0 | 12211 | False | 500 |
| NO_PROBE | 3 | door-open-v3 | 0 | 12211 | False | 500 |
| DIRECT_G8 | 3 | door-open-v3 | 1 | 12211 | False | 500 |
| KEEP_G8_AFTER16 | 3 | door-open-v3 | 1 | 12211 | False | 500 |
| UPDATE_G16 | 3 | door-open-v3 | 1 | 12211 | False | 500 |
| POINT16_CYCLE | 3 | door-open-v3 | 1 | 12211 | False | 500 |
| PASSIVE_G16 | 3 | door-open-v3 | 1 | 12211 | False | 500 |
| POINT16_WIDE | 3 | door-open-v3 | 1 | 12211 | False | 500 |
| NO_PROBE | 3 | door-open-v3 | 1 | 12211 | False | 500 |
| DIRECT_G8 | 3 | door-open-v3 | 2 | 12211 | False | 500 |
| KEEP_G8_AFTER16 | 3 | door-open-v3 | 2 | 12211 | False | 500 |
| UPDATE_G16 | 3 | door-open-v3 | 2 | 12211 | False | 500 |
| POINT16_CYCLE | 3 | door-open-v3 | 2 | 12211 | False | 500 |
| PASSIVE_G16 | 3 | door-open-v3 | 2 | 12211 | False | 500 |
| POINT16_WIDE | 3 | door-open-v3 | 2 | 12211 | False | 500 |
| NO_PROBE | 3 | door-open-v3 | 2 | 12211 | False | 500 |
| DIRECT_G8 | 3 | door-open-v3 | 3 | 12211 | False | 500 |
| KEEP_G8_AFTER16 | 3 | door-open-v3 | 3 | 12211 | False | 500 |
| UPDATE_G16 | 3 | door-open-v3 | 3 | 12211 | False | 500 |
| POINT16_CYCLE | 3 | door-open-v3 | 3 | 12211 | False | 500 |
| PASSIVE_G16 | 3 | door-open-v3 | 3 | 12211 | False | 500 |
| POINT16_WIDE | 3 | door-open-v3 | 3 | 12211 | False | 500 |
| NO_PROBE | 3 | door-open-v3 | 3 | 12211 | False | 500 |
| DIRECT_G8 | 4 | push-v3 | 0 | 12212 | False | 500 |
| KEEP_G8_AFTER16 | 4 | push-v3 | 1 | 12212 | False | 500 |
| DIRECT_G8 | 4 | push-v3 | 2 | 12212 | False | 500 |
| KEEP_G8_AFTER16 | 4 | push-v3 | 2 | 12212 | False | 500 |
| DIRECT_G8 | 4 | push-v3 | 3 | 12212 | False | 500 |
| KEEP_G8_AFTER16 | 4 | push-v3 | 3 | 12212 | False | 500 |
| NO_PROBE | 4 | push-v3 | 3 | 12212 | False | 500 |
| NO_PROBE | 4 | reach-v3 | 0 | 12213 | False | 500 |
| NO_PROBE | 4 | reach-v3 | 1 | 12213 | False | 500 |
| NO_PROBE | 4 | reach-v3 | 2 | 12213 | False | 500 |
| NO_PROBE | 4 | reach-v3 | 3 | 12213 | False | 500 |
| NO_PROBE | 5 | push-v3 | 0 | 12215 | False | 500 |
| NO_PROBE | 5 | push-v3 | 1 | 12215 | False | 500 |
| NO_PROBE | 5 | push-v3 | 2 | 12215 | False | 500 |
| NO_PROBE | 5 | push-v3 | 3 | 12215 | False | 500 |
| NO_PROBE | 5 | reach-v3 | 0 | 12216 | False | 500 |
| NO_PROBE | 5 | reach-v3 | 1 | 12216 | False | 500 |
| NO_PROBE | 5 | reach-v3 | 2 | 12216 | False | 500 |
| NO_PROBE | 5 | reach-v3 | 3 | 12216 | False | 500 |
| NO_PROBE | 5 | door-open-v3 | 0 | 12217 | False | 500 |
| NO_PROBE | 5 | door-open-v3 | 1 | 12217 | False | 500 |
| NO_PROBE | 5 | door-open-v3 | 2 | 12217 | False | 500 |
| NO_PROBE | 5 | door-open-v3 | 3 | 12217 | False | 500 |
| PASSIVE_G16 | 6 | reach-v3 | 0 | 12219 | False | 500 |
| PASSIVE_G16 | 6 | reach-v3 | 1 | 12219 | False | 500 |
| PASSIVE_G16 | 6 | reach-v3 | 2 | 12219 | False | 500 |
| PASSIVE_G16 | 6 | reach-v3 | 3 | 12219 | False | 500 |
| NO_PROBE | 7 | push-v3 | 0 | 12221 | False | 500 |
| NO_PROBE | 7 | push-v3 | 1 | 12221 | False | 500 |
| NO_PROBE | 7 | push-v3 | 2 | 12221 | False | 500 |
| NO_PROBE | 7 | push-v3 | 3 | 12221 | False | 500 |
| NO_PROBE | 7 | reach-v3 | 0 | 12222 | False | 500 |
| NO_PROBE | 7 | reach-v3 | 2 | 12222 | False | 500 |
| NO_PROBE | 7 | door-open-v3 | 0 | 12223 | False | 500 |
| NO_PROBE | 7 | door-open-v3 | 1 | 12223 | False | 500 |
| NO_PROBE | 7 | door-open-v3 | 2 | 12223 | False | 500 |
| NO_PROBE | 7 | door-open-v3 | 3 | 12223 | False | 500 |

## 全部真实研究费用

672 次真实执行共 101,069 个 Env.step／672 次控制初始重置；顶层重置 34,272，完成 do_simulation 请求帧 17,641,345。

| 阶段 | 完成重置 | 完成模拟调用 | 完成请求帧 |
|---|---:|---:|---:|
| GOAL_GENERATION | 33600 | 3360000 | 16800000 |
| CONTROLLED_RESET | 672 | 67200 | 336000 |
| CONTROL | 0 | 101069 | 505345 |

查询表依赖的五分支源实际消耗 55,833 个控制步；整批对照人口费用仍完整披露。所选分支统计没有新增物理执行，不能当作部署中的真实成本节省。每控制步五帧／0.0125 秒；请求帧不是全部 C 引擎计算或真实机器人费用。

审计独立重建噪声、逐步政策／程序与保存控制器；前缀配对、Gaussian／点拟合及查询表统计公式明确复用。没有动力学重仿真或完整隐状态资格。API、自然经验记忆写入和底层政策权重更新为零。

单次赢家反转、查询表收益和真正条件最优策略是不同问题。三训练未来可能不足以估计期望代价；无收益不证明不存在可学习条件策略，有收益也不证明当前有可部署方法。新颖性、强方法竞争、独立在线确认与完整论文仍未完成。
