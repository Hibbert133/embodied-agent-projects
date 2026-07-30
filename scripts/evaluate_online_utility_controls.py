"""Evaluate deterministic controls for a completed online utility-Agent run."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import (  # noqa: E402
    FaultCondition,
    rollout,
    save_csv,
)
from src.stochastic_recovery import derive_retry_seed  # noqa: E402
from src.utility_controls import choose_oracle_candidate, choose_probe_greedy  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=ROOT / "outputs/autoresearch/benchmark_tuning",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parse_args()
    try:
        run_dir = args.run_dir.resolve()
        prepared = {row["case_id"]: row for row in load_jsonl(run_dir / "prepared_cases.jsonl")}
        online = {row["case_id"]: row for row in load_csv(run_dir / "results.csv")}
        oracle = {
            row["case_id"]: row
            for row in load_jsonl(args.benchmark_dir / "oracle_audit.jsonl")
        }
        if set(prepared) != set(online):
            raise ValueError("prepared and online case sets differ")

        rows: list[dict[str, Any]] = []
        for case_id, evidence in prepared.items():
            hidden = oracle[case_id]
            seed = int(evidence["seed"])
            fault = FaultCondition(
                hidden["condition_id"],
                hidden["perturbation_type"],
                hidden["perturbation_parameters"],
            )
            candidates = {item["candidate_id"]: item for item in evidence["candidates"]}
            compensation = candidates["bias_compensation"]
            execution_seed = derive_retry_seed(seed, 201)
            compensation_result = rollout(
                seed,
                fault,
                tuple(compensation["correction"]),
                str(compensation["schedule"]),
                int(compensation["max_full_rollout_steps"]),
                perturbation_seed=execution_seed,
            )
            retry_result = rollout(
                seed,
                fault,
                (0.0, 0.0, 0.0, 0.0),
                "whole",
                int(candidates["stochastic_retry"]["max_full_rollout_steps"]),
                perturbation_seed=execution_seed,
            )
            outcomes = {
                "bias_compensation": compensation_result,
                "stochastic_retry": retry_result,
            }
            outcome_views = [
                {
                    "candidate_id": candidate_id,
                    "success": result.success,
                    "steps": result.steps,
                    "final_object_goal_distance": result.final_object_goal_distance,
                }
                for candidate_id, result in outcomes.items()
            ]
            selections = {
                "always_compensation": "bias_compensation",
                "always_retry": "stochastic_retry",
                "probe_greedy": choose_probe_greedy(
                    evidence["candidate_probe_evidence"]
                ),
                "online_agent": str(online[case_id]["candidate_id"]),
                "oracle_candidate": choose_oracle_candidate(outcome_views),
            }
            active_steps = int(evidence["active_probe_steps"])
            candidate_steps = int(evidence["candidate_probe_steps"])
            overhead = {
                "always_compensation": active_steps,
                "always_retry": 0,
                "probe_greedy": active_steps + candidate_steps,
                "online_agent": active_steps + candidate_steps,
                "oracle_candidate": active_steps + candidate_steps,
            }
            for method, candidate_id in selections.items():
                result = outcomes[candidate_id]
                rows.append(
                    {
                        "case_id": case_id,
                        "seed": seed,
                        "condition_id": hidden["condition_id"],
                        "method": method,
                        "candidate_id": candidate_id,
                        "recovery_success": result.success,
                        "evidence_environment_steps": overhead[method],
                        "final_rollout_steps": result.steps,
                        "total_recovery_environment_steps": overhead[method]
                        + result.steps,
                        "final_object_goal_distance": result.final_object_goal_distance,
                    }
                )
            recorded = online[case_id]
            selected_result = outcomes[str(recorded["candidate_id"])]
            if (
                str(recorded["recovery_success"]).lower()
                != str(selected_result.success).lower()
                or int(recorded["final_rollout_steps"]) != selected_result.steps
                or abs(
                    float(recorded["final_object_goal_distance"])
                    - selected_result.final_object_goal_distance
                )
                > 1e-10
            ):
                raise RuntimeError(f"{case_id}: online result is not reproducible")
            print(
                f"case={case_id} online={selections['online_agent']} "
                f"greedy={selections['probe_greedy']} "
                f"oracle={selections['oracle_candidate']}"
            )

        save_csv(run_dir / "control_results.csv", rows)
        summary: list[dict[str, Any]] = []
        methods = list(dict.fromkeys(row["method"] for row in rows))
        for method in methods:
            selected = [row for row in rows if row["method"] == method]
            recovered = sum(bool(row["recovery_success"]) for row in selected)
            summary.append(
                {
                    "method": method,
                    "cases": len(selected),
                    "recovered": recovered,
                    "conditional_recovery_rate": recovered / len(selected),
                    "mean_total_recovery_environment_steps": mean(
                        float(row["total_recovery_environment_steps"])
                        for row in selected
                    ),
                    "mean_final_object_goal_distance": mean(
                        float(row["final_object_goal_distance"])
                        for row in selected
                    ),
                }
            )
        save_csv(run_dir / "control_summary.csv", summary)
        agreement = sum(
            online[case_id]["candidate_id"]
            == choose_probe_greedy(prepared[case_id]["candidate_probe_evidence"])
            for case_id in prepared
        )
        print(f"online/greedy agreement: {agreement}/{len(prepared)}")
        print(f"summary: {(run_dir / 'control_summary.csv').resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
