# 任务期间被动积分适应：完整任务开发与独立资格验证

运行 `task_passive_20261022T032948Z_67fefc4da922`；冻结源码 `67fefc4da9224e0c62b8373d0d4e8cb5b3d1bade`。

本轮是强工程基线，区分参数数值合法、预测能力与完整任务收益。任务 PI 不使用 F20 逆模型，也不代表 ARX／GRU 已恢复有效；限幅和回退不构成安全保证。
每步固定策略查询一次。位置误差是未裁剪 float32 策略动作除以任务固定 P 增益，仅表示当前策略目标，不是最终任务误差。积分以发送命令单位累积，并按实际有界发送命令投影抗饱和；收到真实物理回执后才提交积分状态。

NO_PROBE 无初始探测；DIRECT_C8 使用八步初始标定；MOVE_KEEP_C8 执行原移动后保留标定；MOVE_INTEGRAL 只使用原移动阶段积分。RAW_TASK_PI 从零时刻持续积分；DIRECT_TASK_PI 在 C8 后积分；两个 MOVE_TASK_PI 在共同真实移动后持续积分，分别以 C8／原移动积分为基准。底层策略权重固定，XY 以外的发送命令保持该控制器原值。

开发选择：`{'RAW_TASK_PI': 0.5, 'DIRECT_TASK_PI': 0.5, 'MOVE_KEEP_TASK_PI': 0.5, 'MOVE_INTEGRAL_TASK_PI': 2.0}`；锁定主方法 `DIRECT_TASK_PI_T0.5`；开发门槛 `PASSED_FOR_LOCKED_QUALIFICATION_ONLY`。

时间常数在完整六组开发人口的截止损失上选择，平局取较大时间常数；主程序平局遵循预注册顺序。没有按任务挑参数。独立资格使用九个新组；若开发不优于 DIRECT_C8 和 MOVE_INTEGRAL，则不采集资格人口。

## DEV：DEVELOPMENT_SELECTION_ONLY

| 程序 | 成功／全部 | 平均截止损失↓ | 实际控制步 |
|---|---:|---:|---:|
| NO_PROBE | 29/36 | 164.555556 | 5924 |
| DIRECT_C8 | 30/36 | 149.000000 | 5364 |
| MOVE_KEEP_C8 | 30/36 | 181.111111 | 6520 |
| MOVE_INTEGRAL | 34/36 | 140.333333 | 5052 |
| RAW_TASK_PI_T0.125 | 34/36 | 96.527778 | 3475 |
| RAW_TASK_PI_T0.5 | 35/36 | 80.694444 | 2905 |
| RAW_TASK_PI_T2.0 | 34/36 | 101.277778 | 3646 |
| RAW_TASK_PI_T8.0 | 32/36 | 140.694444 | 5065 |
| DIRECT_TASK_PI_T0.125 | 34/36 | 111.083333 | 3999 |
| DIRECT_TASK_PI_T0.5 | 36/36 | 78.666667 | 2832 |
| DIRECT_TASK_PI_T2.0 | 35/36 | 102.083333 | 3675 |
| DIRECT_TASK_PI_T8.0 | 32/36 | 134.166667 | 4830 |
| MOVE_KEEP_TASK_PI_T0.125 | 34/36 | 139.194444 | 5011 |
| MOVE_KEEP_TASK_PI_T0.5 | 36/36 | 112.750000 | 4059 |
| MOVE_KEEP_TASK_PI_T2.0 | 35/36 | 139.777778 | 5032 |
| MOVE_KEEP_TASK_PI_T8.0 | 32/36 | 167.250000 | 6021 |
| MOVE_INTEGRAL_TASK_PI_T0.125 | 35/36 | 130.194444 | 4687 |
| MOVE_INTEGRAL_TASK_PI_T0.5 | 36/36 | 114.500000 | 4122 |
| MOVE_INTEGRAL_TASK_PI_T2.0 | 36/36 | 114.388889 | 4118 |
| MOVE_INTEGRAL_TASK_PI_T8.0 | 36/36 | 119.138889 | 4289 |

| 锁定主比较 | 平均损失差 | 95% 整组区间 |
|---|---:|---|
| DIRECT_TASK_PI_T0.5_MINUS_DIRECT_C8 | -70.333333 | [-102.916667, -37.750000] |
| DIRECT_TASK_PI_T0.5_MINUS_MOVE_INTEGRAL | -61.666667 | [-72.638889, -50.694444] |

完整任务 × 不变／变化分层：

| 任务 | 条件 | 程序 | 成功／全部 | 平均截止损失↓ |
|---|---|---|---:|---:|
| push-v3 | UNCHANGED | NO_PROBE | 3/6 | 282.500000 |
| push-v3 | UNCHANGED | DIRECT_C8 | 6/6 | 70.166667 |
| push-v3 | UNCHANGED | MOVE_KEEP_C8 | 6/6 | 109.166667 |
| push-v3 | UNCHANGED | MOVE_INTEGRAL | 6/6 | 110.000000 |
| push-v3 | UNCHANGED | RAW_TASK_PI_T0.125 | 4/6 | 222.666667 |
| push-v3 | UNCHANGED | RAW_TASK_PI_T0.5 | 5/6 | 170.000000 |
| push-v3 | UNCHANGED | RAW_TASK_PI_T2.0 | 5/6 | 152.666667 |
| push-v3 | UNCHANGED | RAW_TASK_PI_T8.0 | 3/6 | 282.333333 |
| push-v3 | UNCHANGED | DIRECT_TASK_PI_T0.125 | 4/6 | 262.833333 |
| push-v3 | UNCHANGED | DIRECT_TASK_PI_T0.5 | 6/6 | 79.833333 |
| push-v3 | UNCHANGED | DIRECT_TASK_PI_T2.0 | 6/6 | 70.833333 |
| push-v3 | UNCHANGED | DIRECT_TASK_PI_T8.0 | 6/6 | 69.666667 |
| push-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T0.125 | 5/6 | 186.833333 |
| push-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T0.5 | 6/6 | 106.000000 |
| push-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T2.0 | 6/6 | 107.000000 |
| push-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T8.0 | 6/6 | 109.333333 |
| push-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T0.125 | 5/6 | 176.500000 |
| push-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T0.5 | 6/6 | 108.500000 |
| push-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 6/6 | 108.500000 |
| push-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T8.0 | 6/6 | 109.666667 |
| push-v3 | CHANGED | NO_PROBE | 5/6 | 136.333333 |
| push-v3 | CHANGED | DIRECT_C8 | 3/6 | 286.000000 |
| push-v3 | CHANGED | MOVE_KEEP_C8 | 3/6 | 305.500000 |
| push-v3 | CHANGED | MOVE_INTEGRAL | 6/6 | 114.333333 |
| push-v3 | CHANGED | RAW_TASK_PI_T0.125 | 6/6 | 104.666667 |
| push-v3 | CHANGED | RAW_TASK_PI_T0.5 | 6/6 | 69.000000 |
| push-v3 | CHANGED | RAW_TASK_PI_T2.0 | 5/6 | 138.833333 |
| push-v3 | CHANGED | RAW_TASK_PI_T8.0 | 5/6 | 136.333333 |
| push-v3 | CHANGED | DIRECT_TASK_PI_T0.125 | 6/6 | 130.166667 |
| push-v3 | CHANGED | DIRECT_TASK_PI_T0.5 | 6/6 | 88.166667 |
| push-v3 | CHANGED | DIRECT_TASK_PI_T2.0 | 5/6 | 167.666667 |
| push-v3 | CHANGED | DIRECT_TASK_PI_T8.0 | 3/6 | 285.500000 |
| push-v3 | CHANGED | MOVE_KEEP_TASK_PI_T0.125 | 5/6 | 190.500000 |
| push-v3 | CHANGED | MOVE_KEEP_TASK_PI_T0.5 | 6/6 | 121.666667 |
| push-v3 | CHANGED | MOVE_KEEP_TASK_PI_T2.0 | 5/6 | 198.500000 |
| push-v3 | CHANGED | MOVE_KEEP_TASK_PI_T8.0 | 3/6 | 305.333333 |
| push-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T0.125 | 6/6 | 137.166667 |
| push-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T0.5 | 6/6 | 114.000000 |
| push-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 6/6 | 113.166667 |
| push-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T8.0 | 6/6 | 113.500000 |
| reach-v3 | UNCHANGED | NO_PROBE | 5/6 | 182.833333 |
| reach-v3 | UNCHANGED | DIRECT_C8 | 6/6 | 54.833333 |
| reach-v3 | UNCHANGED | MOVE_KEEP_C8 | 6/6 | 67.666667 |
| reach-v3 | UNCHANGED | MOVE_INTEGRAL | 6/6 | 75.833333 |
| reach-v3 | UNCHANGED | RAW_TASK_PI_T0.125 | 6/6 | 44.666667 |
| reach-v3 | UNCHANGED | RAW_TASK_PI_T0.5 | 6/6 | 37.833333 |
| reach-v3 | UNCHANGED | RAW_TASK_PI_T2.0 | 6/6 | 54.666667 |
| reach-v3 | UNCHANGED | RAW_TASK_PI_T8.0 | 6/6 | 77.666667 |
| reach-v3 | UNCHANGED | DIRECT_TASK_PI_T0.125 | 6/6 | 41.333333 |
| reach-v3 | UNCHANGED | DIRECT_TASK_PI_T0.5 | 6/6 | 45.166667 |
| reach-v3 | UNCHANGED | DIRECT_TASK_PI_T2.0 | 6/6 | 50.666667 |
| reach-v3 | UNCHANGED | DIRECT_TASK_PI_T8.0 | 6/6 | 53.333333 |
| reach-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T0.125 | 6/6 | 61.166667 |
| reach-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T0.5 | 6/6 | 63.333333 |
| reach-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T2.0 | 6/6 | 66.000000 |
| reach-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T8.0 | 6/6 | 67.166667 |
| reach-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T0.125 | 6/6 | 61.500000 |
| reach-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T0.5 | 6/6 | 64.500000 |
| reach-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 6/6 | 70.166667 |
| reach-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T8.0 | 6/6 | 74.000000 |
| reach-v3 | CHANGED | NO_PROBE | 4/6 | 217.000000 |
| reach-v3 | CHANGED | DIRECT_C8 | 3/6 | 279.500000 |
| reach-v3 | CHANGED | MOVE_KEEP_C8 | 3/6 | 289.333333 |
| reach-v3 | CHANGED | MOVE_INTEGRAL | 4/6 | 225.166667 |
| reach-v3 | CHANGED | RAW_TASK_PI_T0.125 | 6/6 | 36.333333 |
| reach-v3 | CHANGED | RAW_TASK_PI_T0.5 | 6/6 | 38.500000 |
| reach-v3 | CHANGED | RAW_TASK_PI_T2.0 | 6/6 | 93.000000 |
| reach-v3 | CHANGED | RAW_TASK_PI_T8.0 | 6/6 | 179.166667 |
| reach-v3 | CHANGED | DIRECT_TASK_PI_T0.125 | 6/6 | 42.666667 |
| reach-v3 | CHANGED | DIRECT_TASK_PI_T0.5 | 6/6 | 75.166667 |
| reach-v3 | CHANGED | DIRECT_TASK_PI_T2.0 | 6/6 | 137.666667 |
| reach-v3 | CHANGED | DIRECT_TASK_PI_T8.0 | 5/6 | 208.333333 |
| reach-v3 | CHANGED | MOVE_KEEP_TASK_PI_T0.125 | 6/6 | 67.833333 |
| reach-v3 | CHANGED | MOVE_KEEP_TASK_PI_T0.5 | 6/6 | 73.666667 |
| reach-v3 | CHANGED | MOVE_KEEP_TASK_PI_T2.0 | 6/6 | 157.666667 |
| reach-v3 | CHANGED | MOVE_KEEP_TASK_PI_T8.0 | 5/6 | 214.666667 |
| reach-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T0.125 | 6/6 | 68.166667 |
| reach-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T0.5 | 6/6 | 72.666667 |
| reach-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 6/6 | 82.666667 |
| reach-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T8.0 | 6/6 | 106.000000 |
| door-open-v3 | UNCHANGED | NO_PROBE | 6/6 | 85.833333 |
| door-open-v3 | UNCHANGED | DIRECT_C8 | 6/6 | 98.500000 |
| door-open-v3 | UNCHANGED | MOVE_KEEP_C8 | 6/6 | 146.666667 |
| door-open-v3 | UNCHANGED | MOVE_INTEGRAL | 6/6 | 155.166667 |
| door-open-v3 | UNCHANGED | RAW_TASK_PI_T0.125 | 6/6 | 86.666667 |
| door-open-v3 | UNCHANGED | RAW_TASK_PI_T0.5 | 6/6 | 85.500000 |
| door-open-v3 | UNCHANGED | RAW_TASK_PI_T2.0 | 6/6 | 85.666667 |
| door-open-v3 | UNCHANGED | RAW_TASK_PI_T8.0 | 6/6 | 85.666667 |
| door-open-v3 | UNCHANGED | DIRECT_TASK_PI_T0.125 | 6/6 | 94.833333 |
| door-open-v3 | UNCHANGED | DIRECT_TASK_PI_T0.5 | 6/6 | 92.166667 |
| door-open-v3 | UNCHANGED | DIRECT_TASK_PI_T2.0 | 6/6 | 93.333333 |
| door-open-v3 | UNCHANGED | DIRECT_TASK_PI_T8.0 | 6/6 | 94.500000 |
| door-open-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T0.125 | 6/6 | 155.333333 |
| door-open-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T0.5 | 6/6 | 149.166667 |
| door-open-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T2.0 | 6/6 | 148.666667 |
| door-open-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T8.0 | 6/6 | 147.333333 |
| door-open-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T0.125 | 6/6 | 157.833333 |
| door-open-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T0.5 | 6/6 | 151.166667 |
| door-open-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 6/6 | 150.000000 |
| door-open-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T8.0 | 6/6 | 149.833333 |
| door-open-v3 | CHANGED | NO_PROBE | 6/6 | 82.833333 |
| door-open-v3 | CHANGED | DIRECT_C8 | 6/6 | 105.000000 |
| door-open-v3 | CHANGED | MOVE_KEEP_C8 | 6/6 | 168.333333 |
| door-open-v3 | CHANGED | MOVE_INTEGRAL | 6/6 | 161.500000 |
| door-open-v3 | CHANGED | RAW_TASK_PI_T0.125 | 6/6 | 84.166667 |
| door-open-v3 | CHANGED | RAW_TASK_PI_T0.5 | 6/6 | 83.333333 |
| door-open-v3 | CHANGED | RAW_TASK_PI_T2.0 | 6/6 | 82.833333 |
| door-open-v3 | CHANGED | RAW_TASK_PI_T8.0 | 6/6 | 83.000000 |
| door-open-v3 | CHANGED | DIRECT_TASK_PI_T0.125 | 6/6 | 94.666667 |
| door-open-v3 | CHANGED | DIRECT_TASK_PI_T0.5 | 6/6 | 91.500000 |
| door-open-v3 | CHANGED | DIRECT_TASK_PI_T2.0 | 6/6 | 92.333333 |
| door-open-v3 | CHANGED | DIRECT_TASK_PI_T8.0 | 6/6 | 93.666667 |
| door-open-v3 | CHANGED | MOVE_KEEP_TASK_PI_T0.125 | 6/6 | 173.500000 |
| door-open-v3 | CHANGED | MOVE_KEEP_TASK_PI_T0.5 | 6/6 | 162.666667 |
| door-open-v3 | CHANGED | MOVE_KEEP_TASK_PI_T2.0 | 6/6 | 160.833333 |
| door-open-v3 | CHANGED | MOVE_KEEP_TASK_PI_T8.0 | 6/6 | 159.666667 |
| door-open-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T0.125 | 6/6 | 180.000000 |
| door-open-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T0.5 | 6/6 | 176.166667 |
| door-open-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 6/6 | 161.833333 |
| door-open-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T8.0 | 6/6 | 161.833333 |
## QUAL：NOT_PASSED

| 程序 | 成功／全部 | 平均截止损失↓ | 实际控制步 |
|---|---:|---:|---:|
| NO_PROBE | 41/54 | 196.574074 | 10615 |
| DIRECT_C8 | 46/54 | 138.870370 | 7499 |
| MOVE_KEEP_C8 | 46/54 | 167.500000 | 9045 |
| MOVE_INTEGRAL | 54/54 | 114.925926 | 6206 |
| RAW_TASK_PI_T0.5 | 53/54 | 83.037037 | 4484 |
| DIRECT_TASK_PI_T0.5 | 53/54 | 101.962963 | 5506 |
| MOVE_KEEP_TASK_PI_T0.5 | 54/54 | 113.407407 | 6124 |
| MOVE_INTEGRAL_TASK_PI_T2.0 | 54/54 | 111.740741 | 6034 |

| 锁定主比较 | 平均损失差 | 95% 整组区间 |
|---|---:|---|
| DIRECT_TASK_PI_T0.5_MINUS_DIRECT_C8 | -36.907407 | [-70.333333, -3.387037] |
| DIRECT_TASK_PI_T0.5_MINUS_MOVE_INTEGRAL | -12.962963 | [-32.703704, 4.925926] |

完整任务 × 不变／变化分层：

| 任务 | 条件 | 程序 | 成功／全部 | 平均截止损失↓ |
|---|---|---|---:|---:|
| push-v3 | UNCHANGED | NO_PROBE | 5/9 | 258.333333 |
| push-v3 | UNCHANGED | DIRECT_C8 | 9/9 | 72.777778 |
| push-v3 | UNCHANGED | MOVE_KEEP_C8 | 9/9 | 101.555556 |
| push-v3 | UNCHANGED | MOVE_INTEGRAL | 9/9 | 112.000000 |
| push-v3 | UNCHANGED | RAW_TASK_PI_T0.5 | 9/9 | 75.666667 |
| push-v3 | UNCHANGED | DIRECT_TASK_PI_T0.5 | 8/9 | 149.111111 |
| push-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T0.5 | 9/9 | 99.666667 |
| push-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 9/9 | 101.444444 |
| push-v3 | CHANGED | NO_PROBE | 7/9 | 162.888889 |
| push-v3 | CHANGED | DIRECT_C8 | 5/9 | 263.444444 |
| push-v3 | CHANGED | MOVE_KEEP_C8 | 4/9 | 323.111111 |
| push-v3 | CHANGED | MOVE_INTEGRAL | 9/9 | 112.333333 |
| push-v3 | CHANGED | RAW_TASK_PI_T0.5 | 8/9 | 130.222222 |
| push-v3 | CHANGED | DIRECT_TASK_PI_T0.5 | 9/9 | 104.888889 |
| push-v3 | CHANGED | MOVE_KEEP_TASK_PI_T0.5 | 9/9 | 121.444444 |
| push-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 9/9 | 111.333333 |
| reach-v3 | UNCHANGED | NO_PROBE | 4/9 | 388.000000 |
| reach-v3 | UNCHANGED | DIRECT_C8 | 9/9 | 57.111111 |
| reach-v3 | UNCHANGED | MOVE_KEEP_C8 | 9/9 | 67.222222 |
| reach-v3 | UNCHANGED | MOVE_INTEGRAL | 9/9 | 73.444444 |
| reach-v3 | UNCHANGED | RAW_TASK_PI_T0.5 | 9/9 | 66.666667 |
| reach-v3 | UNCHANGED | DIRECT_TASK_PI_T0.5 | 9/9 | 85.111111 |
| reach-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T0.5 | 9/9 | 69.666667 |
| reach-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 9/9 | 67.111111 |
| reach-v3 | CHANGED | NO_PROBE | 7/9 | 199.666667 |
| reach-v3 | CHANGED | DIRECT_C8 | 5/9 | 253.777778 |
| reach-v3 | CHANGED | MOVE_KEEP_C8 | 6/9 | 209.888889 |
| reach-v3 | CHANGED | MOVE_INTEGRAL | 9/9 | 87.222222 |
| reach-v3 | CHANGED | RAW_TASK_PI_T0.5 | 9/9 | 54.666667 |
| reach-v3 | CHANGED | DIRECT_TASK_PI_T0.5 | 9/9 | 82.000000 |
| reach-v3 | CHANGED | MOVE_KEEP_TASK_PI_T0.5 | 9/9 | 85.555556 |
| reach-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 9/9 | 78.000000 |
| door-open-v3 | UNCHANGED | NO_PROBE | 9/9 | 85.555556 |
| door-open-v3 | UNCHANGED | DIRECT_C8 | 9/9 | 92.777778 |
| door-open-v3 | UNCHANGED | MOVE_KEEP_C8 | 9/9 | 149.555556 |
| door-open-v3 | UNCHANGED | MOVE_INTEGRAL | 9/9 | 149.555556 |
| door-open-v3 | UNCHANGED | RAW_TASK_PI_T0.5 | 9/9 | 85.555556 |
| door-open-v3 | UNCHANGED | DIRECT_TASK_PI_T0.5 | 9/9 | 96.222222 |
| door-open-v3 | UNCHANGED | MOVE_KEEP_TASK_PI_T0.5 | 9/9 | 144.111111 |
| door-open-v3 | UNCHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 9/9 | 151.666667 |
| door-open-v3 | CHANGED | NO_PROBE | 9/9 | 85.000000 |
| door-open-v3 | CHANGED | DIRECT_C8 | 9/9 | 93.333333 |
| door-open-v3 | CHANGED | MOVE_KEEP_C8 | 9/9 | 153.666667 |
| door-open-v3 | CHANGED | MOVE_INTEGRAL | 9/9 | 155.000000 |
| door-open-v3 | CHANGED | RAW_TASK_PI_T0.5 | 9/9 | 85.444444 |
| door-open-v3 | CHANGED | DIRECT_TASK_PI_T0.5 | 9/9 | 94.444444 |
| door-open-v3 | CHANGED | MOVE_KEEP_TASK_PI_T0.5 | 9/9 | 160.000000 |
| door-open-v3 | CHANGED | MOVE_INTEGRAL_TASK_PI_T2.0 | 9/9 | 160.888889 |

## 完整成本与范围

| 阶段 | 执行 | 控制步 | 全部重置 | 物理帧 | 在线 C4/C8 估计尝试 |
|---|---:|---:|---:|---:|---:|
| SOFTWARE_NATIVE | 36 | 6906 | 1836 | 952530 | 54 |
| DEV | 720 | 90626 | 36720 | 18813130 | 1080 |
| QUAL | 432 | 55513 | 22032 | 11293565 | 648 |

截止损失是成功时的全部实际控制步，失败／无效初始估计为 500；初始探测和实际移动已经计入一次。受控初始重置后不重置、不恢复状态、不替换噪声；未到边界或移动阶段的提前成功保留完整分母。
历史名义 C8 完整来源另有 480 次执行、3,840 控制步、24,480 全部重置和 12,259,200 物理帧。NO_PROBE 和 RAW_TASK_PI 不读取或收取该模型。每个选定 PI 程序还必须披露完整开发人口的调参费用，不能只报告获胜参数或成功分支；软件契约费用另列。
组是独立统计单位，同一组中的任务、条件、程序及相关时间步不能增加独立样本量。bootstrap 在 16／32／64 步三个边界层内重采样完整组。全部二级配对比较及失败案例编号在统计 JSON 中；二级区间为未作多重比较校正的描述性结果。
原生审计核对保存先于执行、真实回执后提交积分、一次策略查询、float32 仿射→实际噪声→最终裁剪、全部工厂／受控重置和物理帧，并检查共同移动后的状态。它使用原始状态见证与记录复算，不等同于独立物理引擎或实机验证。
本轮新增响应模型训练、策略训练和在线 LLM API 调用均为 0。全部失败、负结果和原始日志保留；不补采、换种子或挑选有利任务。
本轮仅建立任务期间被动适应的强对照。即使任务门槛通过，也不是算法创新或 CCF A 目标完成。移动前的获取决策还须与这一强对照实际部署比较，并在独立自身时序历史上验证完整获取成本、错误更新与消融；若无额外收益，应保留反证。
