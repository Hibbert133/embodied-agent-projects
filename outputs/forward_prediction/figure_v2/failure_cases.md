# 前向预测失败记录

运行 `forward_prediction_20261014T064233Z_bb812df15401`。
Manifest `d657fa9c3d0d6582f02a0dc7f346fdf7dbd013da977e93355bbacc7477a6868f`；冻结提交 `bb812df15401fdaa702659294be1e457dd309758`。

以下为区间未覆盖，不改写任务成功；模型从未参与动作选择。

| 种子 | 任务 | 程序 | 模型 | 最大误差 mm | 冻结半径 mm | 任务成功 |
|---|---|---|---|---:|---:|---|
| 10400 | reach-v3 | POLICY_ONLY | QUADRATIC_STATE | 1.8549 | 1.2643 | True |
| 10400 | reach-v3 | PROBE_THEN_POLICY | QUADRATIC_STATE | 1.9645 | 1.7307 | True |
| 10403 | reach-v3 | POLICY_ONLY | QUADRATIC_STATE | 1.4238 | 1.2643 | True |
| 10403 | reach-v3 | PROBE_THEN_POLICY | QUADRATIC_STATE | 2.0081 | 1.7307 | True |
| 10404 | reach-v3 | POLICY_ONLY | QUADRATIC_STATE | 1.8111 | 1.2643 | True |
| 10407 | push-v3 | PROBE_THEN_POLICY | LEGACY_ARX | 1.7894 | 1.7588 | True |
| 10408 | reach-v3 | PROBE_THEN_POLICY | LEGACY_ARX | 1.2716 | 1.2690 | True |
| 10412 | push-v3 | PROBE_THEN_POLICY | NEAREST_STATE | 3.0123 | 2.6090 | True |

## 名义任务失败

| 阶段 | 种子 | 任务 | 程序 | 实际步数 |
|---|---|---|---|---:|
| CALIBRATION | 10314 | door-open-v3 | POLICY_ONLY | 500 |
