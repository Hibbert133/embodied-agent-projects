"""Calibrate a reproducible Gaussian-noise OOD condition for autoresearch."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.autoresearch import select_noise_calibration  # noqa: E402
from src.perturbations import GaussianNoisePerturbation  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(300, 310)))
    parser.add_argument("--levels", type=float, nargs="+", default=[0.25, 0.30, 0.35, 0.40])
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_ROOT / "outputs" / "autoresearch" / "noise_calibration",
    )
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write empty calibration CSV")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    if not args.seeds or not args.levels or args.max_steps <= 0:
        print("[FAIL] seeds, levels, and positive max steps are required", file=sys.stderr)
        return 1
    detailed: list[dict[str, Any]] = []
    try:
        for level in args.levels:
            if level < 0:
                raise ValueError("noise levels must be non-negative")
            for seed in args.seeds:
                env = create_push_environment(seed)
                try:
                    result = run_episode(
                        env, create_push_policy(), seed=seed, max_steps=args.max_steps,
                        perturbation=GaussianNoisePerturbation(level),
                    )
                finally:
                    env.close()
                detailed.append({
                    "noise_std": level, "seed": seed, "success": result.success,
                    "steps": result.steps,
                    "final_object_goal_distance": result.final_object_goal_distance,
                    "clipped_step_fraction": result.clipped_step_fraction,
                    "clipped_element_fraction": result.clipped_element_fraction,
                })
            print(f"noise_std={level:.3f} completed={len(args.seeds)}")
        grouped: dict[float, list[dict[str, Any]]] = defaultdict(list)
        for row in detailed:
            grouped[float(row["noise_std"])].append(row)
        summary = []
        for level in sorted(grouped):
            rows = grouped[level]
            successes = sum(bool(row["success"]) for row in rows)
            summary.append({
                "noise_std": level, "episodes": len(rows), "successes": successes,
                "success_rate": successes / len(rows),
                "failure_rate": 1.0 - successes / len(rows),
                "mean_steps": mean(float(row["steps"]) for row in rows),
                "mean_final_object_goal_distance": mean(
                    float(row["final_object_goal_distance"]) for row in rows
                ),
                "clipped_step_fraction": mean(
                    float(row["clipped_step_fraction"]) for row in rows
                ),
                "clipped_element_fraction": mean(
                    float(row["clipped_element_fraction"]) for row in rows
                ),
            })
        selected = dict(select_noise_calibration(summary))
        selected["selection_rule"] = "closest_failure_rate_to_0.5_then_lower_std"
        selected["primary_eligible"] = float(selected["clipped_step_fraction"]) <= 0.5
        output = args.output_dir.expanduser().resolve()
        write_csv(output / "episodes.csv", detailed)
        write_csv(output / "summary.csv", summary)
        (output / "selected.json").write_text(
            json.dumps(selected, indent=2) + "\n", encoding="utf-8"
        )
        print(f"selected_noise_std={selected['noise_std']}")
        print(f"summary: {output / 'summary.csv'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
