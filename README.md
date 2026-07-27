# MetaWorld Push 可视化入门

这是一个不训练强化学习模型的具身智能示例：在 MetaWorld 的 `push-v3`
任务中运行内置脚本策略，用 MuJoCo 的 `render_mode="rgb_array"` 获取 RGB 帧，
保存 rollout 视频和 JSONL 轨迹，并支持多个 episode 的批量评测。

## 项目结构

```text
.
├── INSTALL.md
├── README.md
├── requirements.txt
├── outputs/
│   ├── push_demo.mp4         # rollout 视频
│   ├── push_demo.jsonl       # 视频对应的逐步轨迹
│   ├── push_evaluation.csv   # 批量评测汇总
│   ├── push_trajectories/    # 每个评测 episode 的 JSONL
│   ├── perturbation_sweep.csv    # 每个扰动 episode 的详细结果
│   ├── perturbation_summary.csv  # 按扰动强度汇总的结果
│   └── perturbation_videos/      # 代表性成功/失败 rollout 视频与轨迹
├── src/
│   ├── rollout.py            # 可复用的 episode rollout 逻辑
│   ├── trajectory.py         # 轨迹结构与 JSONL 保存
│   └── perturbations.py      # 统一动作扰动接口
├── scripts/
│   ├── check_install.py      # 版本、环境创建、渲染冒烟测试
│   ├── demo_push.py          # push rollout、视频与轨迹保存
│   ├── evaluate_push.py      # 多 episode 批量评测
│   ├── sweep_perturbations.py # 配对 seed 的扰动强度扫描
│   └── render_perturbation_videos.py # 扰动对比视频
└── tests/
    └── test_trajectory.py
```

## 完整运行命令

先按 [INSTALL.md](INSTALL.md) 创建 Python 3.10 环境并安装依赖。Windows
PowerShell 中的完整命令是：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/check_install.py
python scripts/demo_push.py
```

成功后，视频位于 `outputs/push_demo.mp4`。脚本默认最多运行 500 步；也可以指定参数：

```powershell
python scripts/demo_push.py --output outputs/push_demo.mp4 --seed 42 --max-steps 500 --fps 30
```

默认还会将同一次 rollout 的轨迹保存到 `outputs/push_demo.jsonl`。可以单独指定：

```powershell
python scripts/demo_push.py --trajectory-output outputs/my_trajectory.jsonl
```

运行 10 个 episode 的批量评测：

```powershell
python scripts/evaluate_push.py --num-episodes 10 --seed-start 100 --max-steps 500 --output-csv outputs/push_evaluation.csv --trajectory-dir outputs/push_trajectories
```

评测在每个 episode 首次达到 success 时立即停止，汇总结果写入
`outputs/push_evaluation.csv`，逐 episode 轨迹写入 `outputs/push_trajectories/`。
运行轨迹单元测试：

```powershell
python -m unittest tests.test_trajectory -v
```

运行默认动作扰动扫描；每个配置使用完全相同的一组 episode seeds：

```powershell
python scripts/sweep_perturbations.py --num-episodes 20 --seed-start 100 --max-steps 500 --output-csv outputs/perturbation_sweep.csv --summary-csv outputs/perturbation_summary.csv
```

也可以选择一种扰动并指定强度：

```powershell
python scripts/sweep_perturbations.py --perturbation-type action_bias --levels 0.06 0.07 --num-episodes 20
```

生成一组可复现的代表性扰动 rollout 视频（包括成功和失败样本）：

```powershell
python scripts/render_perturbation_videos.py --max-steps 500 --fps 30
```

视频和对应 JSONL 轨迹写入 `outputs/perturbation_videos/`，实际结果清单写入该目录的
`manifest.csv`。文件名标明扰动类型、强度、结果和 seed；脚本仍会重新执行每个 rollout，
并把本次真实的 success、steps、return 和裁剪统计写入清单。

这些脚本都应从项目根目录运行。它们不要求 GPU/CUDA，也不会训练或下载策略权重。

完整的 Day 2 实验设置、真实结果、图表和代表性视频见
[DAY2_PERTURBATION_STUDY.md](DAY2_PERTURBATION_STUDY.md)。

Day 2.5 修正了扰动语义：默认 mask 为 `(x, y, z)`，gripper 不受 scale、noise
或 bias 影响；bias 必须提供完整 4 维向量。轨迹 schema v2 提供无扰动真值的
Agent View 和供审计使用的 Oracle View，并增加基于 MetaWorld 3.1.1 observation
源码布局的 push 进度指标。完整说明和真实实验见
[reports/day2_5_perturbation_hygiene.md](reports/day2_5_perturbation_hygiene.md)。

## Episode、rollout、trajectory、return 和 success rate

- `episode`：环境从一次 `reset()` 开始，到成功、自然终止、时间截断或达到脚本步数
  上限为止的一次完整尝试。
- `rollout`：策略在环境中连续选择动作并产生状态转移的执行过程。一个 rollout
  通常对应一个 episode；demo 为了保留完整 500 步视频，成功后仍继续到环境结束。
- `trajectory`（轨迹）：rollout 中按时间排序的逐步记录。本项目每行 JSON 保存
  episode_id、seed、step、执行动作前的 observation，以及该动作产生的 reward、
  success、terminated 和 truncated。success 是累计状态，一旦成功就不会变回 False。
- `return`（回报）：一个 episode 内所有 step reward 的总和。这里仅用于评价脚本策略，
  不用于训练。
- `success rate`（成功率）：成功 episode 数除以总 episode 数。

## 可控动作扰动

- `ActionScalePerturbation`（动作缩放）：按固定比例缩放策略动作，用于模拟执行器
  增益不足、运动速度下降或控制响应衰减。
- `GaussianNoisePerturbation`（高斯噪声）：在每一步加入由 episode seed 独立生成的
  随机噪声，用于模拟传感器到控制链路的抖动或低层控制噪声。它不使用全局
  `np.random` 状态，相同 seed 可以完全复现。
- `ActionBiasPerturbation`（固定偏差）：在动作上持续加入固定偏移，用于模拟执行器
  零点误差、标定偏差或长期控制漂移。默认强度扫描使用标量偏差，并将它广播到
  全部动作维度。

动作依次经过 `raw_action`、`perturbed_action`、范围裁剪和 `executed_action`。
轨迹格式已升级，新增这三个字段以及 `was_clipped`。为兼容旧读取代码，原有
`action` 字段继续保留，并与真正送入环境的 `executed_action` 相同。每个 episode
还会统计 `clip_count` 和 `clip_fraction`。

## 一次交互中各变量的含义

Gymnasium 风格的一步交互是：

```python
observation, reward, terminated, truncated, info = env.step(action)
success = bool(info.get("success", False))
```

- `observation`（观测）：机器人当前能得到的状态向量。此任务中包含机械臂末端、
  夹爪、物体以及目标等状态；它是策略决定下一步动作的输入，不是渲染出的 RGB 图像。
- `action`（动作）：传给环境的 4 维连续控制量。前三维控制末端执行器在 x/y/z
  方向的位移趋势，最后一维控制夹爪；数值受动作空间范围限制。
- `reward`（奖励）：环境对当前一步进展给出的标量反馈。物体更接近目标通常会得到
  更高奖励。这里仅记录它，不用它训练模型。
- `terminated`（自然终止）：任务到达环境定义的终止状态。MetaWorld 的不少任务即使
  已成功也不一定立即把它设为 `True`，因此还要查看 `success`。
- `truncated`（截断）：episode 因时间步上限等外部限制而停止，而不是因任务本身的
  终止条件停止。
- `success`（成功）：`info["success"]` 给出的任务成功指标；在 push 中表示物体已被
  推到目标区域附近。它与 `terminated` 是不同概念。

脚本使用 MetaWorld 自带的 `SawyerPushV3Policy`。它是手写脚本策略，不是训练得到的
强化学习模型。

## 常见错误

- Python 不是 3.10：`check_install.py` 会直接报错并显示当前版本。
- 无法创建 MuJoCo 渲染上下文：确认图形驱动可用，并先运行安装检查获取明确错误。
  无 GPU 的 Windows Server/虚拟机请按 [INSTALL.md](INSTALL.md) 的 Mesa CPU
  软件 OpenGL 小节配置。
- MP4 写入失败：重新执行 `python -m pip install -r requirements.txt`，确保
  `imageio-ffmpeg` 已安装。
