"""Analyze repeated paired outcomes without fitting an intervention selector."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


COMPENSATION = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _winner(
    left: Mapping[str, float], right: Mapping[str, float], *, tolerance: float = 1e-12
) -> str:
    for key, prefer_high in (("status_utility", True), ("progress", True), ("steps", False)):
        difference = float(left[key]) - float(right[key])
        if abs(difference) > tolerance:
            return COMPENSATION if (difference > 0) == prefer_high else RETRY
    return "TIE"


def _mean_outcome(rows: Sequence[Mapping[str, str]], utilities: Mapping[str, float]) -> dict[str, float]:
    return {
        "status_utility": statistics.fmean(float(utilities[row["verification_status"]]) for row in rows),
        "progress": statistics.fmean(float(row["observed_progress"]) for row in rows),
        "steps": statistics.fmean(float(row["verification_steps"]) for row in rows),
    }


def _entropy(statuses: Sequence[str]) -> float:
    counts = Counter(statuses)
    total = len(statuses)
    return -sum((count / total) * math.log(count / total) for count in counts.values())


def _bootstrap_reliability(
    case_counts: Sequence[tuple[int, int]], *, seed: int, resamples: int
) -> dict[str, float] | None:
    if not case_counts or sum(total for _, total in case_counts) == 0:
        return None
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        sampled = [case_counts[rng.randrange(len(case_counts))] for _ in case_counts]
        denominator = sum(total for _, total in sampled)
        estimates.append(sum(correct for correct, _ in sampled) / denominator if denominator else 0.0)
    estimates.sort()
    return {
        "low": estimates[int(0.025 * resamples)],
        "high": estimates[min(resamples - 1, int(0.975 * resamples))],
    }


def analyze(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    if status.get("status") != "COMPLETED":
        raise RuntimeError("utility-stability analysis requires a completed run")
    repetitions = int(config["verification_repetitions"])
    utilities = {key: float(value) for key, value in config["estimands"]["status_utility"].items()}
    grouped: dict[int, dict[int, dict[str, dict[str, str]]]] = {}
    for row in _csv(run_dir / "candidate_results.csv"):
        episode = int(row["episode_id"])
        realization = int(row["realization_index"])
        grouped.setdefault(episode, {}).setdefault(realization, {})[row["candidate_id"]] = row

    case_rows: list[dict[str, Any]] = []
    loo_counts: list[tuple[int, int]] = []
    action_statuses = {COMPENSATION: Counter(), RETRY: Counter()}
    action_entropies = {COMPENSATION: [], RETRY: []}
    random_stream_violations = 0
    pair_completeness_violations = 0
    for episode, realizations in sorted(grouped.items()):
        if len(realizations) != repetitions:
            pair_completeness_violations += 1
            continue
        per_action = {COMPENSATION: [], RETRY: []}
        realization_winners: list[str] = []
        for realization, pair in sorted(realizations.items()):
            if set(pair) != {COMPENSATION, RETRY}:
                pair_completeness_violations += 1
                continue
            if pair[COMPENSATION]["paired_verification_seed"] != pair[RETRY]["paired_verification_seed"]:
                random_stream_violations += 1
            for action in (COMPENSATION, RETRY):
                per_action[action].append(pair[action])
                action_statuses[action][pair[action]["verification_status"]] += 1
            realization_winners.append(_winner(
                {
                    "status_utility": utilities[pair[COMPENSATION]["verification_status"]],
                    "progress": float(pair[COMPENSATION]["observed_progress"]),
                    "steps": float(pair[COMPENSATION]["verification_steps"]),
                },
                {
                    "status_utility": utilities[pair[RETRY]["verification_status"]],
                    "progress": float(pair[RETRY]["observed_progress"]),
                    "steps": float(pair[RETRY]["verification_steps"]),
                },
            ))

        means = {action: _mean_outcome(per_action[action], utilities) for action in per_action}
        expected_winner = _winner(means[COMPENSATION], means[RETRY])
        margin = means[COMPENSATION]["status_utility"] - means[RETRY]["status_utility"]
        correct = comparable = 0
        for held_out in range(repetitions):
            remaining = {
                action: [row for index, row in enumerate(per_action[action]) if index != held_out]
                for action in per_action
            }
            loo_winner = _winner(
                _mean_outcome(remaining[COMPENSATION], utilities),
                _mean_outcome(remaining[RETRY], utilities),
            )
            observed = realization_winners[held_out]
            if observed != "TIE" and loo_winner != "TIE":
                comparable += 1
                correct += int(observed == loo_winner)
        loo_counts.append((correct, comparable))
        for action in per_action:
            action_entropies[action].append(_entropy([row["verification_status"] for row in per_action[action]]))
        non_tie_winners = {winner for winner in realization_winners if winner != "TIE"}
        case_rows.append({
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "episode_id": episode,
            "seed": int(per_action[COMPENSATION][0]["seed"]),
            "compensation_accept_rate": sum(row["verification_status"] == "ACCEPTED" for row in per_action[COMPENSATION]) / repetitions,
            "retry_accept_rate": sum(row["verification_status"] == "ACCEPTED" for row in per_action[RETRY]) / repetitions,
            "compensation_mean_status_utility": means[COMPENSATION]["status_utility"],
            "retry_mean_status_utility": means[RETRY]["status_utility"],
            "compensation_minus_retry_utility": margin,
            "expected_winner": expected_winner,
            "stable_preference": abs(margin) >= float(config["estimands"]["stable_preference_absolute_mean_utility_margin"]),
            "realization_winner_reversal": len(non_tie_winners) > 1,
            "loo_correct": correct,
            "loo_comparable": comparable,
            "compensation_status_entropy": action_entropies[COMPENSATION][-1],
            "retry_status_entropy": action_entropies[RETRY][-1],
        })

    total_comparable = sum(total for _, total in loo_counts)
    total_correct = sum(correct for correct, _ in loo_counts)
    reliability = total_correct / total_comparable if total_comparable else None
    stable_count = sum(bool(row["stable_preference"]) for row in case_rows)
    integrity = {
        "chronology_violations": int(status["chronology_violations"]),
        "oracle_leakage_events": int(status["oracle_leakage_events"]),
        "budget_violations": int(status["budget_violations"]),
        "random_stream_violations": random_stream_violations,
        "pair_completeness_violations": pair_completeness_violations,
    }
    gate = (
        len(case_rows) >= int(config["estimands"]["operational_cases_minimum"])
        and stable_count >= int(config["estimands"]["stable_preference_cases_minimum"])
        and reliability is not None
        and reliability >= float(config["estimands"]["leave_one_realization_out_winner_reliability_minimum"])
        and not any(integrity.values())
    )
    summary = {
        "experiment_run_id": manifest["experiment_run_id"],
        "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"],
        "claim_scope": config["claim_scope"],
        "initial_units_scanned": int(status["initial_units_scanned"]),
        "operational_cases": len(case_rows),
        "verification_repetitions": repetitions,
        "candidate_rollouts": int(status["candidate_rollouts"]),
        "stable_preference_cases": stable_count,
        "realization_winner_reversal_cases": sum(bool(row["realization_winner_reversal"]) for row in case_rows),
        "leave_one_realization_out": {
            "correct": total_correct,
            "comparable": total_comparable,
            "winner_reliability": reliability,
            "bootstrap_ci95": _bootstrap_reliability(
                loo_counts, seed=int(config["bootstrap"]["seed"]),
                resamples=int(config["bootstrap"]["resamples"]),
            ),
        },
        "action_outcomes": {
            action: {
                "counts": dict(action_statuses[action]),
                "accepted_rate": action_statuses[action]["ACCEPTED"] / sum(action_statuses[action].values()),
                "mean_within_state_status_entropy": statistics.fmean(action_entropies[action]),
            }
            for action in (COMPENSATION, RETRY)
        },
        "integrity": integrity,
        "feasibility_gate_passed": gate,
        "selector_fitting_authorized": False,
        "llm_authorized": False,
        "validation_authorized": False,
        "threshold_fitted": False,
        "api_calls": 0,
    }
    with (run_dir / "utility_stability_cases.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(case_rows[0]))
        writer.writeheader()
        writer.writerows(case_rows)
    (run_dir / "utility_stability_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.run_dir.resolve()), indent=2))
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
