"""Summarize real recovery trial CSVs without hand-entered experiment values."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, nargs="+", required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser.parse_args()


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.expanduser().resolve().open(encoding="utf-8", newline="") as file:
            rows.extend(csv.DictReader(file))
    if not rows:
        raise ValueError("input CSV files contain no rows")
    return rows


def summarize(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    episodes: dict[tuple[str, int], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        schedule = row.get("correction_schedule", "")
        method = f"{row['planner']}:{schedule}" if schedule else row["planner"]
        episodes[(method, int(row["seed"]))].append(row)
    by_planner: dict[str, list[dict[str, object]]] = defaultdict(list)
    for (planner, seed), trials in episodes.items():
        ordered = sorted(trials, key=lambda item: int(item["trial"]))
        final = ordered[-1]
        rollout_steps = sum(int(item["steps"]) for item in ordered)
        probe_steps = max(int(item.get("probe_environment_steps", 0) or 0) for item in ordered)
        by_planner[planner].append(
            {
                "seed": seed,
                "success": any(item["success"].lower() == "true" for item in ordered),
                "trials": len(ordered),
                "final_distance": float(final["final_object_goal_distance"]),
                "rollout_steps": rollout_steps,
                "probe_steps": probe_steps,
                "total_steps": rollout_steps + probe_steps,
                "approach_steps": int(final.get("approach_steps", 0) or 0),
                "push_steps": int(final.get("push_steps", 0) or 0),
                "near_goal_steps": int(final.get("near_goal_steps", 0) or 0),
            }
        )
    summaries: list[dict[str, object]] = []
    for planner, items in sorted(by_planner.items()):
        successes = sum(bool(item["success"]) for item in items)
        summaries.append(
            {
                "planner": planner,
                "num_episodes": len(items),
                "successes": successes,
                "success_rate": successes / len(items),
                "mean_trials": mean(float(item["trials"]) for item in items),
                "mean_final_object_goal_distance": mean(float(item["final_distance"]) for item in items),
                "mean_rollout_steps": mean(float(item["rollout_steps"]) for item in items),
                "mean_probe_steps": mean(float(item["probe_steps"]) for item in items),
                "mean_total_environment_steps": mean(float(item["total_steps"]) for item in items),
                "mean_final_trial_approach_steps": mean(float(item["approach_steps"]) for item in items),
                "mean_final_trial_push_steps": mean(float(item["push_steps"]) for item in items),
                "mean_final_trial_near_goal_steps": mean(float(item["near_goal_steps"]) for item in items),
            }
        )
    return summaries


def main() -> int:
    args = parse_args()
    summaries = summarize(read_rows(args.input_csv))
    output = args.output_csv.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    for row in summaries:
        print(
            f"{row['planner']}: {row['successes']}/{row['num_episodes']} "
            f"success={float(row['success_rate']):.1%} "
            f"final_distance={float(row['mean_final_object_goal_distance']):.6f}m "
            f"total_steps={float(row['mean_total_environment_steps']):.1f}"
        )
    print(f"summary: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
