# 安装说明

本项目使用 Python 3.10、CPU 和 MuJoCo。无需 CUDA，也无需单独安装 FFmpeg；
`imageio-ffmpeg` 会提供保存 MP4 所需的可执行文件。

## Windows PowerShell

确认已安装 64 位 Python 3.10，然后在项目根目录运行：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/check_install.py
python scripts/demo_push.py
```

如果 PowerShell 阻止激活脚本，可以不激活环境，直接运行：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\check_install.py
.\.venv\Scripts\python.exe scripts\demo_push.py
```

## Linux / macOS

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/check_install.py
python scripts/demo_push.py
```

MetaWorld 官方支持并测试 Linux/macOS；Windows 可用但不是官方支持平台。本项目中的
固定版本已在当前 Windows 环境实际验证。

### Windows 仅有基础显示驱动时

MuJoCo 的物理仿真使用 CPU，但 `rgb_array` 渲染仍需要 OpenGL。若安装检查报告
`WGL: The driver does not appear to support OpenGL`，应优先安装机器厂商提供的显卡
驱动。对于没有 GPU 的 Windows Server/虚拟机，可使用 Mesa 的 CPU 软件 OpenGL：

1. 从 [mesa-dist-win 26.0.3](https://github.com/pal1000/mesa-dist-win/releases/tag/26.0.3)
   下载 `mesa3d-26.0.3-release-msvc.7z` 并解压。
2. 用管理员 PowerShell 进入解压目录。
3. 运行 `.\systemwidedeploy.cmd 1`；选项 `1` 安装核心桌面 OpenGL 驱动。
4. 重新运行 `python scripts/check_install.py`。

这套 Mesa 回退方案完全使用 CPU，不需要 CUDA。它会注册系统级 OpenGL 驱动，因此
只应在确实没有可用厂商 OpenGL 驱动时使用。
