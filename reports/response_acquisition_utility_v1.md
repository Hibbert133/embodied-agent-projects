# 同一旧缓存与连续状态上的取证收益：中文核查

RESPONSE_SET 的 48 个精确配对中，取证分支成功 48/48，沿用同一旧缓存成功 41/48；有利 7、有害 0。全部 48 个案例都是冷启动后案例号 1。G_OPTIMAL 配对 55 个，成功 49/55 对 48/55，有利 5、有害 4；其有害分支均停止。

这是原始开发数据上的机制解释，不是新任务或独立确认。两组共享 48 个旧状态，不能视为 103 个独立样本；原 288 单元总体中 RESPONSE_SET 被 FIXED16、FIXED8_WIDE、FIXED16_WIDE 支配的负结果保持不变。

原运行 `action_response_20261014T104928Z_1c3798544481`，原冻结源 `1c37985444816ad9cca434d2fe38825678fc82dd`；只读核查源 `784e61976859fd4611c8d678d1d923ec937a9a78`。

[完整原实验报告](action_response_development_v3.md) · [核查协议](../docs/research/response_acquisition_utility_audit_v1.md) · [逐案数据](../outputs/response_acquisition_utility/audit_v1/audit.json) · [独立复算](../outputs/response_acquisition_utility/verification_v1/verification.json)

## 配对人口与代价

每个方法先检查全部 288 个原单元；资格仅使用同流／任务／情景／案例号、种子、评估器算子 ID、非空旧缓存、完整初始状态与 RNG、前六步真实命令／政策动作／前后观察／RNG。旧缓存与数值均精确匹配，没有近似匹配或按后续成败筛选。算子真值只用于本离线评估。

| 方法 | 原单元 | 无旧缓存 | 旧缓存已不同 | 合格 | 案例号 1 | 更晚案例 |
|---|---:|---:|---:|---:|---:|---:|
| RESPONSE_SET | 288 | 48 | 192 | 48 | 48 | 0 |
| G_OPTIMAL | 288 | 48 | 185 | 55 | 48 | 7 |

实际没有因前缀运动不同、历史短或六步内已结束而排除的记录。每个排除单元和原因均保存在逐案数据，不能为不同旧模型伪造刷新反事实。

| 方法／人口 | 成功：取证 / 缓存 | 停止：取证 / 缓存 | 有利 / 有害 / 同成 / 同败 | 平均总步：取证 / 缓存 | 平均剩余步：取证 / 缓存 | 额外探测步 |
|---|---|---|---|---|---|---:|
| RESPONSE_SET 全部 | 48 / 41（n=48） | 0 / 0 | 7 / 0 / 41 / 0 | 105.2083 / 144.5625 | 99.2083 / 138.5625 | 25.1667 |
| RESPONSE_SET 案例 1 | 48 / 41（n=48） | 0 / 0 | 7 / 0 / 41 / 0 | 105.2083 / 144.5625 | 99.2083 / 138.5625 | 25.1667 |
| G_OPTIMAL 全部 | 49 / 48（n=55） | 4 / 0 | 5 / 4 / 44 / 2 | 113.8000 / 137.1273 | 107.8000 / 131.1273 | 21.9636 |
| G_OPTIMAL 案例 1 | 44 / 41（n=48） | 2 / 0 | 5 / 2 / 39 / 2 | 119.2083 / 144.5625 | 113.2083 / 138.5625 | 22.0000 |

总步和剩余步包含停止与失败；剩余步减去共同六步前缀，额外探测同时包含微探测与固定刷新。G_OPTIMAL 的停止降低平均步数，不能据此声称效率收益。

两种方法和缓存参照均承担原完整来源的 21,010 步／288 次登记控制环境重置，原实验按 288 单元摊销。这项事后配对分析不把来源改按 48 或 55 单元重新分摊，也不新增采集成本。Env.step 与控制重置是登记口径；MetaWorld 工厂内部初始化的条件性推算见完整报告。

## 完整分层

| 方法／分层 | 成功：取证 / 缓存 | 停止：取证 / 缓存 | 有利 / 有害 / 同成 / 同败 | 平均总步：取证 / 缓存 | 平均剩余步：取证 / 缓存 | 额外探测步 |
|---|---|---|---|---|---|---:|
| RESPONSE_SET/push-v3 | 16 / 13（n=16） | 0 / 0 | 3 / 0 / 13 / 0 | 92.8125 / 146.3750 | 86.8125 / 140.3750 | 23.7500 |
| RESPONSE_SET/reach-v3 | 16 / 15（n=16） | 0 / 0 | 1 / 0 / 15 / 0 | 84.8750 / 89.5000 | 78.8750 / 83.5000 | 24.7500 |
| RESPONSE_SET/door-open-v3 | 16 / 13（n=16） | 0 / 0 | 3 / 0 / 13 / 0 | 137.9375 / 197.8125 | 131.9375 / 191.8125 | 27.0000 |
| RESPONSE_SET/STATIONARY | 24 / 23（n=24） | 0 / 0 | 1 / 0 / 23 / 0 | 104.1667 / 91.0833 | 98.1667 / 85.0833 | 26.6667 |
| RESPONSE_SET/MIXED | 24 / 18（n=24） | 0 / 0 | 6 / 0 / 18 / 0 | 106.2500 / 198.0417 | 100.2500 / 192.0417 | 23.6667 |
| RESPONSE_SET/流 0 | 6 / 4（n=6） | 0 / 0 | 2 / 0 / 4 / 0 | 103.3333 / 215.3333 | 97.3333 / 209.3333 | 28.0000 |
| RESPONSE_SET/流 1 | 6 / 6（n=6） | 0 / 0 | 0 / 0 / 6 / 0 | 88.6667 / 125.3333 | 82.6667 / 119.3333 | 20.6667 |
| RESPONSE_SET/流 2 | 6 / 6（n=6） | 0 / 0 | 0 / 0 / 6 / 0 | 126.0000 / 85.3333 | 120.0000 / 79.3333 | 28.0000 |
| RESPONSE_SET/流 3 | 6 / 5（n=6） | 0 / 0 | 1 / 0 / 5 / 0 | 104.8333 / 160.0000 | 98.8333 / 154.0000 | 22.6667 |
| RESPONSE_SET/流 4 | 6 / 6（n=6） | 0 / 0 | 0 / 0 / 6 / 0 | 98.0000 / 72.0000 | 92.0000 / 66.0000 | 32.0000 |
| RESPONSE_SET/流 5 | 6 / 3（n=6） | 0 / 0 | 3 / 0 / 3 / 0 | 96.3333 / 284.5000 | 90.3333 / 278.5000 | 22.6667 |
| RESPONSE_SET/流 6 | 6 / 5（n=6） | 0 / 0 | 1 / 0 / 5 / 0 | 109.8333 / 149.3333 | 103.8333 / 143.3333 | 20.6667 |
| RESPONSE_SET/流 7 | 6 / 6（n=6） | 0 / 0 | 0 / 0 / 6 / 0 | 114.6667 / 64.6667 | 108.6667 / 58.6667 | 26.6667 |
| G_OPTIMAL/push-v3 | 17 / 14（n=17） | 0 / 0 | 3 / 0 / 14 / 0 | 93.5294 / 141.1176 | 87.5294 / 135.1176 | 24.4706 |
| G_OPTIMAL/reach-v3 | 18 / 17（n=18） | 0 / 0 | 1 / 0 / 17 / 0 | 91.0556 / 87.6667 | 85.0556 / 81.6667 | 19.1111 |
| G_OPTIMAL/door-open-v3 | 14 / 17（n=20） | 4 / 0 | 1 / 4 / 13 / 2 | 151.5000 / 178.2500 | 145.5000 / 172.2500 | 22.4000 |
| G_OPTIMAL/STATIONARY | 25 / 27（n=28） | 2 / 0 | 0 / 2 / 25 / 1 | 111.7857 / 89.1071 | 105.7857 / 83.1071 | 22.5714 |
| G_OPTIMAL/MIXED | 24 / 21（n=27） | 2 / 0 | 5 / 2 / 19 / 1 | 115.8889 / 186.9259 | 109.8889 / 180.9259 | 21.3333 |
| G_OPTIMAL/流 0 | 4 / 4（n=6） | 0 / 0 | 0 / 0 / 4 / 2 | 254.0000 / 215.3333 | 248.0000 / 209.3333 | 24.0000 |
| G_OPTIMAL/流 1 | 6 / 6（n=6） | 0 / 0 | 0 / 0 / 6 / 0 | 89.5000 / 125.3333 | 83.5000 / 119.3333 | 18.0000 |
| G_OPTIMAL/流 2 | 6 / 6（n=6） | 0 / 0 | 0 / 0 / 6 / 0 | 124.3333 / 85.3333 | 118.3333 / 79.3333 | 25.3333 |
| G_OPTIMAL/流 3 | 6 / 5（n=6） | 0 / 0 | 1 / 0 / 5 / 0 | 113.8333 / 160.0000 | 107.8333 / 154.0000 | 19.3333 |
| G_OPTIMAL/流 4 | 6 / 10（n=10） | 4 / 0 | 0 / 4 / 6 / 0 | 65.7000 / 83.2000 | 59.7000 / 77.2000 | 21.6000 |
| G_OPTIMAL/流 5 | 6 / 3（n=6） | 0 / 0 | 3 / 0 / 3 / 0 | 96.8333 / 284.5000 | 90.8333 / 278.5000 | 18.0000 |
| G_OPTIMAL/流 6 | 7 / 6（n=7） | 0 / 0 | 1 / 0 / 6 / 0 | 110.8571 / 136.1429 | 104.8571 / 130.1429 | 23.4286 |
| G_OPTIMAL/流 7 | 8 / 8（n=8） | 0 / 0 | 0 / 0 / 8 / 0 | 94.3750 / 66.7500 | 88.3750 / 60.7500 | 25.0000 |

STATIONARY 的 RESPONSE_SET 多消耗平均 13.0833 步、增加 1 次成功；MIXED 平均少 91.7917 步、增加 6 次成功。同种子对应相同任务初始化，但两个情景的执行器时序分布不同。协议中“边际任务分布”在此应理解为物理执行情景，不指任务种子另行抽样；不能据情景差宣称纯时序耦合的因果效应。

## 分支结局如何影响步数

| 方法 | 结局 | 案例数 | 取证减缓存总步 | 额外探测总步 |
|---|---|---:|---:|---:|
| RESPONSE_SET | HELPFUL | 7 | -2771 | 152 |
| RESPONSE_SET | HARMFUL | 0 | 0 | 0 |
| RESPONSE_SET | BOTH_SUCCESS | 41 | 882 | 1056 |
| RESPONSE_SET | BOTH_FAILED | 0 | 0 | 0 |
| G_OPTIMAL | HELPFUL | 5 | -2004 | 92 |
| G_OPTIMAL | HARMFUL | 4 | -304 | 80 |
| G_OPTIMAL | BOTH_SUCCESS | 44 | 1025 | 988 |
| G_OPTIMAL | BOTH_FAILED | 2 | 0 | 48 |

RESPONSE_SET 的 7 个新增成功使总步差减少 2,771 步；41 个共同成功案例反而总共多 882 步，平均多 21.5122 步。整体少 1,889 步主要来自避免跑满 500 步的失败，不能解释为每次取证都省时。这些结局分组只是描述已发生分支，不用于拟合任何在线选择器。

## 全部合格配对

案例号从 0 计数。结局标签有利／有害仅指二元成功差；两条分支均按原始物理轨迹计费。

| 方法 | 流 | 任务 | 情景 | 案例 | 种子 | 结局 | 取证 / 缓存步 | 额外探测 | 取证停止 | 初次状态 |
|---|---:|---|---|---:|---:|---|---|---:|---|---|
| RESPONSE_SET | 0 | push-v3 | STATIONARY | 1 | 10801 | 同成 | 78 / 60 | 28 | 否 | UNRESOLVED |
| RESPONSE_SET | 0 | push-v3 | MIXED | 1 | 10801 | 同成 | 78 / 60 | 28 | 否 | UNRESOLVED |
| RESPONSE_SET | 0 | reach-v3 | STATIONARY | 1 | 10807 | 同成 | 104 / 86 | 24 | 否 | UNRESOLVED |
| RESPONSE_SET | 0 | reach-v3 | MIXED | 1 | 10807 | 同成 | 104 / 86 | 24 | 否 | UNRESOLVED |
| RESPONSE_SET | 0 | door-open-v3 | STATIONARY | 1 | 10813 | 有利 | 128 / 500 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 0 | door-open-v3 | MIXED | 1 | 10813 | 有利 | 128 / 500 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 1 | push-v3 | STATIONARY | 1 | 10819 | 同成 | 91 / 51 | 16 | 否 | UNRESOLVED |
| RESPONSE_SET | 1 | push-v3 | MIXED | 1 | 10819 | 同成 | 67 / 61 | 16 | 否 | UNRESOLVED |
| RESPONSE_SET | 1 | reach-v3 | STATIONARY | 1 | 10825 | 同成 | 66 / 47 | 20 | 否 | UNRESOLVED |
| RESPONSE_SET | 1 | reach-v3 | MIXED | 1 | 10825 | 同成 | 70 / 153 | 24 | 否 | UNRESOLVED |
| RESPONSE_SET | 1 | door-open-v3 | STATIONARY | 1 | 10831 | 同成 | 133 / 101 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 1 | door-open-v3 | MIXED | 1 | 10831 | 同成 | 105 / 339 | 16 | 否 | INCOMPATIBLE |
| RESPONSE_SET | 2 | push-v3 | STATIONARY | 1 | 10837 | 同成 | 109 / 71 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 2 | push-v3 | MIXED | 1 | 10837 | 同成 | 109 / 71 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 2 | reach-v3 | STATIONARY | 1 | 10843 | 同成 | 106 / 71 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 2 | reach-v3 | MIXED | 1 | 10843 | 同成 | 106 / 71 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 2 | door-open-v3 | STATIONARY | 1 | 10849 | 同成 | 163 / 114 | 20 | 否 | UNRESOLVED |
| RESPONSE_SET | 2 | door-open-v3 | MIXED | 1 | 10849 | 同成 | 163 / 114 | 20 | 否 | UNRESOLVED |
| RESPONSE_SET | 3 | push-v3 | STATIONARY | 1 | 10855 | 同成 | 96 / 68 | 16 | 否 | UNRESOLVED |
| RESPONSE_SET | 3 | push-v3 | MIXED | 1 | 10855 | 有利 | 92 / 500 | 16 | 否 | UNRESOLVED |
| RESPONSE_SET | 3 | reach-v3 | STATIONARY | 1 | 10861 | 同成 | 78 / 39 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 3 | reach-v3 | MIXED | 1 | 10861 | 同成 | 55 / 28 | 20 | 否 | UNRESOLVED |
| RESPONSE_SET | 3 | door-open-v3 | STATIONARY | 1 | 10867 | 同成 | 122 / 138 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 3 | door-open-v3 | MIXED | 1 | 10867 | 同成 | 186 / 187 | 20 | 否 | UNRESOLVED |
| RESPONSE_SET | 4 | push-v3 | STATIONARY | 1 | 10873 | 同成 | 99 / 68 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 4 | push-v3 | MIXED | 1 | 10873 | 同成 | 99 / 68 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 4 | reach-v3 | STATIONARY | 1 | 10879 | 同成 | 78 / 50 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 4 | reach-v3 | MIXED | 1 | 10879 | 同成 | 78 / 50 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 4 | door-open-v3 | STATIONARY | 1 | 10885 | 同成 | 117 / 98 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 4 | door-open-v3 | MIXED | 1 | 10885 | 同成 | 117 / 98 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 5 | push-v3 | STATIONARY | 1 | 10891 | 同成 | 91 / 65 | 16 | 否 | UNRESOLVED |
| RESPONSE_SET | 5 | push-v3 | MIXED | 1 | 10891 | 有利 | 103 / 500 | 20 | 否 | UNRESOLVED |
| RESPONSE_SET | 5 | reach-v3 | STATIONARY | 1 | 10897 | 同成 | 67 / 55 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 5 | reach-v3 | MIXED | 1 | 10897 | 有利 | 55 / 500 | 20 | 否 | UNRESOLVED |
| RESPONSE_SET | 5 | door-open-v3 | STATIONARY | 1 | 10903 | 同成 | 134 / 87 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 5 | door-open-v3 | MIXED | 1 | 10903 | 有利 | 128 / 500 | 16 | 否 | INCOMPATIBLE |
| RESPONSE_SET | 6 | push-v3 | STATIONARY | 1 | 10909 | 同成 | 94 / 75 | 16 | 否 | UNRESOLVED |
| RESPONSE_SET | 6 | push-v3 | MIXED | 1 | 10909 | 有利 | 95 / 500 | 16 | 否 | UNRESOLVED |
| RESPONSE_SET | 6 | reach-v3 | STATIONARY | 1 | 10915 | 同成 | 75 / 51 | 20 | 否 | UNRESOLVED |
| RESPONSE_SET | 6 | reach-v3 | MIXED | 1 | 10915 | 同成 | 66 / 55 | 20 | 否 | UNRESOLVED |
| RESPONSE_SET | 6 | door-open-v3 | STATIONARY | 1 | 10921 | 同成 | 127 / 97 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 6 | door-open-v3 | MIXED | 1 | 10921 | 同成 | 202 / 118 | 20 | 否 | UNRESOLVED |
| RESPONSE_SET | 7 | push-v3 | STATIONARY | 1 | 10927 | 同成 | 92 / 62 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 7 | push-v3 | MIXED | 1 | 10927 | 同成 | 92 / 62 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 7 | reach-v3 | STATIONARY | 1 | 10933 | 同成 | 125 / 45 | 16 | 否 | UNRESOLVED |
| RESPONSE_SET | 7 | reach-v3 | MIXED | 1 | 10933 | 同成 | 125 / 45 | 16 | 否 | UNRESOLVED |
| RESPONSE_SET | 7 | door-open-v3 | STATIONARY | 1 | 10939 | 同成 | 127 / 87 | 32 | 否 | UNRESOLVED |
| RESPONSE_SET | 7 | door-open-v3 | MIXED | 1 | 10939 | 同成 | 127 / 87 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 0 | push-v3 | STATIONARY | 1 | 10801 | 同成 | 80 / 60 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 0 | push-v3 | MIXED | 1 | 10801 | 同成 | 80 / 60 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 0 | reach-v3 | STATIONARY | 1 | 10807 | 同成 | 182 / 86 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 0 | reach-v3 | MIXED | 1 | 10807 | 同成 | 182 / 86 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 0 | door-open-v3 | STATIONARY | 1 | 10813 | 同败 | 500 / 500 | 24 | 否 | UNRESOLVED |
| G_OPTIMAL | 0 | door-open-v3 | MIXED | 1 | 10813 | 同败 | 500 / 500 | 24 | 否 | UNRESOLVED |
| G_OPTIMAL | 1 | push-v3 | STATIONARY | 1 | 10819 | 同成 | 91 / 51 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 1 | push-v3 | MIXED | 1 | 10819 | 同成 | 67 / 61 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 1 | reach-v3 | STATIONARY | 1 | 10825 | 同成 | 66 / 47 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 1 | reach-v3 | MIXED | 1 | 10825 | 同成 | 75 / 153 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 1 | door-open-v3 | STATIONARY | 1 | 10831 | 同成 | 133 / 101 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 1 | door-open-v3 | MIXED | 1 | 10831 | 同成 | 105 / 339 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 2 | push-v3 | STATIONARY | 1 | 10837 | 同成 | 104 / 71 | 24 | 否 | UNRESOLVED |
| G_OPTIMAL | 2 | push-v3 | MIXED | 1 | 10837 | 同成 | 104 / 71 | 24 | 否 | UNRESOLVED |
| G_OPTIMAL | 2 | reach-v3 | STATIONARY | 1 | 10843 | 同成 | 106 / 71 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 2 | reach-v3 | MIXED | 1 | 10843 | 同成 | 106 / 71 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 2 | door-open-v3 | STATIONARY | 1 | 10849 | 同成 | 163 / 114 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 2 | door-open-v3 | MIXED | 1 | 10849 | 同成 | 163 / 114 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 3 | push-v3 | STATIONARY | 1 | 10855 | 同成 | 96 / 68 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 3 | push-v3 | MIXED | 1 | 10855 | 有利 | 92 / 500 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 3 | reach-v3 | STATIONARY | 1 | 10861 | 同成 | 99 / 39 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 3 | reach-v3 | MIXED | 1 | 10861 | 同成 | 78 / 28 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 3 | door-open-v3 | STATIONARY | 1 | 10867 | 同成 | 132 / 138 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 3 | door-open-v3 | MIXED | 1 | 10867 | 同成 | 186 / 187 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 4 | push-v3 | STATIONARY | 1 | 10873 | 同成 | 98 / 68 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 4 | push-v3 | MIXED | 1 | 10873 | 同成 | 98 / 68 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 4 | reach-v3 | STATIONARY | 1 | 10879 | 同成 | 79 / 50 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 4 | reach-v3 | MIXED | 1 | 10879 | 同成 | 79 / 50 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 4 | door-open-v3 | STATIONARY | 1 | 10885 | 有害 | 26 / 98 | 20 | 是 | UNRESOLVED |
| G_OPTIMAL | 4 | door-open-v3 | STATIONARY | 2 | 10886 | 有害 | 26 / 106 | 20 | 是 | UNRESOLVED |
| G_OPTIMAL | 4 | door-open-v3 | STATIONARY | 3 | 10887 | 同成 | 99 / 88 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 4 | door-open-v3 | MIXED | 1 | 10885 | 有害 | 26 / 98 | 20 | 是 | UNRESOLVED |
| G_OPTIMAL | 4 | door-open-v3 | MIXED | 2 | 10886 | 有害 | 26 / 106 | 20 | 是 | UNRESOLVED |
| G_OPTIMAL | 4 | door-open-v3 | MIXED | 3 | 10887 | 同成 | 100 / 100 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 5 | push-v3 | STATIONARY | 1 | 10891 | 同成 | 87 / 65 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 5 | push-v3 | MIXED | 1 | 10891 | 有利 | 103 / 500 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 5 | reach-v3 | STATIONARY | 1 | 10897 | 同成 | 68 / 55 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 5 | reach-v3 | MIXED | 1 | 10897 | 有利 | 61 / 500 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 5 | door-open-v3 | STATIONARY | 1 | 10903 | 同成 | 134 / 87 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 5 | door-open-v3 | MIXED | 1 | 10903 | 有利 | 128 / 500 | 16 | 否 | INCOMPATIBLE |
| G_OPTIMAL | 6 | push-v3 | STATIONARY | 1 | 10909 | 同成 | 97 / 75 | 16 | 否 | UNRESOLVED |
| G_OPTIMAL | 6 | push-v3 | STATIONARY | 2 | 10910 | 同成 | 97 / 57 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 6 | push-v3 | MIXED | 1 | 10909 | 有利 | 112 / 500 | 24 | 否 | UNRESOLVED |
| G_OPTIMAL | 6 | reach-v3 | STATIONARY | 1 | 10915 | 同成 | 75 / 51 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 6 | reach-v3 | MIXED | 1 | 10915 | 同成 | 66 / 55 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 6 | door-open-v3 | STATIONARY | 1 | 10921 | 同成 | 127 / 97 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 6 | door-open-v3 | MIXED | 1 | 10921 | 同成 | 202 / 118 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 7 | push-v3 | STATIONARY | 1 | 10927 | 同成 | 92 / 62 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 7 | push-v3 | MIXED | 1 | 10927 | 同成 | 92 / 62 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 7 | reach-v3 | STATIONARY | 1 | 10933 | 同成 | 64 / 45 | 16 | 否 | UNRESOLVED |
| G_OPTIMAL | 7 | reach-v3 | STATIONARY | 2 | 10934 | 同成 | 82 / 58 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 7 | reach-v3 | MIXED | 1 | 10933 | 同成 | 64 / 45 | 16 | 否 | UNRESOLVED |
| G_OPTIMAL | 7 | reach-v3 | MIXED | 2 | 10934 | 同成 | 107 / 88 | 20 | 否 | UNRESOLVED |
| G_OPTIMAL | 7 | door-open-v3 | STATIONARY | 1 | 10939 | 同成 | 127 / 87 | 32 | 否 | UNRESOLVED |
| G_OPTIMAL | 7 | door-open-v3 | MIXED | 1 | 10939 | 同成 | 127 / 87 | 32 | 否 | UNRESOLVED |

## 研究含义与范围

同一缓存、同一六步状态下确实存在纠正有收益的案例；当前 RESPONSE_SET 对全部配对都继续采集，尚未实现取证的选择性费用收益。G_OPTIMAL 的四个有害配对都在门任务刷新拟合失败后停止，表明辨识的数值风险也必须进入后继决策目标。直接延用当前响应阈值或只优化区间宽度，不足以证明任务价值。

比较包含额外测量引起的真实运动、后续模型与控制变化，不能归因于纯信息价值。未测量同一状态上固定宽八／十六步的分支；原始固定基线从初始状态开始，不能拿它们的终点结果冒充六步后刷新反事实。未训练选择器、校准新阈值或进行新 bootstrap／总体显著性检验。

每个分支只有一次已保存的随机实现。有利／有害标签描述这次配对，不等于稳定的期望收益或可部署的动作标签；后继决策研究仍需独立测量重复随机实现下的收益分布。

核查与独立复算均新增机器人步、环境重置、API 调用为零；API 闭环证据仍来自之前单独报告的在线试验。本结果不完成算法创新、概率资格、独立确认或 CCF A 投稿准备。后继协议需要直接比较同一决策状态的真实候选分支，并把失败、停止、采集运动和后续任务步纳入任务相关成本，而不是只识别参数是否变化。
