"""Evaluate leakage-safe active recovery under simultaneous x/y action bias."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.diagnostic_probes import (  # noqa: E402
    build_agent_probe_context,
    estimate_planar_bias,
    run_symmetric_probes,
)
from src.perturbations import ActionBiasPerturbation  # noqa: E402
from src.planar_recovery import estimate_planar_correction  # noqa: E402
from src.recovery_agent import (  # noqa: E402
    DEFAULT_CORRECTION_MAGNITUDES,
    PhaseGatedCompensatedPolicy,
)
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


METHODS = ("dominant_only", "sequential", "simultaneous", "oracle")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[250, 251, 252, 253, 254])
    parser.add_argument("--bias-x", type=float, default=0.10)
    parser.add_argument("--bias-y", type=float, default=-0.10)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--probe-magnitude", type=float, default=0.2)
    parser.add_argument("--probe-steps", type=int, default=8)
    parser.add_argument(
        "--methods", nargs="+", choices=METHODS, default=list(METHODS)
    )
    parser.add_argument(
        "--correction-schedule",
        choices=("whole", "push_only", "phase_aware"),
        default="whole",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_ROOT / "outputs" / "planar_bias_pilot",
    )
    return parser.parse_args()


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run_trial(
    *, seed: int, bias: tuple[float, float, float, float], correction: np.ndarray,
    max_steps: int, schedule: str,
) -> tuple[Any, dict[str, int]]:
    env = create_push_environment(seed)
    policy = PhaseGatedCompensatedPolicy(
        create_push_policy(), correction, schedule=schedule
    )
    try:
        result = run_episode(
            env, policy, seed=seed, max_steps=max_steps,
            perturbation=ActionBiasPerturbation(bias),
        )
    finally:
        env.close()
    return result, dict(policy.phase_counts)


def result_row(
    *, seed: int, method: str, trial: int, bias: tuple[float, ...],
    correction: Sequence[float], result: Any, probe_steps: int,
    phase_counts: dict[str, int], estimate: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "seed": seed,
        "bias_x": bias[0],
        "bias_y": bias[1],
        "method": method,
        "trial": trial,
        "correction_x": correction[0],
        "correction_y": correction[1],
        "success": result.success,
        "steps": result.steps,
        "episode_return": result.episode_return,
        "final_object_goal_distance": result.final_object_goal_distance,
        "clipped_step_fraction": result.clipped_step_fraction,
        "probe_environment_steps": probe_steps,
        "cumulative_environment_steps": probe_steps + result.steps,
        "approach_steps": phase_counts["approach"],
        "push_steps": phase_counts["push"],
        "near_goal_steps": phase_counts["near_goal"],
        "agent_estimated_bias_x": "" if estimate is None else estimate["estimated_action_bias"][0],
        "agent_estimated_bias_y": "" if estimate is None else estimate["estimated_action_bias"][1],
    }


def summarize(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    initial_failed = {int(row["seed"]) for row in rows if row["method"] == "baseline" and not row["success"]}
    by_method: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["method"] != "baseline" and int(row["seed"]) in initial_failed:
            by_method[str(row["method"])].append(row)
    summaries = []
    for method in METHODS:
        method_rows = by_method.get(method, [])
        final_by_seed: dict[int, dict[str, Any]] = {}
        for row in method_rows:
            final_by_seed[int(row["seed"])] = row
        finals = list(final_by_seed.values())
        recovered = sum(bool(row["success"]) for row in finals)
        summaries.append(
            {
                "method": method,
                "initial_failures": len(initial_failed),
                "evaluated_failures": len(finals),
                "recovered": recovered,
                "conditional_recovery_rate": recovered / len(finals) if finals else 0.0,
                "mean_final_object_goal_distance": mean(float(row["final_object_goal_distance"]) for row in finals) if finals else "",
                "mean_total_environment_steps": mean(float(row["cumulative_environment_steps"]) for row in finals) if finals else "",
            }
        )
    return summaries


def main() -> int:
    args = parse_args()
    if not args.seeds or args.max_steps <= 0 or args.probe_steps <= 0:
        print("[FAIL] seeds and positive step budgets are required", file=sys.stderr)
        return 1
    if np.isclose(args.bias_x, 0.0) or np.isclose(args.bias_y, 0.0):
        print("[FAIL] this experiment requires nonzero x and y bias", file=sys.stderr)
        return 1
    bias = (float(args.bias_x), float(args.bias_y), 0.0, 0.0)
    output_dir = args.output_dir.expanduser().resolve()
    rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    try:
        for seed in args.seeds:
            baseline, counts = run_trial(
                seed=seed, bias=bias, correction=np.zeros(4, dtype=np.float32),
                max_steps=args.max_steps, schedule=args.correction_schedule,
            )
            rows.append(result_row(
                seed=seed, method="baseline", trial=1, bias=bias,
                correction=np.zeros(4), result=baseline, probe_steps=0,
                phase_counts=counts, estimate=None,
            ))
            if baseline.success:
                print(f"seed={seed} initial_success=True; recovery not evaluated")
                continue

            probes = run_symmetric_probes(
                lambda: create_push_environment(seed), seed=seed,
                perturbation_factory=lambda: ActionBiasPerturbation(bias),
                magnitude=args.probe_magnitude, steps=args.probe_steps,
            )
            context = build_agent_probe_context(probes, estimate_planar_bias(probes))
            estimate = estimate_planar_correction(
                context, allowed_magnitudes=DEFAULT_CORRECTION_MAGNITUDES
            )
            estimate_dict = estimate.to_dict()
            probe_environment_steps = int(context["probe_environment_steps"])
            audits.append({
                "seed": seed,
                "injected_bias": bias,
                "agent_inference": context["inference"],
                "agent_planar_correction": estimate_dict,
            })
            dominant = np.asarray(estimate.dominant_axis_correction, dtype=np.float32)
            simultaneous = np.asarray(estimate.simultaneous_correction, dtype=np.float32)
            oracle = -np.asarray(bias, dtype=np.float32)

            for method in args.methods:
                corrections = {
                    "dominant_only": (dominant,),
                    "sequential": (dominant, simultaneous),
                    "simultaneous": (simultaneous,),
                    "oracle": (oracle,),
                }[method]
                cumulative_steps = probe_environment_steps
                for trial_index, correction in enumerate(corrections, start=2):
                    result, counts = run_trial(
                        seed=seed, bias=bias, correction=correction,
                        max_steps=args.max_steps, schedule=args.correction_schedule,
                    )
                    cumulative_steps += result.steps
                    row = result_row(
                        seed=seed, method=method, trial=trial_index, bias=bias,
                        correction=correction, result=result,
                        probe_steps=probe_environment_steps, phase_counts=counts,
                        estimate=estimate_dict,
                    )
                    row["cumulative_environment_steps"] = cumulative_steps
                    rows.append(row)
                    if result.success:
                        break
            print(
                f"seed={seed} initial_success=False estimate="
                f"({estimate.estimated_action_bias[0]:+.3f},"
                f"{estimate.estimated_action_bias[1]:+.3f})"
            )

        write_csv(output_dir / "trials.csv", rows)
        write_csv(output_dir / "summary.csv", summarize(rows))
        audit_path = output_dir / "oracle_audit.jsonl"
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in audits),
            encoding="utf-8",
        )
        print(f"trials: {output_dir / 'trials.csv'}")
        print(f"summary: {output_dir / 'summary.csv'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
