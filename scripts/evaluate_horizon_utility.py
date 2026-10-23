"""Measure candidate-selection accuracy and cost across evidence horizons."""

from __future__ import annotations

import argparse
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
    save_csv,
)
from src.horizon_utility import build_prefix_evidence  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import (  # noqa: E402
    create_push_environment,
    create_push_policy,
    run_episode,
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
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=[20, 40, 80, 120, 160, 240, 320, 400, 500],
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_candidate(
    *,
    seed: int,
    fault: FaultCondition,
    correction: tuple[float, ...],
    schedule: str,
    max_steps: int,
    perturbation_seed: int,
    agent_trajectory_path: Path,
) -> Any:
    environment = create_push_environment(seed)
    policy = PhaseGatedCompensatedPolicy(
        create_push_policy(), correction, schedule=schedule
    )
    try:
        return run_episode(
            environment,
            policy,
            seed=seed,
            max_steps=max_steps,
            perturbation=fault.build(),
            perturbation_seed=perturbation_seed,
            agent_trajectory_path=agent_trajectory_path,
        )
    finally:
        environment.close()


def main() -> int:
    args = parse_args()
    try:
        horizons = sorted(set(args.horizons))
        if not horizons or horizons[0] <= 0:
            raise ValueError("horizons must be positive")
        run_dir = args.run_dir.resolve()
        prepared = load_jsonl(run_dir / "prepared_cases.jsonl")
        oracle_cases = {
            row["case_id"]: row
            for row in load_jsonl(args.benchmark_dir / "oracle_audit.jsonl")
        }
        trajectory_dir = run_dir / "horizon_agent_trajectories"
        probe_traces: dict[tuple[str, str], list[dict[str, Any]]] = {}
        full_outcomes: dict[tuple[str, str], dict[str, Any]] = {}

        for case in prepared:
            case_id = str(case["case_id"])
            seed = int(case["seed"])
            hidden = oracle_cases[case_id]
            fault = FaultCondition(
                hidden["condition_id"],
                hidden["perturbation_type"],
                hidden["perturbation_parameters"],
            )
            for candidate in case["candidates"]:
                candidate_id = str(candidate["candidate_id"])
                final_result = run_candidate(
                    seed=seed,
                    fault=fault,
                    correction=tuple(candidate["correction"]),
                    schedule=str(candidate["schedule"]),
                    max_steps=int(candidate["max_full_rollout_steps"]),
                    perturbation_seed=derive_retry_seed(seed, 201),
                    agent_trajectory_path=(
                        trajectory_dir / f"{case_id}_{candidate_id}_final.jsonl"
                    ),
                )
                # Common random numbers isolate candidate action effects: both
                # candidates see the same probe noise sequence, which remains
                # independent from the final execution stream above.
                probe_path = trajectory_dir / f"{case_id}_{candidate_id}_probe.jsonl"
                run_candidate(
                    seed=seed,
                    fault=fault,
                    correction=tuple(candidate["correction"]),
                    schedule=str(candidate["schedule"]),
                    max_steps=int(candidate["max_full_rollout_steps"]),
                    perturbation_seed=derive_retry_seed(seed, 301),
                    agent_trajectory_path=probe_path,
                )
                probe_traces[(case_id, candidate_id)] = load_jsonl(probe_path)
                full_outcomes[(case_id, candidate_id)] = {
                    "candidate_id": candidate_id,
                    "success": final_result.success,
                    "steps": final_result.steps,
                    "final_object_goal_distance": final_result.final_object_goal_distance,
                }
                print(
                    f"case={case_id} candidate={candidate_id} "
                    f"final_success={final_result.success} final_steps={final_result.steps}"
                )

        rows: list[dict[str, Any]] = []
        for case in prepared:
            case_id = str(case["case_id"])
            candidate_ids = [str(item["candidate_id"]) for item in case["candidates"]]
            outcomes = [full_outcomes[(case_id, item)] for item in candidate_ids]
            oracle_candidate = choose_oracle_candidate(outcomes)
            for horizon in horizons:
                evidence = [
                    build_prefix_evidence(
                        probe_traces[(case_id, candidate_id)],
                        candidate_id=candidate_id,
                        horizon=horizon,
                    )
                    for candidate_id in candidate_ids
                ]
                selected = choose_probe_greedy(evidence)
                selected_outcome = full_outcomes[(case_id, selected)]
                probe_steps = sum(item["observed_steps"] for item in evidence)
                rows.append(
                    {
                        "case_id": case_id,
                        "seed": case["seed"],
                        "horizon": horizon,
                        "selected_candidate": selected,
                        "oracle_candidate": oracle_candidate,
                        "oracle_agreement": selected == oracle_candidate,
                        "selected_full_success": selected_outcome["success"],
                        "candidate_probe_environment_steps": probe_steps,
                        "total_recovery_environment_steps": (
                            int(case["active_probe_steps"])
                            + probe_steps
                            + int(selected_outcome["steps"])
                        ),
                        "selected_final_object_goal_distance": selected_outcome[
                            "final_object_goal_distance"
                        ],
                        "selected_probe_distance": next(
                            item["final_object_goal_distance"]
                            for item in evidence
                            if item["candidate_id"] == selected
                        ),
                        "selected_recent_progress_slope": next(
                            item["recent_20_step_progress_slope"]
                            for item in evidence
                            if item["candidate_id"] == selected
                        ),
                        "probe_stream": "common_derived_salt_301",
                        "final_stream": "independent_derived_salt_201",
                    }
                )

        save_csv(run_dir / "horizon_results.csv", rows)
        summary: list[dict[str, Any]] = []
        for horizon in horizons:
            selected = [row for row in rows if row["horizon"] == horizon]
            summary.append(
                {
                    "horizon": horizon,
                    "cases": len(selected),
                    "oracle_agreement_rate": sum(
                        bool(row["oracle_agreement"]) for row in selected
                    )
                    / len(selected),
                    "conditional_recovery_rate": sum(
                        bool(row["selected_full_success"]) for row in selected
                    )
                    / len(selected),
                    "mean_candidate_probe_environment_steps": mean(
                        float(row["candidate_probe_environment_steps"])
                        for row in selected
                    ),
                    "mean_total_recovery_environment_steps": mean(
                        float(row["total_recovery_environment_steps"])
                        for row in selected
                    ),
                    "mean_final_object_goal_distance": mean(
                        float(row["selected_final_object_goal_distance"])
                        for row in selected
                    ),
                }
            )
        save_csv(run_dir / "horizon_summary.csv", summary)
        print(f"summary: {(run_dir / 'horizon_summary.csv').resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
