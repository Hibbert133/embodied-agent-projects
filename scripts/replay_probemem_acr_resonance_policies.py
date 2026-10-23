"""Replay frozen second-verification policies over collected paired outcomes."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import _write_csv, _write_json  # noqa: E402
from src.probemem.resonance_policy import (  # noqa: E402
    COMPENSATION,
    METHODS,
    RETRY,
    decide_second_attempt,
)


STATUS_UTILITY = {"ACCEPTED": 1.0, "INCONCLUSIVE": 0.5, "REJECTED": 0.0}


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _truth(value: str) -> bool:
    return value.strip().lower() == "true"


def _paired_bootstrap_difference(
    left: Sequence[int], right: Sequence[int], *, seed: int, resamples: int,
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


def _oracle_candidate(pair: dict[str, dict[str, str]]) -> tuple[str, bool]:
    rows = list(pair.values())
    rows.sort(
        key=lambda row: (
            STATUS_UTILITY[row["verification_status"]],
            float(row["observed_progress"]),
            -int(row["verification_steps"]),
        ),
        reverse=True,
    )
    top = rows[0]
    top_key = (
        STATUS_UTILITY[top["verification_status"]],
        float(top["observed_progress"]), -int(top["verification_steps"]),
    )
    tied = sum(
        (
            STATUS_UTILITY[row["verification_status"]],
            float(row["observed_progress"]), -int(row["verification_steps"]),
        ) == top_key
        for row in rows
    ) > 1
    return top["candidate_id"], tied


def replay(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    if status.get("status") != "COMPLETED":
        raise RuntimeError("resonance replay requires a completed collection")
    if tuple(config["methods"]) != METHODS:
        raise ValueError("method registry differs from frozen implementation")
    cases = [row for row in _csv(run_dir / "case_results.csv") if _truth(row["eligible_first_attempt"])]
    grouped: dict[int, dict[str, dict[str, str]]] = {}
    for row in _csv(run_dir / "second_candidate_results.csv"):
        grouped.setdefault(int(row["episode_id"]), {})[row["candidate_id"]] = row
    if len(grouped) != int(config["stopping_rule"]["target_second_decision_cases"]):
        raise ValueError("second-decision population differs from frozen target")
    case_by_episode = {int(row["episode_id"]): row for row in cases}
    if len(case_by_episode) != len(cases):
        raise ValueError("duplicate eligible first-attempt episode")

    result_rows: list[dict[str, Any]] = []
    integrity = {
        "chronology_violations": 0,
        "oracle_leakage_events": 0,
        "budget_violations": 0,
        "attempt_limit_violations": 0,
    }
    for row in cases:
        episode_id = int(row["episode_id"])
        first_status = row["first_verification_status"]
        pair = grouped.get(episode_id)
        if first_status == "ACCEPTED" and pair is not None:
            raise ValueError("accepted first verification unexpectedly has second candidates")
        if first_status != "ACCEPTED" and (pair is None or set(pair) != {COMPENSATION.value, RETRY.value}):
            raise ValueError("non-accepted first verification lacks a complete candidate pair")
        online_before_second = int(row["online_steps_before_optional_second"])
        for method in METHODS:
            oracle_tie = False
            if method == "oracle_second":
                if first_status == "ACCEPTED":
                    selected_name = None
                else:
                    assert pair is not None
                    selected_name, oracle_tie = _oracle_candidate(pair)
                reason = "evaluator_only_counterfactual_oracle"
            else:
                decision = decide_second_attempt(
                    method=method, first_verification_status=first_status,
                    remaining_budget=int(config["budget"]["second_verification_max_steps"]),
                    reserved_second_verification_budget=int(config["budget"]["second_verification_max_steps"]),
                )
                selected_name = decision.selected_skill.value if decision.selected_skill else None
                reason = decision.reason
            selected = pair[selected_name] if pair is not None and selected_name is not None else None
            alternative_name = (
                RETRY.value if selected_name == COMPENSATION.value
                else COMPENSATION.value if selected_name == RETRY.value else None
            )
            alternative = pair[alternative_name] if pair is not None and alternative_name else None
            first_accepted = first_status == "ACCEPTED"
            second_accepted = bool(selected and selected["verification_status"] == "ACCEPTED")
            alternative_accepted = bool(alternative and alternative["verification_status"] == "ACCEPTED")
            any_second_accepted = bool(pair and any(item["verification_status"] == "ACCEPTED" for item in pair.values()))
            total_steps = online_before_second + (int(selected["verification_steps"]) if selected else 0)
            if total_steps > int(config["budget"]["online_max_steps_per_case"]):
                integrity["budget_violations"] += 1
            result_rows.append({
                "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"], "method": method,
                "episode_id": episode_id, "seed": int(row["seed"]),
                "first_attempt_index": int(row["first_attempt_index"]),
                "second_decision_index": int(row["second_decision_index"] or 0),
                "first_verification_status": first_status,
                "second_decision_required": first_status != "ACCEPTED",
                "selected_second_skill": selected_name or "ABSTAIN",
                "decision_reason": reason, "oracle_tie": oracle_tie,
                "second_verification_status": selected["verification_status"] if selected else "NOT_EXECUTED",
                "final_accepted": first_accepted or second_accepted,
                "incremental_recovery": not first_accepted and second_accepted,
                "alternative_second_accepted": alternative_accepted,
                "any_second_candidate_accepted": any_second_accepted,
                "harmful_second_selection": selected is not None and not second_accepted and alternative_accepted,
                "missed_recoverable_abstention": selected is None and not first_accepted and any_second_accepted,
                "second_attempt_requested": selected is not None,
                "initial_steps": int(row["initial_steps"]), "probe_steps": int(row["probe_steps"]),
                "first_verification_steps": int(row["first_verification_steps"]),
                "second_verification_steps": int(selected["verification_steps"]) if selected else 0,
                "total_online_environment_steps": total_steps,
            })

    if any(integrity.values()):
        raise RuntimeError(f"resonance replay integrity failure: {integrity}")
    _write_csv(run_dir / "method_results.csv", result_rows)
    summaries: list[dict[str, Any]] = []
    for method in METHODS:
        rows = [item for item in result_rows if item["method"] == method]
        decision_rows = [item for item in rows if item["second_decision_required"]]
        summaries.append({
            "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
            "method": method, "eligible_first_attempts": len(rows),
            "second_decision_cases": len(decision_rows),
            "first_attempt_accepted": sum(item["first_verification_status"] == "ACCEPTED" for item in rows),
            "final_accepted_cases": sum(bool(item["final_accepted"]) for item in rows),
            "final_accepted_rate": statistics.fmean(bool(item["final_accepted"]) for item in rows),
            "incremental_recoveries": sum(bool(item["incremental_recovery"]) for item in rows),
            "second_attempts": sum(bool(item["second_attempt_requested"]) for item in rows),
            "second_attempt_rate_on_decisions": statistics.fmean(bool(item["second_attempt_requested"]) for item in decision_rows),
            "harmful_second_selections": sum(bool(item["harmful_second_selection"]) for item in rows),
            "missed_recoverable_abstentions": sum(bool(item["missed_recoverable_abstention"]) for item in rows),
            "mean_total_online_environment_steps": statistics.fmean(int(item["total_online_environment_steps"]) for item in rows),
            "total_online_environment_steps": sum(int(item["total_online_environment_steps"]) for item in rows),
            "accepted_after_first_inconclusive": sum(bool(item["final_accepted"]) for item in decision_rows if item["first_verification_status"] == "INCONCLUSIVE"),
            "cases_after_first_inconclusive": sum(item["first_verification_status"] == "INCONCLUSIVE" for item in decision_rows),
            "accepted_after_first_rejected": sum(bool(item["final_accepted"]) for item in decision_rows if item["first_verification_status"] == "REJECTED"),
            "cases_after_first_rejected": sum(item["first_verification_status"] == "REJECTED" for item in decision_rows),
        })
    _write_csv(run_dir / "method_summary.csv", summaries)
    by_method = {row["method"]: row for row in summaries}
    fixed_name = max(
        ("repeat_retry", "switch_compensation"),
        key=lambda name: int(by_method[name]["final_accepted_cases"]),
    )
    fixed = by_method[fixed_name]
    conditioned = by_method["status_conditioned"]
    gate = by_method["rejection_abstain"]
    conditioned_route = (
        int(conditioned["final_accepted_cases"]) - int(fixed["final_accepted_cases"])
        >= int(config["promotion_gate"]["status_conditioned_net_accepted_gain_over_strongest_fixed_minimum"])
    )
    gate_reduction = (
        (int(fixed["second_attempts"]) - int(gate["second_attempts"])) / int(fixed["second_attempts"])
        if int(fixed["second_attempts"]) else 0.0
    )
    gate_route = (
        int(fixed["final_accepted_cases"]) - int(gate["final_accepted_cases"])
        <= int(config["promotion_gate"]["or_rejection_abstain_accepted_deficit_maximum"])
        and gate_reduction >= float(config["promotion_gate"]["or_rejection_abstain_second_attempt_relative_reduction_minimum"])
        and int(gate["total_online_environment_steps"]) < int(fixed["total_online_environment_steps"])
    )
    binary = {
        method: [int(bool(row["final_accepted"])) for row in result_rows if row["method"] == method]
        for method in METHODS
    }
    bootstrap_seed = int(config["random_namespaces"]["paired_bootstrap"])
    report = {
        "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"], "claim_scope": config["claim_scope"],
        "eligible_first_attempts": len(cases), "second_decision_cases": len(grouped),
        "strongest_fixed_second_policy": fixed_name, "method_summaries": by_method,
        "paired_bootstrap_accepted_difference": {
            "status_conditioned_minus_strongest_fixed": _paired_bootstrap_difference(
                binary["status_conditioned"], binary[fixed_name], seed=bootstrap_seed,
                resamples=int(config["bootstrap"]["resamples"]),
            ),
            "rejection_abstain_minus_strongest_fixed": _paired_bootstrap_difference(
                binary["rejection_abstain"], binary[fixed_name], seed=bootstrap_seed + 1,
                resamples=int(config["bootstrap"]["resamples"]),
            ),
        },
        "promotion_routes": {
            "status_conditioned": conditioned_route,
            "rejection_abstain": gate_route,
            "rejection_abstain_second_attempt_relative_reduction": gate_reduction,
        },
        "integrity": integrity,
        "promotion_gate_passed": len(grouped) >= int(config["promotion_gate"]["second_decision_cases_minimum"]) and (conditioned_route or gate_route),
        "llm_authorized": False, "memory_authorized": False,
        "validation_authorized": False, "heldout_authorized": False, "api_calls": 0,
    }
    _write_json(run_dir / "resonance_summary.json", report)
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
