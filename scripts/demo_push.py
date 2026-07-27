"""Run a scripted MetaWorld push-v3 rollout and save video plus trajectory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rollout import (  # noqa: E402
    create_push_environment,
    create_push_policy,
    run_episode,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "outputs" / "push_demo.mp4"
DEFAULT_TRAJECTORY_OUTPUT = PROJECT_ROOT / "outputs" / "push_demo.jsonl"


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--trajectory-output", type=Path, default=DEFAULT_TRAJECTORY_OUTPUT
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def run_rollout(
    output: Path,
    seed: int,
    max_steps: int,
    fps: int,
    trajectory_output: Path = DEFAULT_TRAJECTORY_OUTPUT,
) -> bool:
    """Preserve the original full-length video rollout behavior."""

    env: Any | None = None
    try:
        env = create_push_environment(seed, render_mode="rgb_array")
        result = run_episode(
            env,
            create_push_policy(),
            episode_id=1,
            seed=seed,
            max_steps=max_steps,
            trajectory_path=trajectory_output,
            video_path=output,
            fps=fps,
            stop_on_success=False,
        )
    finally:
        if env is not None:
            env.close()

    resolved_output = output.expanduser().resolve()
    print(f"rollout steps: {result.steps}")
    print(f"return: {result.episode_return:.6f}")
    print(f"elapsed time: {result.elapsed_time_ms:.2f} ms")
    print(f"success: {result.success}")
    print(f"video: {resolved_output}")
    print(f"video size: {resolved_output.stat().st_size} bytes")
    print(f"trajectory: {trajectory_output.expanduser().resolve()}")
    return result.success


def main() -> int:
    configure_console()
    args = parse_args()
    try:
        success = run_rollout(
            args.output,
            args.seed,
            args.max_steps,
            args.fps,
            args.trajectory_output,
        )
    except Exception as exc:
        print(f"[FAIL] push rollout failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if not success:
        print(
            "[WARN] rollout and files completed, but success was not reached.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
