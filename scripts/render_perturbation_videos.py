"""Render reproducible MetaWorld push-v3 perturbation comparison videos."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.perturbations import (  # noqa: E402
    ActionBiasPerturbation,
    ActionPerturbation,
    ActionScalePerturbation,
    GaussianNoisePerturbation,
    IdentityPerturbation,
)
from src.rollout import (  # noqa: E402
    create_push_environment,
    create_push_policy,
    run_episode,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "perturbation_videos"


@dataclass(frozen=True)
class VideoCase:
    name: str
    perturbation_type: str
    perturbation_level: float
    seed: int
    factory: Callable[[], ActionPerturbation]


CASES = (
    VideoCase("baseline_seed100", "identity", 0.0, 100, IdentityPerturbation),
    VideoCase(
        "action_scale_0.6_failure_seed103",
        "action_scale",
        0.6,
        103,
        lambda: ActionScalePerturbation(0.6),
    ),
    VideoCase(
        "noise_0.2_failure_seed103",
        "gaussian_noise",
        0.2,
        103,
        lambda: GaussianNoisePerturbation(0.2),
    ),
    VideoCase(
        "bias_0.08_success_seed102",
        "action_bias",
        0.08,
        102,
        lambda: ActionBiasPerturbation(0.08),
    ),
    VideoCase(
        "bias_0.08_failure_seed100",
        "action_bias",
        0.08,
        100,
        lambda: ActionBiasPerturbation(0.08),
    ),
    VideoCase(
        "bias_0.10_failure_seed100",
        "action_bias",
        0.10,
        100,
        lambda: ActionBiasPerturbation(0.10),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def render_videos(output_dir: Path, max_steps: int, fps: int) -> Path:
    if max_steps <= 0 or fps <= 0:
        raise ValueError("--max-steps and --fps must be positive integers")
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, object]] = []
    policy = create_push_policy()

    for episode_id, case in enumerate(CASES, start=1):
        video_path = output_dir / f"{case.name}.mp4"
        trajectory_path = output_dir / f"{case.name}.jsonl"
        env = None
        try:
            env = create_push_environment(case.seed, render_mode="rgb_array")
            result = run_episode(
                env,
                policy,
                episode_id=episode_id,
                seed=case.seed,
                max_steps=max_steps,
                trajectory_path=trajectory_path,
                video_path=video_path,
                fps=fps,
                perturbation=case.factory(),
            )
        finally:
            if env is not None:
                env.close()

        manifest_rows.append(
            {
                "name": case.name,
                "perturbation_type": case.perturbation_type,
                "perturbation_level": case.perturbation_level,
                "seed": case.seed,
                "success": result.success,
                "steps": result.steps,
                "episode_return": result.episode_return,
                "clip_count": result.clip_count,
                "clip_fraction": result.clip_fraction,
                "video_path": video_path.name,
                "trajectory_path": trajectory_path.name,
            }
        )
        print(
            f"{case.name}: success={result.success}, steps={result.steps}, "
            f"video={video_path}"
        )

    manifest_path = output_dir / "manifest.csv"
    temporary_path = output_dir / ".manifest.csv.tmp"
    try:
        with temporary_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(manifest_rows[0]))
            writer.writeheader()
            writer.writerows(manifest_rows)
        temporary_path.replace(manifest_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    print(f"manifest: {manifest_path}")
    return manifest_path


def main() -> int:
    args = parse_args()
    try:
        render_videos(args.output_dir, args.max_steps, args.fps)
    except Exception as exc:
        print(f"[FAIL] video rendering failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
