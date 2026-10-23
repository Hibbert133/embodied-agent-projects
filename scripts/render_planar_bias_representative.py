"""Render the first held-out case where 2-D repair beats dominant-axis repair."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.perturbations import ActionBiasPerturbation  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials-csv", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_ROOT / "outputs" / "planar_bias_pilot" / "videos",
    )
    return parser.parse_args()


def as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def main() -> int:
    args = parse_args()
    with args.trials_csv.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    by_seed: dict[int, dict[str, dict[str, str]]] = {}
    for row in rows:
        seed = int(row["seed"])
        # Last row is the final outcome for sequential; other methods have one row.
        by_seed.setdefault(seed, {})[row["method"]] = row
    candidates = sorted(
        seed for seed, methods in by_seed.items()
        if "dominant_only" in methods and "simultaneous" in methods
        and not as_bool(methods["dominant_only"]["success"])
        and as_bool(methods["simultaneous"]["success"])
    )
    if not candidates:
        raise ValueError("no dominant-failure/simultaneous-success case found")
    seed = candidates[0]
    selected = by_seed[seed]
    bias = (
        float(selected["baseline"]["bias_x"]),
        float(selected["baseline"]["bias_y"]), 0.0, 0.0,
    )
    configurations = {
        "baseline_failure": np.zeros(4, dtype=np.float32),
        "dominant_only_failure": np.array([
            float(selected["dominant_only"]["correction_x"]),
            float(selected["dominant_only"]["correction_y"]), 0.0, 0.0,
        ], dtype=np.float32),
        "simultaneous_success": np.array([
            float(selected["simultaneous"]["correction_x"]),
            float(selected["simultaneous"]["correction_y"]), 0.0, 0.0,
        ], dtype=np.float32),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for label, correction in configurations.items():
        video = args.output_dir / f"2d_bias_xp014_yn014_seed{seed}_{label}.mp4"
        trajectory = args.output_dir / f"2d_bias_xp014_yn014_seed{seed}_{label}.jsonl"
        env = create_push_environment(seed, render_mode="rgb_array")
        policy = PhaseGatedCompensatedPolicy(create_push_policy(), correction, schedule="whole")
        try:
            result = run_episode(
                env, policy, seed=seed, max_steps=args.max_steps,
                trajectory_path=trajectory, video_path=video, fps=args.fps,
                perturbation=ActionBiasPerturbation(bias),
            )
        finally:
            env.close()
        expected = label.endswith("success")
        if result.success != expected:
            raise RuntimeError(f"rendered {label} outcome changed for seed {seed}")
        manifest.append({
            "seed": seed, "case": label, "bias_x": bias[0], "bias_y": bias[1],
            "correction_x": float(correction[0]), "correction_y": float(correction[1]),
            "success": result.success, "steps": result.steps,
            "final_object_goal_distance": result.final_object_goal_distance,
            "video_path": str(video.resolve()), "trajectory_path": str(trajectory.resolve()),
        })
    manifest_path = args.output_dir / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    print(f"selected seed: {seed}")
    print(f"manifest: {manifest_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
