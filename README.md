# MetaWorld Push 可视化入门

这是一个不训练强化学习模型的最小具身智能示例：在 MetaWorld 的 `push-v3`
任务中运行内置脚本策略，用 MuJoCo 的 `render_mode="rgb_array"` 获取 RGB 帧，
并保存为 `outputs/push_demo.mp4`。

## 项目结构

```text
.
├── INSTALL.md
├── README.md
├── requirements.txt
├── outputs/
│   └── push_demo.mp4       # 运行后生成
└── scripts/
    ├── check_install.py    # 版本、环境创建、渲染冒烟测试
    └── demo_push.py        # push rollout 与视频保存
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

这两个脚本都应从项目根目录运行。它们不要求 GPU/CUDA，也不会训练或下载策略权重。

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
