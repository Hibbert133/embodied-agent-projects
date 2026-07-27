"""Verify the Python/dependency setup and perform a MetaWorld render smoke test."""

from __future__ import annotations

import importlib.metadata
import platform
import sys
from typing import Any


REQUIRED_PACKAGES = (
    "metaworld",
    "mujoco",
    "imageio",
    "imageio-ffmpeg",
    "packaging",
)


def configure_console() -> None:
    """Avoid UnicodeEncodeError on legacy Windows console code pages."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def fail(message: str, exc: BaseException | None = None) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    if exc is not None:
        print(f"       {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1


def main() -> int:
    configure_console()
    if sys.version_info[:2] != (3, 10):
        return fail(
            "需要 Python 3.10；当前是 "
            f"{platform.python_version()} ({sys.executable})"
        )

    print(f"[OK] Python {platform.python_version()}: {sys.executable}")
    for package in REQUIRED_PACKAGES:
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            return fail(f"缺少依赖 {package}，请安装 requirements.txt", exc)
        print(f"[OK] {package} {version}")

    env: Any | None = None
    try:
        import gymnasium as gym
        import metaworld  # noqa: F401 - importing registers Gymnasium environments

        env = gym.make(
            "Meta-World/MT1",
            env_name="push-v3",
            render_mode="rgb_array",
            seed=42,
        )
        observation, info = env.reset(seed=42)
        frame = env.render()

        if observation.ndim != 1:
            raise RuntimeError(f"观测应为一维向量，实际 shape={observation.shape}")
        if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
            shape = None if frame is None else frame.shape
            raise RuntimeError(f"渲染结果不是 RGB 图像，实际 shape={shape}")

        action = env.action_space.sample() * 0.0
        step_result = env.step(action)
        if len(step_result) != 5:
            raise RuntimeError(f"env.step 应返回 5 项，实际返回 {len(step_result)} 项")

        print(f"[OK] push-v3 observation shape: {observation.shape}")
        print(f"[OK] action space: {env.action_space}")
        print(f"[OK] rgb_array frame shape: {frame.shape}, dtype={frame.dtype}")
        print("[PASS] MetaWorld + MuJoCo 安装与渲染检查通过")
        return 0
    except Exception as exc:
        return fail("MetaWorld/MuJoCo 冒烟测试失败", exc)
    finally:
        if env is not None:
            env.close()


if __name__ == "__main__":
    raise SystemExit(main())
