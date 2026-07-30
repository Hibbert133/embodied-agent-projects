"""Collect passive push-v3 rollouts for an ambiguity-benchmark split.

This script executes only the initial rollout for each registered fault condition.
It records Oracle fault metadata for evaluator-side benchmark construction, while
all matching features come from outcomes that are available after the rollout.
No diagnostic probes, corrective interventions, API calls, or video rendering are
performed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import (  # noqa: E402
    get_conditions,
    rollout,
    save_csv,
    save_jsonl,
)


def compare_reference_baselines(
    collected: Sequence[Mapping[str, Any]],
    reference: Sequence[Mapping[str, Any]],
    *,
    absolute_tolerance: float = 1e-12,
) -> None:
    """Fail closed unless execution outcomes reproduce an existing baseline."""
    by_key = {
        (str(row["condition_id"]), int(row["seed"])): row for row in collected
    }
    reference_by_key = {
        (str(row["condition_id"]), int(row["seed"])): row for row in reference
    }
    if set(by_key) != set(reference_by_key):
        missing = sorted(set(reference_by_key) - set(by_key))
        extra = sorted(set(by_key) - set(reference_by_key))
        raise ValueError(f"baseline key mismatch; missing={missing}, extra={extra}")
    for key in sorted(by_key):
        actual = by_key[key]
        expected = reference_by_key[key]
        if bool(actual["success"]) != _parse_bool(expected["success"]):
            raise ValueError(f"success regression for {key}")
        if int(actual["steps"]) != int(expected["steps"]):
            raise ValueError(f"step regression for {key}")
        if not math.isclose(
            float(actual["final_object_goal_distance"]),
            float(expected["final_object_goal_distance"]),
            rel_tol=0.0,
            abs_tol=absolute_tolerance,
        ):
            raise ValueError(f"final-distance regression for {key}")


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise ValueError(f"invalid boolean: {value!r}")


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def collect_rollouts(
    *,
    seed_start: int,
    num_seeds: int,
    max_steps: int,
    noise_std: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    oracle_rows: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, Any]] = []
    number = 0
    for fault in get_conditions(noise_std):
        for seed in range(seed_start, seed_start + num_seeds):
            number += 1
            result = rollout(seed, fault, (0, 0, 0, 0), "whole", max_steps)
            baseline = {
                "success": result.success,
                "steps": result.steps,
                "episode_return": result.episode_return,
                "final_object_goal_distance": result.final_object_goal_distance,
                "progress_to_goal": result.progress_to_goal,
            }
            oracle_rows.append(
                {
                    "case_id": f"heldout_case_{number:04d}",
                    "seed": seed,
                    "condition_id": fault.condition_id,
                    "perturbation_type": fault.kind,
                    "perturbation_parameters": fault.parameters,
                    "baseline": baseline,
                }
            )
            baseline_rows.append(
                {"condition_id": fault.condition_id, "seed": seed, **baseline}
            )
            print(
                f"condition={fault.condition_id} seed={seed} "
                f"success={result.success} steps={result.steps}"
            )
    return oracle_rows, baseline_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-start", type=int, default=310)
    parser.add_argument("--num-seeds", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument(
        "--noise-selection",
        type=Path,
        default=ROOT / "outputs/autoresearch/noise_calibration/selected.json",
    )
    parser.add_argument(
        "--reference-baselines",
        type=Path,
        default=ROOT / "outputs/autoresearch/gated_recovery_validation/baselines.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/heldout_rollouts",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if min(args.num_seeds, args.max_steps) <= 0:
            raise ValueError("num-seeds and max-steps must be positive")
        noise_std = float(
            json.loads(args.noise_selection.read_text(encoding="utf-8"))["noise_std"]
        )
        oracle_rows, baseline_rows = collect_rollouts(
            seed_start=args.seed_start,
            num_seeds=args.num_seeds,
            max_steps=args.max_steps,
            noise_std=noise_std,
        )
        reference = _load_csv(args.reference_baselines)
        compare_reference_baselines(baseline_rows, reference)
        output_dir = args.output_dir.resolve()
        save_jsonl(output_dir / "oracle_audit.jsonl", oracle_rows)
        save_csv(output_dir / "baselines.csv", baseline_rows)
        metadata = {
            "split": "heldout",
            "seed_start": args.seed_start,
            "num_seeds": args.num_seeds,
            "max_steps": args.max_steps,
            "noise_std": noise_std,
            "rendering": False,
            "diagnostic_probes": False,
            "reference_regression_check": _display_path(args.reference_baselines),
            "reference_rows_matched": len(reference),
        }
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        print(f"reference regression: matched {len(reference)}/{len(reference)} rows")
        print(f"oracle audit: {output_dir / 'oracle_audit.jsonl'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
