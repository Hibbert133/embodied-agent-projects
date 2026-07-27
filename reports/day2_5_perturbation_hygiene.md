# Day 2.5 Perturbation Hygiene

## Scope and semantic correction

本阶段基于 `c810465b8fe9c5e3bf55bf0b1d7e20d408db14ca`，开发分支为
`fix/perturbation-semantics`。旧 scalar bias 会广播至 `[dx,dy,dz,gripper]`，把夹爪
控制与平移控制混合，无法解释为单轴执行器偏差。schema v2 因此拒绝 scalar bias，要求
完整四维向量，并默认只允许 mask `(True,True,True,False)`。夹爪决定接触/抓持状态，扰动
它会引入与平移偏差不同的故障机制，所以本阶段保持 gripper 不变。

## Agent View and Oracle View

Agent View 仅含 `schema_version, episode_id, seed, step, observation,
next_observation, commanded_action, reward, success, terminated, truncated,
task_progress_metrics`。其中 `commanded_action` 严格等于策略的 `raw_action`，表示策略向
执行系统发出的命令，而不是注入偏差并裁剪后的动作。
Oracle View 另外含 `raw_action, perturbed_action, executed_action,
perturbation_type, perturbation_parameters, was_clipped, clipped_element_count`。
`executed_action` 仅属于 Oracle View。每条 transition 对齐为
`state_t + commanded_action_t → state_t+1`：`observation` 是动作前状态，
`next_observation` 是环境 step 返回的动作后状态，reward、终止标志和 success 也属于这次
step 的结果，task metrics 基于 `next_observation` 计算。未来诊断接口只能接收严格校验的
schema-v2 Agent View，不能通过动作差值获知注入真值。

旧 schema v1 缺少 `next_observation`，且 `commanded_action` 语义不可靠，不进行批量迁移。
Day 3 只允许读取本修复后生成并通过必要字段校验的 schema v2。修复前生成的实验审计轨迹
即使曾带有版本字段，也不应作为 Day 3 Agent View 输入。旧代表轨迹现已由重新运行
`scripts/render_day2_5_representatives.py` 产生的 schema-v2 文件覆盖；唯一统一目录为
`outputs/representative_trajectories/`，Day 3 只能读取这些重新生成并通过验证器的文件。

## Observation and task metrics provenance

已检查本机 MetaWorld 3.1.1 源码：`SawyerXYZEnv._get_obs()` 拼接当前 18 维、上一帧
18 维和 goal 3 维；`_get_curr_obs_combined_no_goal()` 先放 hand position，再放 gripper
opening 和 object position/quaternion。因此当前 gripper 为 `[0:3]`、object 为 `[4:7]`、
goal 为 `[-3:]`。`SawyerPushEnvV3.compute_reward()` 也明确使用 `obs[4:7]`。距离单位是
MuJoCo 米。`progress_to_goal = initial_object_goal_distance - current_distance`；
`lateral_drift` 是 object 到初始 object→goal 的 XY 直线垂距。所有指标只使用当前和初始
observation，不访问未来状态。return 保留为辅助指标，不作为主要进度依据。

## 20-seed coarse scan (seeds 100–119)

| Axis | Direction | Magnitude | Success | Mean steps | Final distance (m) | Clipped-step fraction |
|---|---|---:|---:|---:|---:|---:|
| x | positive | 0.00 | 100% | 62.75 | 0.0479 | 45.50% |
| x | positive | 0.02 | 100% | 63.00 | 0.0477 | 45.32% |
| x | positive | 0.04 | 100% | 70.60 | 0.0477 | 43.56% |
| x | positive | 0.06 | 100% | 69.15 | 0.0478 | 43.89% |
| x | positive | 0.08 | 95% | 88.95 | 0.0497 | 35.30% |
| x | positive | 0.10 | 90% | 118.95 | 0.0577 | 28.37% |
| x | positive | 0.12 | 65% | 222.60 | 0.0761 | 18.24% |
| x | negative | 0.00 | 100% | 62.75 | 0.0479 | 45.50% |
| x | negative | 0.02 | 100% | 63.15 | 0.0478 | 45.29% |
| x | negative | 0.04 | 100% | 63.10 | 0.0477 | 45.25% |
| x | negative | 0.06 | 100% | 63.40 | 0.0477 | 45.03% |
| x | negative | 0.08 | 90% | 106.30 | 0.0687 | 26.67% |
| x | negative | 0.10 | 95% | 94.70 | 0.0565 | 32.58% |
| x | negative | 0.12 | 80% | 152.80 | 0.0964 | 20.84% |
| y | positive | 0.00 | 100% | 62.75 | 0.0479 | 45.50% |
| y | positive | 0.02 | 100% | 62.10 | 0.0481 | 46.05% |
| y | positive | 0.04 | 100% | 61.75 | 0.0474 | 46.32% |
| y | positive | 0.06 | 100% | 61.15 | 0.0475 | 46.77% |
| y | positive | 0.08 | 100% | 61.70 | 0.0478 | 46.76% |
| y | positive | 0.10 | 85% | 129.60 | 0.1027 | 21.95% |
| y | positive | 0.12 | 90% | 110.35 | 0.0809 | 25.15% |
| y | negative | 0.00 | 100% | 62.75 | 0.0479 | 45.50% |
| y | negative | 0.02 | 100% | 63.80 | 0.0475 | 44.59% |
| y | negative | 0.04 | 100% | 64.30 | 0.0485 | 44.09% |
| y | negative | 0.06 | 95% | 87.10 | 0.0502 | 34.90% |
| y | negative | 0.08 | 95% | 88.15 | 0.0513 | 34.37% |
| y | negative | 0.10 | 95% | 88.95 | 0.0593 | 32.77% |
| y | negative | 0.12 | 85% | 133.35 | 0.0629 | 24.90% |

预设无 40%–60% 候选。自动细搜 +x 0.125–0.150 后，0.145 得到 50%（20 seeds），
成功/失败 final distance 分别约 0.0476/0.2202 m。

## Selected configuration and 50-seed validation

最终选择 `axis=x, direction=positive, magnitude=0.145`。seeds 100–149 的结果为：

- success rate：44%（22/50），Wilson 95% CI `[31.16%, 57.69%]`
- failures / recovery-relevant failures：28 / 28（均为正常运行至 500 steps 的任务失败）
- mean / median steps：334.34 / 500
- mean final object-goal distance：0.16045 m；成功 0.04789 m，失败 0.24889 m
- clipped-step fraction：18.83%
- clipped-element fraction：4.85%

该配置同时产生足量成功和失败，裁剪率没有极端增加，且失败不是异常或环境崩溃。

## Visual evidence and limitations

代表视频在 `outputs/videos/`：seed 100 为成功，seed 148 为典型失败，seed 135 为
最接近目标但最终失败；对应 schema-v2 JSONL 位于 `outputs/representative_trajectories/`。
轨迹语义修复只改变记录字段：相同 seeds 的 success、steps、return 和最终距离与原
50-seed CSV 完全一致，既有实验结论不变。
图表位于 `outputs/figures/`，全部直接读取真实 CSV。局限包括仅使用一个任务/脚本策略、
50 seeds 的置信区间仍较宽、near-success 仅按最终距离选择，以及 MetaWorld observation-space
边界 warning。没有实现失败诊断、适应、记忆、LLM 或学习。

## Reproduction commands

```powershell
python scripts/evaluate_push.py --num-episodes 20 --seed-start 100 --max-steps 500 --output-csv outputs/day2_5/baseline.csv --trajectory-dir outputs/day2_5/baseline_trajectories
python scripts/demo_push.py --output outputs/day2_5/demo_regression.mp4 --trajectory-output outputs/day2_5/demo_regression.jsonl --seed 42 --max-steps 500 --fps 30
python scripts/sweep_perturbations.py --perturbation-type action_bias --bias-axis all --bias-sign all --levels 0 0.02 0.04 0.06 0.08 0.10 0.12 --num-episodes 20 --seed-start 100 --max-steps 500 --output-csv outputs/day2_5/single_axis_bias_20_seed.csv --summary-csv outputs/day2_5/single_axis_bias_20_seed_summary.csv
python scripts/sweep_perturbations.py --perturbation-type action_bias --bias-axis x --bias-sign positive --levels 0.125 0.130 0.135 0.140 0.145 0.150 --num-episodes 20 --seed-start 100 --max-steps 500 --output-csv outputs/day2_5/single_axis_bias_fine_20_seed.csv --summary-csv outputs/day2_5/single_axis_bias_fine_20_seed_summary.csv
python scripts/sweep_perturbations.py --perturbation-type action_bias --bias-axis x --bias-sign positive --levels 0.145 --num-episodes 50 --seed-start 100 --max-steps 500 --output-csv outputs/day2_5/selected_config_50_seed.csv --summary-csv outputs/day2_5/selected_config_50_seed_summary.csv
python scripts/render_day2_5_representatives.py
python scripts/plot_day2_5_results.py
python -m unittest discover -s tests -v
python -m pip check
git diff --check
```
