# 名义响应观察：多任务独立审计

状态 `COMPLETED_FEASIBILITY_FAILED`；完整性 `PASSED`。

| 任务/程序 | 有块轨迹/16 | 轨迹最大块误差 p90 | 最大值 | 名义任务成功/16 |
|---|---:|---:|---:|---:|
| push-v3|POLICY_ONLY | 16 | 0.5433 | 0.5743 | 16 |
| push-v3|PROBE_THEN_POLICY | 16 | 0.5705 | 0.5901 | 16 |
| reach-v3|POLICY_ONLY | 16 | 0.4301 | 0.4735 | 16 |
| reach-v3|PROBE_THEN_POLICY | 16 | 0.4627 | 0.4662 | 16 |
| door-open-v3|POLICY_ONLY | 16 | 2.8665 | 4.1822 | 16 |
| door-open-v3|PROBE_THEN_POLICY | 16 | 2.6214 | 3.0011 | 16 |

固定可行性门：`{'push-v3|POLICY_ONLY': False, 'push-v3|PROBE_THEN_POLICY': False, 'reach-v3|POLICY_ONLY': False, 'reach-v3|PROBE_THEN_POLICY': False, 'door-open-v3|POLICY_ONLY': False, 'door-open-v3|PROBE_THEN_POLICY': False}`。

新物理成本 6933 步/96 初始重置；原离线资源 2,304 步/144 次重置另列。

公开名义零偏置、噪声标准差 0.05；新任务与程序各 16 个种子。平均四步误差是经验结果，不是 Gaussian 噪声的确定性界。

观察资格、概率/任务成功保证仍未建立。被动点辨识没有改变本轮动作，也没有与新控制方法比较任务收益。

Independent inverse formula, saved snapshots before evaluator labels, fixed-policy commands, full visible state/RNG chains and costs. No task dynamics resimulation; empirical feasibility is not a physical/probability contract.
