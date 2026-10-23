"""Chronologically replay frozen distributional ACR methods on paired outcomes."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import _write_csv, _write_json  # noqa: E402
from scripts.run_probemem_v2_smoke import _seed  # noqa: E402
from src.probemem.distributional_policy import (  # noqa: E402
    COMPENSATION,
    METHODS,
    RETRY,
    ObservedActionOutcome,
    decide_distributional_action,
)


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _paired_bootstrap_difference(
    left: Sequence[int], right: Sequence[int], *, seed: int, resamples: int
) -> dict[str, float]:
    if len(left) != len(right) or not left:
        raise ValueError("paired bootstrap requires equal non-empty samples")
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        indices = [rng.randrange(len(left)) for _ in left]
        values.append(statistics.fmean(left[index] - right[index] for index in indices))
    values.sort()
    return {
        "point": statistics.fmean(a - b for a, b in zip(left, right)),
        "low": values[int(0.025 * resamples)],
        "high": values[min(resamples - 1, int(0.975 * resamples))],
    }


def _selected_accept_probability(decision: Any) -> float | None:
    if decision.selected_skill is None:
        return None
    alpha = decision.compensation_alpha if decision.selected_skill is COMPENSATION else decision.retry_alpha
    return float(alpha[0] / sum(alpha))


def replay(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    if status.get("status") != "COMPLETED":
        raise RuntimeError("distributional replay requires a completed collection")
    policy = config["distributional_policy"]
    if tuple(config["methods"]) != METHODS:
        raise ValueError("method registry differs from frozen implementation")
    grouped: dict[int, dict[str, dict[str, str]]] = {}
    for row in _csv(run_dir / "candidate_results.csv"):
        grouped.setdefault(int(row["operational_index"]), {})[row["candidate_id"]] = row
    if len(grouped) != int(config["stopping_rule"]["target_operational_cases"]):
        raise ValueError("operational population differs from frozen target")

    histories: dict[str, list[ObservedActionOutcome]] = {method: [] for method in METHODS}
    result_rows: list[dict[str, Any]] = []
    integrity = {"chronology_violations": 0, "oracle_leakage_events": 0, "current_outcome_predecision_reads": 0}
    for operational_index, pair in sorted(grouped.items()):
        if set(pair) != {COMPENSATION.value, RETRY.value}:
            raise ValueError("candidate pair is incomplete")
        episode_id = int(pair[COMPENSATION.value]["episode_id"])
        seed = int(pair[COMPENSATION.value]["seed"])
        for method_index, method in enumerate(METHODS):
            decision_timestamp = time.perf_counter_ns()
            decision = decide_distributional_action(
                method=method, episode_id=episode_id, operational_index=operational_index,
                history=histories[method], exploration_episodes=int(policy["exploration_episodes"]),
                superiority_probability=float(policy["superiority_probability"]),
                monte_carlo_samples=int(policy["monte_carlo_samples"]),
                sampling_seed=_seed(seed, int(config["random_namespaces"]["posterior_sampling"]) + method_index),
            )
            selected = decision.selected_skill
            selected_row = pair[selected.value] if selected is not None else None
            alternative = RETRY if selected is COMPENSATION else COMPENSATION if selected is RETRY else None
            alternative_row = pair[alternative.value] if alternative is not None else None
            selected_accepted = bool(selected_row and selected_row["verification_status"] == "ACCEPTED")
            alternative_accepted = bool(alternative_row and alternative_row["verification_status"] == "ACCEPTED")
            any_accepted = any(row["verification_status"] == "ACCEPTED" for row in pair.values())
            predicted_accept = _selected_accept_probability(decision)
            result_rows.append({
                "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"], "method": method,
                "operational_index": operational_index, "episode_id": episode_id, "seed": seed,
                "decision_timestamp_ns": decision_timestamp,
                "history_episode_ids": json.dumps(list(decision.history_episode_ids)),
                "history_size": len(histories[method]), "selected_skill": selected.value if selected else "ABSTAIN",
                "reason": decision.reason, "compensation_alpha": json.dumps(decision.compensation_alpha),
                "retry_alpha": json.dumps(decision.retry_alpha),
                "compensation_mean_utility": decision.compensation_mean_utility,
                "retry_mean_utility": decision.retry_mean_utility,
                "probability_compensation_better": decision.probability_compensation_better,
                "selected_predicted_accept_probability": predicted_accept,
                "verification_status": selected_row["verification_status"] if selected_row else "NOT_EXECUTED",
                "selected_accepted": selected_accepted, "alternative_accepted": alternative_accepted,
                "any_candidate_accepted": any_accepted,
                "harmful_transfer": selected is not None and not selected_accepted and alternative_accepted,
                "missed_recoverable_abstention": selected is None and any_accepted,
                "probe_steps": int(pair[COMPENSATION.value]["probe_steps"]),
                "verification_steps": int(selected_row["verification_steps"]) if selected_row else 0,
                "total_additional_steps": int(pair[COMPENSATION.value]["probe_steps"]) + (int(selected_row["verification_steps"]) if selected_row else 0),
                "current_outcome_read_after_decision": True,
            })
            if selected_row is not None:
                histories[method].append(ObservedActionOutcome(episode_id, selected, selected_row["verification_status"]))

    _write_csv(run_dir / "method_results.csv", result_rows)
    summaries: list[dict[str, Any]] = []
    exploration = int(policy["exploration_episodes"])
    for method in METHODS:
        rows = [row for row in result_rows if row["method"] == method]
        post = [row for row in rows if int(row["operational_index"]) > exploration]
        selected = [row for row in rows if row["selected_skill"] != "ABSTAIN"]
        post_selected = [row for row in post if row["selected_skill"] != "ABSTAIN"]
        brier_rows = [row for row in selected if row["selected_predicted_accept_probability"] is not None]
        summaries.append({
            "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
            "method": method, "episodes": len(rows),
            "accepted_cases": sum(bool(row["selected_accepted"]) for row in rows),
            "accepted_rate": statistics.fmean(bool(row["selected_accepted"]) for row in rows),
            "post_exploration_accepted_cases": sum(bool(row["selected_accepted"]) for row in post),
            "post_exploration_coverage": len(post_selected) / len(post),
            "covered_accepted_precision": statistics.fmean(bool(row["selected_accepted"]) for row in selected) if selected else None,
            "post_exploration_covered_precision": statistics.fmean(bool(row["selected_accepted"]) for row in post_selected) if post_selected else None,
            "harmful_transfer_cases": sum(bool(row["harmful_transfer"]) for row in rows),
            "missed_recoverable_abstentions": sum(bool(row["missed_recoverable_abstention"]) for row in rows),
            "abstentions": len(rows) - len(selected),
            "mean_total_additional_steps": statistics.fmean(int(row["total_additional_steps"]) for row in rows),
            "total_additional_steps": sum(int(row["total_additional_steps"]) for row in rows),
            "selected_accept_brier": statistics.fmean((float(row["selected_predicted_accept_probability"]) - int(bool(row["selected_accepted"]))) ** 2 for row in brier_rows) if brier_rows else None,
        })
    _write_csv(run_dir / "method_summary.csv", summaries)
    by_method = {row["method"]: row for row in summaries}
    binary = {
        method: [int(bool(row["selected_accepted"])) for row in result_rows if row["method"] == method]
        for method in METHODS
    }
    last = by_method["accepted_only_last"]
    greedy = by_method["posterior_greedy"]
    abstain = by_method["posterior_abstain"]
    greedy_route = (
        int(greedy["accepted_cases"]) - int(last["accepted_cases"])
        >= int(config["promotion_gate"]["posterior_greedy_net_accepted_gain_over_last_success_minimum"])
        and int(greedy["harmful_transfer_cases"]) <= int(last["harmful_transfer_cases"])
    )
    last_harm = int(last["harmful_transfer_cases"])
    abstain_harm = int(abstain["harmful_transfer_cases"])
    relative_reduction = (last_harm - abstain_harm) / last_harm if last_harm else 0.0
    precision_gain = (
        float(abstain["post_exploration_covered_precision"]) - float(last["post_exploration_covered_precision"])
        if abstain["post_exploration_covered_precision"] is not None and last["post_exploration_covered_precision"] is not None
        else float("-inf")
    )
    abstain_route = (
        relative_reduction >= float(config["promotion_gate"]["or_abstain_harmful_transfer_relative_reduction_minimum"])
        and last_harm - abstain_harm >= int(config["promotion_gate"]["or_abstain_harmful_transfer_absolute_reduction_minimum"])
        and precision_gain >= float(config["promotion_gate"]["or_abstain_covered_precision_gain_minimum"])
        and float(abstain["post_exploration_coverage"]) >= float(config["promotion_gate"]["or_abstain_post_exploration_coverage_minimum"])
    )
    zero_integrity = not any(int(value) for value in integrity.values())
    passed = len(grouped) >= int(config["promotion_gate"]["operational_cases_minimum"]) and zero_integrity and (greedy_route or abstain_route)
    report = {
        "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"], "claim_scope": config["claim_scope"],
        "operational_cases": len(grouped), "method_summaries": by_method,
        "paired_bootstrap_accepted_difference": {
            "posterior_greedy_minus_accepted_only_last": _paired_bootstrap_difference(
                binary["posterior_greedy"], binary["accepted_only_last"],
                seed=int(config["random_namespaces"]["paired_bootstrap"]), resamples=int(config["bootstrap"]["resamples"]),
            ),
            "posterior_abstain_minus_accepted_only_last": _paired_bootstrap_difference(
                binary["posterior_abstain"], binary["accepted_only_last"],
                seed=int(config["random_namespaces"]["paired_bootstrap"]) + 1, resamples=int(config["bootstrap"]["resamples"]),
            ),
        },
        "promotion_routes": {
            "posterior_greedy": greedy_route, "posterior_abstain": abstain_route,
            "abstain_harmful_transfer_relative_reduction": relative_reduction,
            "abstain_post_exploration_precision_gain": precision_gain if precision_gain != float("-inf") else None,
        },
        "integrity": integrity, "promotion_gate_passed": passed,
        "llm_authorized": False, "validation_authorized": False, "heldout_authorized": False,
        "api_calls": 0,
    }
    _write_json(run_dir / "distributional_summary.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(replay(args.run_dir.resolve()), indent=2))
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
