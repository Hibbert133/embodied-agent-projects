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
│   ├── perturbations.py      # 统一动作扰动接口
│   ├── diagnostic_probes.py  # 泄漏安全的主动对称探测与偏差估计
│   ├── recovery_agent.py     # 受约束的高层恢复 Agent 与对照组
│   └── openai_recovery_planner.py # 可选 Responses API planner
├── scripts/
│   ├── check_install.py      # 版本、环境创建、渲染冒烟测试
│   ├── demo_push.py          # push rollout、视频与轨迹保存
│   ├── evaluate_push.py      # 多 episode 批量评测
│   ├── sweep_perturbations.py # 配对 seed 的扰动强度扫描
│   ├── run_active_diagnostic_probes.py # 主动探测证据采集
│   ├── render_perturbation_videos.py # 扰动对比视频
│   └── run_recovery_agent.py # 有限 rollout 预算恢复实验
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

轨迹 transition 的严格语义为
`observation(state_t) + commanded_action(action_t) → next_observation(state_t+1)`。
`commanded_action` 是策略原始输出；扰动后并裁剪的 `executed_action` 只在 Oracle View
中用于实验审计。`task_progress_metrics` 基于 `next_observation` 计算。Day 3 只能读取
严格校验后的 schema-v2 Agent View，不能读取人工注入 bias 的类型、方向、强度或动作差值。

## 高层恢复 Agent 与 OpenAI API

本项目中的 Agent 不是替代 `SawyerPushV3Policy` 的逐步控制器。低层策略继续输出每个
timestep 的动作；高层恢复 Agent 在一次完整失败 rollout 后读取 schema-v2 Agent View，
提出下一次 rollout 使用的固定 x/y 命令补偿，并根据新证据决定下一次实验：

```text
失败轨迹 -> Agent-visible evidence -> 补偿提案 -> 本地校验 -> 新 rollout
```

提案只能选择 `x/y`、正负方向和预先批准的幅值。Agent 没有 shell、文件编辑或直接环境
控制权限，也看不到 `perturbation_type`、注入 bias、`perturbed_action` 或
`executed_action`。补偿由 `CompensatedPolicy` 加到低层策略输出中，因此它属于机器人
真实发出的 `commanded_action`；隐藏扰动仍在其后由实验执行系统施加。

系统支持无恢复、随机搜索、确定性规则、OpenAI planner 和知道隐藏 bias 的 Oracle 上界。
运行规则 Agent：

```powershell
python scripts/run_recovery_agent.py --planner rule --seed-start 100 --num-episodes 3 --max-trials 5 --bias-axis x --bias-sign positive --bias-magnitude 0.145
```

只在代表性案例中显式开启视频，避免渲染影响量化实验耗时：

```powershell
python scripts/run_recovery_agent.py --planner oracle --seed-start 148 --max-trials 2 --video-dir outputs/recovery/videos
```

OpenAI planner 使用 Responses API。密钥只通过环境变量提供，不得写入仓库：

```powershell
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_MODEL="gpt-5.6-luna"
python scripts/run_recovery_agent.py --planner openai --seed-start 100 --num-episodes 3 --max-trials 5 --bias-axis x --bias-sign positive --bias-magnitude 0.145
```

默认每个 episode 最多执行 5 个总 trial（包含初始无补偿 trial），成功立即停止。CSV 写入
`outputs/recovery/trials.csv`，逐 trial 的 schema-v2 轨迹写入
`outputs/recovery/trajectories/`，模型版本、prompt hash、response ID、token usage 和延迟写入
`outputs/recovery/planner_audit.jsonl`。API 错误会被明确报告，不会静默换成规则 Agent；
`none/random/rule/oracle` 均不需要 API key。

系统也支持 Anthropic Messages 协议兼容服务，例如显式指定 `glm-5.1` 的 ModelArts
端点。推荐使用安全启动脚本；它只在当前进程中临时设置密钥，结束时立即清除：

```powershell
.\scripts\run_anthropic_recovery.ps1 -Model glm-5.1 -Seed 148 -MaxTrials 5
```

该安全脚本默认按 `RunName` 把 CSV、审计、轨迹和每个 trial 的视频隔离保存到
`outputs/recovery/runs/<RunName>/`；可通过 `-Fps` 修改帧率。视频渲染会增加 wall-clock
时间，因此量化延迟比较仍应使用不录视频的
`run_recovery_agent.py` 命令。

兼容端点默认允许单次请求等待 180 秒并最多重试 2 次；可用
`-ApiTimeout 300 -ApiMaxRetries 3` 调整。每个完成的 trial 会立即 checkpoint 到 CSV 和审计
JSONL，因此后续请求超时不会丢失已完成的 rollout。

也可以自行设置 `ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL` 和 `LLM_MODEL` 后运行：

```powershell
python scripts/run_recovery_agent.py --planner anthropic --model glm-5.1 --base-url https://api.modelarts-maas.com/anthropic --seed-start 148 --max-trials 5
```

科研实验不要使用 `haiku` 等客户端别名，必须显式记录实际模型名。第三方兼容服务可能不
支持 Anthropic 的全部参数，因此本项目只发送基础 Messages 请求，并在本地严格校验 JSON
提案。`effortLevel` 属于特定客户端配置，目前不会作为未经验证的 API 参数发送。

合并各实验 CSV 后生成真实结果图（可一次传入多个 CSV）：

```powershell
python scripts/plot_recovery_results.py --input-csv outputs/recovery/none.csv outputs/recovery/random.csv outputs/recovery/rule.csv outputs/recovery/openai.csv outputs/recovery/oracle.csv
```

脚本输出 `recovery_success_rate.png`、`recovery_mean_trials.png` 和
`recovery_curve.png`，不会包含手工填写的数据。

科研评测必须固定 prompt、模型、候选补偿集合、seed 和 rollout 预算，再比较恢复成功率、
成功所需 trial 数及累计环境步数。LLM 组是额外对照组，不能替代确定性基线；Oracle 只用于
估计上界，不能作为 Agent 输入。中英文设计说明见
[reports/day3_recovery_agent_design.md](reports/day3_recovery_agent_design.md)。

首个真实 `glm-5.1` 单 seed 接入实验及其失败分析见
[reports/day3_glm51_pilot.md](reports/day3_glm51_pilot.md)。该结果仅用于验证 Agent 闭环和
提出下一步消融，不作为统计性能结论。

### 主动诊断探测与结构化 Prompt

恢复 Prompt 使用 `push-recovery-v2-causal`：明确世界坐标系、
`state_t + commanded_action_t -> state_t+1`、加性漂移应由反向 correction 抵消、return
仅为辅助证据，并要求检查历史尝试以避免无依据重复。Prompt 不包含注入 bias、
perturbed/executed action 或裁剪真值。

以下命令从完全相同的 seeded reset 分别执行 `+x/-x/+y/-y` 八步短时命令，直接保存
Agent 可见转移与独立 Oracle 审计表：

```powershell
python scripts/run_active_diagnostic_probes.py --seeds 103 107 108 144 148 --bias-axis x --bias-sign positive --bias-magnitude 0.145 --probe-magnitude 0.2 --probe-steps 8
```

无需 API 的 probe-guided 确定性消融使用 Agent 可见的成对位移估计共同漂移，并施加反向
有界修正：

```powershell
python scripts/run_recovery_agent.py --planner probe_rule --active-probes --seeds 103 107 108 144 148 --max-trials 2 --bias-axis x --bias-sign positive --bias-magnitude 0.145 --output-csv outputs/active_probes/probe_rule_stratified_trials.csv --audit-jsonl outputs/active_probes/probe_rule_stratified_audit.jsonl --trajectory-dir outputs/active_probes/stratified_trajectories
```

`--active-probes` 也可与 `--planner anthropic` 或 `--planner openai` 组合，使结构化探测证据
进入 planner payload。探测步数通过 `probe_environment_steps` 单独计费，不能隐藏在 rollout
预算之外。当前五 seed 结果仅是 development study，不是 held-out 性能结论；详见
[reports/active_diagnostic_probe_pilot.md](reports/active_diagnostic_probe_pilot.md)。

真实非 API 消融可通过下列脚本自动汇总和绘图，汇总过程不会手工输入实验数字：

```powershell
python scripts/summarize_recovery_ablation.py --input-csv outputs/active_probes/ablation_none.csv outputs/active_probes/ablation_rule.csv outputs/active_probes/probe_rule_stratified_trials.csv outputs/active_probes/ablation_oracle.csv --output-csv outputs/active_probes/ablation_summary.csv
python scripts/plot_recovery_results.py --input-csv outputs/active_probes/ablation_none.csv outputs/active_probes/ablation_rule.csv outputs/active_probes/probe_rule_stratified_trials.csv outputs/active_probes/ablation_oracle.csv --output-dir outputs/active_probes/figures
```

代表性视频位于 `outputs/active_probes/representative_videos/`，并由同目录
`manifest.csv` 关联 seed、修正、结果、步数和最终距离。

### Phase-aware recovery

`--correction-schedule` 支持 `whole`、`push_only` 和 `phase_aware`。阶段只由当前
observation 的 gripper-object 与 object-goal 距离确定。开发实验使用：

```powershell
python scripts/run_recovery_agent.py --planner probe_rule --active-probes --seeds 103 107 108 144 148 --max-trials 2 --bias-axis x --bias-sign positive --bias-magnitude 0.145 --correction-schedule phase_aware --output-csv outputs/active_probes/phase_aware.csv --audit-jsonl outputs/active_probes/phase_aware_audit.jsonl --trajectory-dir outputs/active_probes/phase_trajectories/phase_aware
```

CSV 额外记录 `correction_schedule`、`approach_steps`、`push_steps` 和
`near_goal_steps`。当前 schedule 是使用 development seeds 选择的，必须冻结后才能进行
held-out 评测。设计、真实结果和同 seed 视频对照见
[reports/phase_aware_recovery_study.md](reports/phase_aware_recovery_study.md)。

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
  零点误差、标定偏差或长期控制漂移。bias 必须是完整 4 维向量；默认 mask 只允许
  修改前三个平移维度，单轴实验只修改 x 或 y，绝不通过标量广播修改 gripper。

动作依次经过 `raw_action`、`perturbed_action`、范围裁剪和 `executed_action`。
轨迹格式已升级，新增这三个字段以及 `was_clipped`。为兼容旧读取代码，原有
`action` 字段继续保留，并与真正送入环境的 `executed_action` 相同。每个 episode
还会统计 `clipped_step_count`、`clipped_step_fraction`、`clipped_element_count` 和
`clipped_element_fraction`；旧的 `clip_count/clip_fraction` 属性仅作读取兼容。

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
