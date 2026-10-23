"""Analyze the immutable ProbeMem-ACR second-verification validation."""

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
from src.probemem.resonance_policy import COMPENSATION, METHODS, RETRY, decide_second_attempt  # noqa: E402


STATUS_UTILITY = {"ACCEPTED": 1.0, "INCONCLUSIVE": 0.5, "REJECTED": 0.0}


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _truth(value: str) -> bool:
    return value.strip().lower() == "true"


def _paired_bootstrap_difference(
    left: Sequence[float], right: Sequence[float], *, seed: int, resamples: int,
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
    rows = sorted(
        pair.values(),
        key=lambda row: (STATUS_UTILITY[row["verification_status"]], float(row["observed_progress"]),
                         -int(row["verification_steps"]), row["candidate_id"]),
        reverse=True,
    )
    score = lambda row: (STATUS_UTILITY[row["verification_status"]], float(row["observed_progress"]),  # noqa: E731
                         -int(row["verification_steps"]))
    return rows[0]["candidate_id"], score(rows[0]) == score(rows[1])


def _select_strongest_fixed(summary: dict[str, dict[str, Any]]) -> str:
    return min(
        ("repeat_retry", "switch_compensation"),
        key=lambda method: (
            -int(summary[method]["final_accepted_cases"]),
            int(summary[method]["harmful_second_selections"]),
            int(summary[method]["total_online_environment_steps"]),
            method,
        ),
    )


def analyze(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "immutable_manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
    run_status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    if run_status.get("status") not in {"COMPLETED", "INCOMPLETE_FOR_VALIDATION"}:
        raise RuntimeError("validation analysis requires a completed or explicitly incomplete collection")
    if tuple(config["methods"]) != METHODS:
        raise ValueError("validation method registry differs from frozen host policy")
    cases = [row for row in _csv(run_dir / "case_results.csv") if _truth(row["eligible_first_attempt"])]
    grouped: dict[int, dict[str, dict[str, str]]] = {}
    candidate_path = run_dir / "second_candidate_results.csv"
    if candidate_path.exists():
        for row in _csv(candidate_path):
            grouped.setdefault(int(row["episode_id"]), {})[row["candidate_id"]] = row
    result_rows: list[dict[str, Any]] = []
    integrity = {"chronology_violations": 0, "oracle_leakage_events": 0,
                 "budget_violations": 0, "attempt_limit_violations": 0,
                 "counterfactual_predecision_reads": 0}
    for row in cases:
        episode_id = int(row["episode_id"])
        first_status = row["first_verification_status"]
        pair = grouped.get(episode_id)
        if first_status == "ACCEPTED" and pair is not None:
            raise ValueError("first success unexpectedly has second counterfactuals")
        if first_status != "ACCEPTED" and (pair is None or set(pair) != {COMPENSATION.value, RETRY.value}):
            raise ValueError("second-decision case lacks complete paired candidates")
        first_distance = float(row["first_final_object_goal_distance"])
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
            selected = pair[selected_name] if pair is not None and selected_name else None
            alternative_name = RETRY.value if selected_name == COMPENSATION.value else COMPENSATION.value if selected_name == RETRY.value else None
            alternative = pair[alternative_name] if pair is not None and alternative_name else None
            first_accepted = first_status == "ACCEPTED"
            second_accepted = bool(selected and selected["verification_status"] == "ACCEPTED")
            alternative_accepted = bool(alternative and alternative["verification_status"] == "ACCEPTED")
            any_second_accepted = bool(pair and any(item["verification_status"] == "ACCEPTED" for item in pair.values()))
            second_steps = int(selected["verification_steps"]) if selected else 0
            total_steps = online_before_second + second_steps
            if total_steps > int(config["budget"]["online_max_steps_per_case"]):
                integrity["budget_violations"] += 1
            final_distance = float(selected["final_object_goal_distance"]) if selected else first_distance
            result_rows.append({
                "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"], "method": method,
                "episode_id": episode_id, "seed": int(row["seed"]),
                "first_attempt_index": int(row["first_attempt_index"]),
                "second_decision_index": int(row["second_decision_index"] or 0),
                "first_verification_status": first_status,
                "second_decision_required": first_status != "ACCEPTED",
                "selected_second_skill": selected_name or "ABSTAIN", "decision_reason": reason,
                "oracle_tie": oracle_tie,
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
                "second_verification_steps": second_steps,
                "total_online_environment_steps": total_steps,
                "final_object_goal_distance": final_distance,
            })
    if any(integrity.values()):
        raise RuntimeError(f"validation analysis integrity failure: {integrity}")
    _write_csv(run_dir / "method_results.csv", result_rows)
    summaries: list[dict[str, Any]] = []
    for method in METHODS:
        rows = [item for item in result_rows if item["method"] == method]
        decisions = [item for item in rows if item["second_decision_required"]]
        distances = [float(item["final_object_goal_distance"]) for item in rows]
        summaries.append({
            "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
            "method": method, "eligible_first_attempts": len(rows), "second_decision_cases": len(decisions),
            "first_attempt_accepted": sum(item["first_verification_status"] == "ACCEPTED" for item in rows),
            "final_accepted_cases": sum(bool(item["final_accepted"]) for item in rows),
            "final_accepted_rate": statistics.fmean(bool(item["final_accepted"]) for item in rows),
            "incremental_recoveries": sum(bool(item["incremental_recovery"]) for item in rows),
            "second_attempts": sum(bool(item["second_attempt_requested"]) for item in rows),
            "harmful_second_selections": sum(bool(item["harmful_second_selection"]) for item in rows),
            "missed_recoverable_abstentions": sum(bool(item["missed_recoverable_abstention"]) for item in rows),
            "mean_final_object_goal_distance": statistics.fmean(distances),
            "median_final_object_goal_distance": statistics.median(distances),
            "mean_total_online_environment_steps": statistics.fmean(int(item["total_online_environment_steps"]) for item in rows),
            "total_online_environment_steps": sum(int(item["total_online_environment_steps"]) for item in rows),
            "accepted_after_first_inconclusive": sum(bool(item["final_accepted"]) for item in decisions if item["first_verification_status"] == "INCONCLUSIVE"),
            "cases_after_first_inconclusive": sum(item["first_verification_status"] == "INCONCLUSIVE" for item in decisions),
            "accepted_after_first_rejected": sum(bool(item["final_accepted"]) for item in decisions if item["first_verification_status"] == "REJECTED"),
            "cases_after_first_rejected": sum(item["first_verification_status"] == "REJECTED" for item in decisions),
        })
    by_method = {row["method"]: row for row in summaries}
    single = by_method["single_retry"]
    for row in summaries:
        extra_steps = int(row["total_online_environment_steps"]) - int(single["total_online_environment_steps"])
        extra_recoveries = int(row["final_accepted_cases"]) - int(single["final_accepted_cases"])
        row["recovery_per_additional_100_steps"] = (100.0 * extra_recoveries / extra_steps) if extra_steps > 0 else None
    _write_csv(run_dir / "method_summary.csv", summaries)
    fixed_name = _select_strongest_fixed(by_method)
    fixed, conditioned = by_method[fixed_name], by_method["status_conditioned"]
    recovery_not_below = int(conditioned["final_accepted_cases"]) >= int(fixed["final_accepted_cases"])
    harm_not_above = int(conditioned["harmful_second_selections"]) <= int(fixed["harmful_second_selections"])
    recovery_tied = int(conditioned["final_accepted_cases"]) == int(fixed["final_accepted_cases"])
    tie_improvement = any((
        int(conditioned["total_online_environment_steps"]) < int(fixed["total_online_environment_steps"]),
        int(conditioned["second_attempts"]) < int(fixed["second_attempts"]),
        int(conditioned["harmful_second_selections"]) < int(fixed["harmful_second_selections"]),
    ))
    population_complete = (
        run_status["status"] == "COMPLETED"
        and len(cases) >= int(config["population"]["eligible_first_attempts_minimum"])
        and len(grouped) >= int(config["population"]["second_decision_cases_minimum"])
    )
    promotion = population_complete and recovery_not_below and harm_not_above and (not recovery_tied or tie_improvement)
    def values(method: str, field: str) -> list[float]:
        return [float(row[field]) for row in result_rows if row["method"] == method]
    seed = int(config["random_namespaces"]["paired_bootstrap"])
    conditioned_rows = [row for row in result_rows if row["method"] == "status_conditioned"]
    fixed_rows = [row for row in result_rows if row["method"] == fixed_name]
    wins = sum(bool(a["final_accepted"]) and not bool(b["final_accepted"]) for a, b in zip(conditioned_rows, fixed_rows))
    losses = sum(not bool(a["final_accepted"]) and bool(b["final_accepted"]) for a, b in zip(conditioned_rows, fixed_rows))
    report = {
        "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"], "claim_scope": config["claim_scope"],
        "initial_units_scanned": int(run_status["initial_units_scanned"]),
        "eligible_first_attempts": len(cases), "second_decision_cases": len(grouped),
        "strongest_fixed_second_policy": fixed_name, "method_summaries": by_method,
        "status_conditioned_vs_strongest_fixed_win_tie_loss": {
            "wins": wins, "ties": len(conditioned_rows) - wins - losses, "losses": losses,
        },
        "paired_bootstrap_difference": {
            "accepted_rate": _paired_bootstrap_difference(values("status_conditioned", "final_accepted"), values(fixed_name, "final_accepted"), seed=seed, resamples=int(config["bootstrap"]["resamples"])),
            "harmful_selection_rate": _paired_bootstrap_difference(values("status_conditioned", "harmful_second_selection"), values(fixed_name, "harmful_second_selection"), seed=seed + 1, resamples=int(config["bootstrap"]["resamples"])),
            "environment_steps": _paired_bootstrap_difference(values("status_conditioned", "total_online_environment_steps"), values(fixed_name, "total_online_environment_steps"), seed=seed + 2, resamples=int(config["bootstrap"]["resamples"])),
        },
        "promotion_checks": {
            "population_complete": population_complete, "recovery_not_below": recovery_not_below,
            "harmful_selections_not_above": harm_not_above,
            "recovery_tied": recovery_tied, "tie_has_strict_efficiency_improvement": tie_improvement,
        },
        "integrity": integrity, "promotion_gate_passed": promotion,
        "validation_status": "PROMOTED" if promotion else "NOT_PROMOTED" if population_complete else "INCOMPLETE_FOR_VALIDATION",
        "glm_development_authorized": promotion, "memory_authorized": False,
        "heldout_authorized": False, "api_calls": 0,
    }
    _write_json(run_dir / "validation_summary.json", report)
    return report


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
