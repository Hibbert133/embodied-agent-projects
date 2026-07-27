# Day 2 Perturbation Study

## Objective

在 MetaWorld `push-v3` 无扰动 baseline 基础上，加入可复现的动作缩放、高斯噪声和固定偏差，扫描扰动强度，并选择成功率为 30%–70% 的中等难度配置。本阶段不包含失败诊断、参数自适应、记忆、LLM 或强化学习。

## GitHub

- 仓库：<https://github.com/Hibbert133/embodied-agent-projects.git>
- Commit：Day 2 已提交为 `c810465b8fe9c5e3bf55bf0b1d7e20d408db14ca`。

## Experimental Setup

- 任务：MetaWorld `push-v3`
- 策略：`SawyerPushV3Policy`
- episode seeds：100–119，所有配置使用相同 seeds
- 每个配置 episode 数：20
- 最大步数：500
- 执行环境：Python 3.10、CPU、MuJoCo `rgb_array`
- 达到 success 后立即停止 episode

## Perturbations

- Action scale：将动作乘以固定比例，模拟执行器增益不足或控制响应衰减。
- Gaussian noise：每步加入高斯噪声，使用由 episode seed 初始化的独立 NumPy Generator，模拟低层控制抖动。
- Action bias：持续加入固定动作偏移，模拟执行器零点误差或标定偏差。

## Quantitative Results

### Action scale

| Level | Success rate | Average steps | Clip fraction |
|---:|---:|---:|---:|
| 1.0 | 100% | 62.75 | 45.50% |
| 0.8 | 100% | 70.95 | 31.29% |
| 0.6 | 90% | 140.85 | 6.53% |
| 0.4 | 100% | 158.05 | 0.44% |
| 0.2 | 100% | 302.35 | 0.00% |

### Gaussian noise

| Level | Success rate | Average steps | Clip fraction |
|---:|---:|---:|---:|
| 0.00 | 100% | 62.75 | 45.50% |
| 0.02 | 100% | 62.75 | 45.66% |
| 0.05 | 100% | 62.80 | 46.10% |
| 0.10 | 100% | 62.60 | 45.93% |
| 0.20 | 95% | 86.60 | 34.53% |

### Action bias

| Level | Success rate | Average steps | Clip fraction |
|---:|---:|---:|---:|
| 0.00 | 100% | 62.75 | 45.50% |
| 0.02 | 100% | 62.80 | 45.54% |
| 0.05 | 90% | 120.90 | 22.95% |
| 0.10 | 0% | 500.00 | 3.43% |
| 0.15 | 0% | 500.00 | 59.04% |

预设 bias 强度未得到中等成功率，进一步局部搜索得到：0.06 为 90%、0.07 为 85%、0.08 为 50%、0.09 为 25%。

## Selected Medium-Difficulty Configuration

- 扰动类型：Action bias
- 扰动强度：0.08
- 成功率：50%（10/20）
- 平均步数：294.30
- clip fraction：6.63%

## Visualization

- [成功率图](outputs/perturbation_plots/success_rate.svg)
- [平均步数图](outputs/perturbation_plots/average_steps.svg)
- [动作裁剪比例图](outputs/perturbation_plots/clip_fraction.svg)
- [详细 CSV](outputs/perturbation_sweep.csv)
- [汇总 CSV](outputs/perturbation_summary.csv)

## Representative Success and Failure Cases

- 成功：[bias 0.08, seed 102](outputs/perturbation_videos/bias_0.08_success_seed102.mp4)
- 失败：[bias 0.08, seed 100](outputs/perturbation_videos/bias_0.08_failure_seed100.mp4)
- 其他代表性视频及逐步轨迹：[视频目录](outputs/perturbation_videos/)
- 视频真实结果清单：[manifest.csv](outputs/perturbation_videos/manifest.csv)

## Observations

- Action scale 降低主要增加完成任务所需步数；在本次 20-seed 样本中，成功率不是严格单调的，因此不能表述为“随强度平滑下降”。
- Gaussian noise 在预设最高强度 0.20 时仍有 95% 成功率，没有观察到 0.10 后突然崩溃。
- Action bias 对策略最敏感：成功率从 0.07 的 85% 降至 0.08 的 50%，到 0.10 降为 0%。
- clip fraction 并不等价于难度。零扰动已有 45.50% 裁剪，而 bias 0.10 的裁剪率只有 3.43%，但成功率为 0%。

## Limitations

1. 每个配置只有 20 个 seeds，成功率仍存在抽样波动；例如 scale 的成功率未呈单调关系。
2. 只评测了 `push-v3` 和内置脚本策略，结论不能直接推广到其他任务或学习策略。
3. 当前图表按每种扰动自身的 level 排列，不应跨扰动类型直接比较同一数值的物理含义。

## Reproduction Commands

```powershell
python scripts/evaluate_push.py --num-episodes 20 --seed-start 100 --max-steps 500
python scripts/sweep_perturbations.py --num-episodes 20 --seed-start 100 --max-steps 500
python scripts/sweep_perturbations.py --perturbation-type action_bias --levels 0.06 0.07 0.08 0.09 --num-episodes 20 --append
python scripts/plot_perturbation_results.py
python scripts/render_perturbation_videos.py --max-steps 500 --fps 30
python -m unittest discover -s tests -v
python -m py_compile src/perturbations.py src/trajectory.py src/rollout.py scripts/evaluate_push.py scripts/sweep_perturbations.py scripts/plot_perturbation_results.py scripts/render_perturbation_videos.py
python -m pip check
git diff --check
```

测试结果：10/10 单元测试通过；`py_compile`、`pip check` 和 `git diff --check` 通过；6 个代表性 MP4 均可解码且帧数有效。
