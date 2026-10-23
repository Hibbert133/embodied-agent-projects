"""Replay frozen global and contextual ACR policies on a chronological stream."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.replay_probemem_acr_distributional_methods import _paired_bootstrap_difference  # noqa: E402
from scripts.run_probemem_acr_utility_stability import _write_csv, _write_json  # noqa: E402
from scripts.run_probemem_v2_smoke import _seed  # noqa: E402
from src.probemem.contextual_policy import (  # noqa: E402
    CONTEXTUAL_METHODS,
    ContextualOutcome,
    decide_contextual_action,
)
from src.probemem.distributional_policy import (  # noqa: E402
    COMPENSATION,
    RETRY,
    ObservedActionOutcome,
    decide_distributional_action,
)
from src.probemem.intervention_utility import INTERVENTION_APPLICABILITY_FEATURES  # noqa: E402


GLOBAL_METHODS = ("always_compensation", "always_retry", "accepted_only_last", "posterior_greedy")
STATUS_UTILITY = {"ACCEPTED": 1.0, "INCONCLUSIVE": 0.5, "REJECTED": 0.0}


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _evidence(path: Path) -> dict[int, tuple[float, ...]]:
    output = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        features = row["evidence_signature"]["features"]
        values = tuple(float(features[name]) for name in INTERVENTION_APPLICABILITY_FEATURES)
        output[int(row["episode_id"])] = values
    return output


def replay(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    if status.get("status") != "COMPLETED":
        raise RuntimeError("contextual replay requires a completed collection")
    methods = tuple(config["methods"])
    if methods != GLOBAL_METHODS + CONTEXTUAL_METHODS:
        raise ValueError("contextual method registry differs from the frozen implementation")
    grouped: dict[int, dict[str, dict[str, str]]] = {}
    for row in _csv(run_dir / "candidate_results.csv"):
        grouped.setdefault(int(row["operational_index"]), {})[row["candidate_id"]] = row
    if len(grouped) != int(config["stopping_rule"]["target_operational_cases"]):
        raise ValueError("operational population differs from the contextual target")
    evidence = _evidence(run_dir / "evidence_signatures.jsonl")

    global_history: dict[str, list[ObservedActionOutcome]] = {method: [] for method in GLOBAL_METHODS}
    contextual_history: dict[str, list[ContextualOutcome]] = {method: [] for method in CONTEXTUAL_METHODS}
    rows: list[dict[str, Any]] = []
    integrity = {
        "chronology_violations": 0,
        "oracle_leakage_events": 0,
        "current_outcome_predecision_reads": 0,
        "standardization_current_or_future_reads": 0,
    }
    global_policy = config["global_posterior"]
    contextual_policy = config["contextual_model"]
    for operational_index, pair in sorted(grouped.items()):
        if set(pair) != {COMPENSATION.value, RETRY.value}:
            raise ValueError("contextual candidate pair is incomplete")
        episode_id = int(pair[COMPENSATION.value]["episode_id"])
        seed = int(pair[COMPENSATION.value]["seed"])
        query = evidence[episode_id]
        for method_index, method in enumerate(methods):
            decision_timestamp = time.perf_counter_ns()
            if method in GLOBAL_METHODS:
                decision = decide_distributional_action(
                    method=method,
                    episode_id=episode_id,
                    operational_index=operational_index,
                    history=global_history[method],
                    exploration_episodes=int(global_policy["exploration_episodes"]),
                    superiority_probability=float(global_policy["superiority_probability"]),
                    monte_carlo_samples=int(global_policy["monte_carlo_samples"]),
                    sampling_seed=_seed(seed, int(config["random_namespaces"]["global_posterior_sampling"]) + method_index),
                )
                selected = decision.selected_skill
                history_ids = decision.history_episode_ids
                standardization_ids: tuple[int, ...] = ()
                comp_mean = decision.compensation_mean_utility
                retry_mean = decision.retry_mean_utility
                probability = decision.probability_compensation_better
            else:
                decision = decide_contextual_action(
                    method=method,
                    episode_id=episode_id,
                    operational_index=operational_index,
                    query_values=query,
                    history=contextual_history[method],
                    exploration_episodes=int(contextual_policy["exploration_episodes"]),
                    prior_precision=float(contextual_policy["prior_precision"]),
                    noise_variance=float(contextual_policy["noise_variance"]),
                    superiority_probability=float(contextual_policy["superiority_probability"]),
                    standardization_epsilon=float(contextual_policy["standardization_epsilon"]),
                )
                selected = decision.selected_skill
                history_ids = decision.history_episode_ids
                standardization_ids = decision.standardization_episode_ids
                comp_mean = decision.compensation.mean_utility
                retry_mean = decision.retry.mean_utility
                probability = decision.probability_compensation_better
                if any(item >= episode_id for item in standardization_ids):
                    integrity["standardization_current_or_future_reads"] += 1
            selected_row = pair[selected.value] if selected is not None else None
            alternative = RETRY if selected is COMPENSATION else COMPENSATION if selected is RETRY else None
            alternative_row = pair[alternative.value] if alternative is not None else None
            selected_accepted = bool(selected_row and selected_row["verification_status"] == "ACCEPTED")
            alternative_accepted = bool(alternative_row and alternative_row["verification_status"] == "ACCEPTED")
            any_accepted = any(item["verification_status"] == "ACCEPTED" for item in pair.values())
            predicted_utility = (
                comp_mean if selected is COMPENSATION else retry_mean if selected is RETRY else None
            )
            observed_utility = STATUS_UTILITY[selected_row["verification_status"]] if selected_row else None
            rows.append({
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"],
                "method": method,
                "operational_index": operational_index,
                "episode_id": episode_id,
                "seed": seed,
                "decision_timestamp_ns": decision_timestamp,
                "history_episode_ids": json.dumps(list(history_ids)),
                "standardization_episode_ids": json.dumps(list(standardization_ids)),
                "selected_skill": selected.value if selected else "ABSTAIN",
                "reason": decision.reason,
                "compensation_mean_utility": comp_mean,
                "retry_mean_utility": retry_mean,
                "probability_compensation_better": probability,
                "selected_predicted_utility": predicted_utility,
                "observed_utility": observed_utility,
                "verification_status": selected_row["verification_status"] if selected_row else "NOT_EXECUTED",
                "selected_accepted": selected_accepted,
                "alternative_accepted": alternative_accepted,
                "any_candidate_accepted": any_accepted,
                "harmful_transfer": selected is not None and not selected_accepted and alternative_accepted,
                "missed_recoverable_abstention": selected is None and any_accepted,
                "probe_steps": int(pair[COMPENSATION.value]["probe_steps"]),
                "verification_steps": int(selected_row["verification_steps"]) if selected_row else 0,
                "total_additional_steps": int(pair[COMPENSATION.value]["probe_steps"]) + (int(selected_row["verification_steps"]) if selected_row else 0),
            })
            if selected_row is not None:
                status_value = selected_row["verification_status"]
                if method in GLOBAL_METHODS:
                    global_history[method].append(ObservedActionOutcome(episode_id, selected, status_value))
                else:
                    contextual_history[method].append(
                        ContextualOutcome(episode_id, selected, STATUS_UTILITY[status_value], query)
                    )

    _write_csv(run_dir / "contextual_method_results.csv", rows)
    exploration = int(contextual_policy["exploration_episodes"])
    summaries: list[dict[str, Any]] = []
    for method in methods:
        selected_rows = [row for row in rows if row["method"] == method]
        post = [row for row in selected_rows if int(row["operational_index"]) > exploration]
        covered = [row for row in selected_rows if row["selected_skill"] != "ABSTAIN"]
        post_covered = [row for row in post if row["selected_skill"] != "ABSTAIN"]
        prediction_rows = [row for row in covered if row["selected_predicted_utility"] is not None]
        summaries.append({
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "method": method,
            "episodes": len(selected_rows),
            "accepted_cases": sum(bool(row["selected_accepted"]) for row in selected_rows),
            "accepted_rate": statistics.fmean(bool(row["selected_accepted"]) for row in selected_rows),
            "post_exploration_accepted_cases": sum(bool(row["selected_accepted"]) for row in post),
            "post_exploration_coverage": len(post_covered) / len(post),
            "covered_accepted_precision": statistics.fmean(bool(row["selected_accepted"]) for row in covered) if covered else None,
            "post_exploration_covered_precision": statistics.fmean(bool(row["selected_accepted"]) for row in post_covered) if post_covered else None,
            "harmful_transfer_cases": sum(bool(row["harmful_transfer"]) for row in selected_rows),
            "missed_recoverable_abstentions": sum(bool(row["missed_recoverable_abstention"]) for row in selected_rows),
            "abstentions": len(selected_rows) - len(covered),
            "mean_total_additional_steps": statistics.fmean(int(row["total_additional_steps"]) for row in selected_rows),
            "total_additional_steps": sum(int(row["total_additional_steps"]) for row in selected_rows),
            "utility_brier": statistics.fmean(
                (float(row["selected_predicted_utility"]) - float(row["observed_utility"])) ** 2
                for row in prediction_rows
            ) if prediction_rows else None,
        })
    _write_csv(run_dir / "contextual_method_summary.csv", summaries)
    by_method = {row["method"]: row for row in summaries}
    fixed_best = max(int(by_method[name]["accepted_cases"]) for name in ("always_compensation", "always_retry"))
    global_row = by_method["posterior_greedy"]
    contextual = by_method["contextual_greedy"]
    abstain = by_method["contextual_abstain"]
    gate = config["promotion_gate"]
    contextual_recovery_ok = int(contextual["accepted_cases"]) >= fixed_best - int(gate["strongest_fixed_accepted_shortfall_maximum"])
    greedy_route = (
        contextual_recovery_ok
        and int(contextual["accepted_cases"]) - int(global_row["accepted_cases"])
        >= int(gate["contextual_greedy_net_accepted_gain_over_global_minimum"])
        and int(contextual["harmful_transfer_cases"]) <= int(global_row["harmful_transfer_cases"])
    )
    global_harm = int(global_row["harmful_transfer_cases"])
    abstain_harm = int(abstain["harmful_transfer_cases"])
    relative_reduction = (global_harm - abstain_harm) / global_harm if global_harm else 0.0
    precision_gain = (
        float(abstain["post_exploration_covered_precision"]) - float(global_row["post_exploration_covered_precision"])
        if abstain["post_exploration_covered_precision"] is not None and global_row["post_exploration_covered_precision"] is not None
        else None
    )
    abstain_recovery_ok = int(abstain["accepted_cases"]) >= fixed_best - int(gate["strongest_fixed_accepted_shortfall_maximum"])
    abstain_route = (
        abstain_recovery_ok
        and relative_reduction >= float(gate["or_contextual_abstain_harmful_transfer_relative_reduction_minimum"])
        and global_harm - abstain_harm >= int(gate["or_contextual_abstain_harmful_transfer_absolute_reduction_minimum"])
        and float(abstain["post_exploration_coverage"]) >= float(gate["or_contextual_abstain_post_exploration_coverage_minimum"])
        and precision_gain is not None
        and precision_gain >= float(gate["or_contextual_abstain_post_exploration_precision_gain_minimum"])
    )
    zero_integrity = not any(int(value) for value in integrity.values())
    passed = len(grouped) >= int(gate["operational_cases_minimum"]) and zero_integrity and (greedy_route or abstain_route)
    binary = {
        method: [int(bool(row["selected_accepted"])) for row in rows if row["method"] == method]
        for method in methods
    }
    report = {
        "experiment_run_id": manifest["experiment_run_id"],
        "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"],
        "claim_scope": config["claim_scope"],
        "operational_cases": len(grouped),
        "method_summaries": by_method,
        "paired_bootstrap_accepted_difference": {
            "contextual_greedy_minus_global_posterior": _paired_bootstrap_difference(
                binary["contextual_greedy"], binary["posterior_greedy"],
                seed=int(config["random_namespaces"]["paired_bootstrap"]),
                resamples=int(config["bootstrap"]["resamples"]),
            ),
            "contextual_abstain_minus_global_posterior": _paired_bootstrap_difference(
                binary["contextual_abstain"], binary["posterior_greedy"],
                seed=int(config["random_namespaces"]["paired_bootstrap"]) + 1,
                resamples=int(config["bootstrap"]["resamples"]),
            ),
        },
        "promotion_routes": {
            "contextual_greedy": greedy_route,
            "contextual_abstain": abstain_route,
            "strongest_fixed_accepted_cases": fixed_best,
            "contextual_abstain_harmful_transfer_relative_reduction": relative_reduction,
            "contextual_abstain_post_exploration_precision_gain": precision_gain,
        },
        "integrity": integrity,
        "promotion_gate_passed": passed,
        "llm_authorized": False,
        "validation_authorized": False,
        "heldout_authorized": False,
        "api_calls": 0,
    }
    _write_json(run_dir / "contextual_summary.json", report)
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
