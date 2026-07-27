"""Run a scripted MetaWorld push-v3 rollout and save RGB frames as MP4."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "push_demo.mp4"


def configure_console() -> None:
    """Avoid UnicodeEncodeError on legacy Windows console code pages."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def validate_frame(frame: Any) -> np.ndarray:
    if not isinstance(frame, np.ndarray):
        raise RuntimeError(f"env.render() 未返回 numpy 数组，而是 {type(frame).__name__}")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise RuntimeError(f"期望 HxWx3 RGB 帧，实际 shape={frame.shape}")
    if frame.dtype != np.uint8:
        frame = np.clip(frame, 0, 255).astype(np.uint8)
    return frame


def run_rollout(output: Path, seed: int, max_steps: int, fps: int) -> bool:
    if max_steps <= 0 or fps <= 0:
        raise ValueError("--max-steps 和 --fps 必须是正整数")

    try:
        import gymnasium as gym
        import metaworld  # noqa: F401 - importing registers Gymnasium environments
        from metaworld.policies import SawyerPushV3Policy
    except ImportError as exc:
        raise RuntimeError("依赖未安装；请先运行 pip install -r requirements.txt") from exc

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_name(f".{output.stem}.tmp{output.suffix}")
    env: Any | None = None
    writer: Any | None = None
    success = False
    steps_run = 0

    try:
        env = gym.make(
            "Meta-World/MT1",
            env_name="push-v3",
            render_mode="rgb_array",
            seed=seed,
        )
        observation, _ = env.reset(seed=seed)
        policy = SawyerPushV3Policy()
        writer = imageio.get_writer(
            temporary_output,
            format="FFMPEG",
            mode="I",
            fps=fps,
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=1,
        )
        writer.append_data(validate_frame(env.render()))

        for step in range(1, max_steps + 1):
            action = np.asarray(policy.get_action(observation), dtype=np.float32)
            action = np.clip(action, env.action_space.low, env.action_space.high)
            observation, reward, terminated, truncated, info = env.step(action)
            writer.append_data(validate_frame(env.render()))
            steps_run = step
            success = success or bool(info.get("success", False))

            if terminated or truncated:
                break

        writer.close()
        writer = None
        if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
            raise RuntimeError("视频编码器没有生成有效文件")
        temporary_output.replace(output)
    finally:
        if writer is not None:
            writer.close()
        if env is not None:
            env.close()
        if temporary_output.exists():
            temporary_output.unlink()

    print(f"rollout steps: {steps_run}")
    print(f"success: {success}")
    print(f"video: {output}")
    print(f"video size: {output.stat().st_size} bytes")
    return success


def main() -> int:
    configure_console()
    args = parse_args()
    try:
        success = run_rollout(args.output, args.seed, args.max_steps, args.fps)
    except Exception as exc:
        print(f"[FAIL] push rollout 失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if not success:
        print("[WARN] rollout 已完成并保存视频，但本次未达到 success。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
