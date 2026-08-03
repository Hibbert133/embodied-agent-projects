"""Analyze categorical stability and continuous feedback sufficiency."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import _write_csv, _write_json  # noqa: E402


COMPENSATION = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _auc(labels: list[int], scores: list[float]) -> float | None:
    positives = [score for label, score in zip(labels, scores) if label]
    negatives = [score for label, score in zip(labels, scores) if not label]
    if not positives or not negatives:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in positives for b in negatives)
    return wins / (len(positives) * len(negatives))


def _cluster_bootstrap(rows: list[dict[str, Any]], field: str, *, seed: int, resamples: int) -> dict[str, float]:
    by_state: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        by_state[int(row["episode_id"])].append(float(row[field]))
    states = sorted(by_state)
    point = statistics.fmean(value for values in by_state.values() for value in values)
    rng = random.Random(seed)
    samples = []
    for _ in range(resamples):
        selected = [rng.choice(states) for _ in states]
        values = [value for state in selected for value in by_state[state]]
        samples.append(statistics.fmean(values))
    samples.sort()
    return {"point": point, "low": samples[int(0.025 * resamples)], "high": samples[min(resamples - 1, int(0.975 * resamples))]}


def analyze(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "immutable_manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
    run_status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    if run_status.get("status") not in {"COMPLETED", "INCOMPLETE_POPULATION"}:
        raise RuntimeError("analysis requires completed collection")
    branches = _csv(run_dir / "branch_results.csv")
    candidates = _csv(run_dir / "second_candidate_results.csv")
    pairs: dict[tuple[int, int], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in candidates:
        pairs[(int(row["episode_id"]), int(row["realization_index"]))][row["candidate_id"]] = row
    state_statuses: dict[int, list[str]] = defaultdict(list)
    for row in branches:
        state_statuses[int(row["episode_id"])].append(row["first_verification_status"])
    stability_rows = []
    for episode_id, statuses in state_statuses.items():
        counts = Counter(statuses)
        stability_rows.append({"episode_id": episode_id, "seed": next(int(r["seed"]) for r in branches if int(r["episode_id"]) == episode_id), "modal_status": max(counts, key=lambda item: (counts[item], item)), "modal_share": max(counts.values()) / len(statuses), "mixed_status": len(counts) > 1, "accepted_count": counts["ACCEPTED"], "inconclusive_count": counts["INCONCLUSIVE"], "rejected_count": counts["REJECTED"]})
    _write_csv(run_dir / "state_stability.csv", stability_rows)
    decision_rows: list[dict[str, Any]] = []
    for row in branches:
        if row["first_verification_status"] == "ACCEPTED":
            continue
        key = (int(row["episode_id"]), int(row["realization_index"]))
        pair = pairs.get(key, {})
        if set(pair) != {COMPENSATION, RETRY}:
            raise ValueError(f"incomplete candidate pair: {key}")
        comp_ok = pair[COMPENSATION]["verification_status"] == "ACCEPTED"
        retry_ok = pair[RETRY]["verification_status"] == "ACCEPTED"
        exclusive = comp_ok != retry_ok
        status_action = RETRY if row["first_verification_status"] == "INCONCLUSIVE" else COMPENSATION
        decision_rows.append({"episode_id": key[0], "seed": int(row["seed"]), "realization_index": key[1], "first_status": row["first_verification_status"], "first_observed_progress": float(row["first_observed_progress"]), "negative_first_final_object_goal_distance": -float(row["first_final_object_goal_distance"]), "compensation_accepted": comp_ok, "retry_accepted": retry_ok, "exclusive_recovery": exclusive, "exclusive_retry_label": exclusive and retry_ok, "status_rule_accepted": pair[status_action]["verification_status"] == "ACCEPTED", "always_repeat_accepted": retry_ok, "always_switch_accepted": comp_ok, "candidate_winner": RETRY if retry_ok and not comp_ok else COMPENSATION if comp_ok and not retry_ok else "BOTH" if comp_ok else "NEITHER"})
    _write_csv(run_dir / "decision_audit.csv", decision_rows)
    exclusive = [row for row in decision_rows if row["exclusive_recovery"]]
    labels = [int(row["exclusive_retry_label"]) for row in exclusive]
    aucs = {name: _auc(labels, [float(row[name]) for row in exclusive]) for name in config["analysis"]["continuous_signals"]}
    winner_sets: dict[int, set[str]] = defaultdict(set)
    for row in decision_rows:
        winner_sets[int(row["episode_id"])].add(str(row["candidate_winner"]))
    status_mixed_fraction = statistics.fmean(bool(row["mixed_status"]) for row in stability_rows)
    mean_modal_share = statistics.fmean(float(row["modal_share"]) for row in stability_rows)
    instability = mean_modal_share <= float(config["analysis"]["status_instability_modal_share_maximum"]) or status_mixed_fraction >= float(config["analysis"]["status_instability_mixed_state_fraction_minimum"])
    gate = config["completion_gate"]
    integrity_keys = ("chronology_violations", "oracle_leakage_events", "budget_violations", "random_namespace_violations", "reset_violations")
    complete = len(stability_rows) >= int(gate["eligible_initial_states_minimum"]) and len(decision_rows) >= int(gate["nonaccepted_first_branches_minimum"]) and len(exclusive) >= int(gate["exclusive_second_recovery_branches_minimum"]) and not any(int(run_status.get(key, 0)) for key in integrity_keys)
    candidate_signal = complete and any(value is not None and value >= float(config["analysis"]["continuous_signal_auc_minimum"]) for value in aucs.values())
    seed = int(config["random_namespaces"]["cluster_bootstrap"])
    difference_rows = [{**row, "status_minus_repeat": int(row["status_rule_accepted"]) - int(row["always_repeat_accepted"]), "status_minus_switch": int(row["status_rule_accepted"]) - int(row["always_switch_accepted"])} for row in decision_rows]
    report = {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"], "claim_scope": config["claim_scope"], "eligible_initial_states": len(stability_rows), "first_realization_branches": len(branches), "nonaccepted_first_branches": len(decision_rows), "exclusive_second_recovery_branches": len(exclusive), "mean_modal_status_share": mean_modal_share, "mixed_status_state_fraction": status_mixed_fraction, "candidate_winner_reversal_states": sum(len(values) > 1 for values in winner_sets.values()), "conditional_second_acceptance": {status: {"cases": sum(row["first_status"] == status for row in decision_rows), "repeat_rate": statistics.fmean(row["always_repeat_accepted"] for row in decision_rows if row["first_status"] == status) if any(row["first_status"] == status for row in decision_rows) else None, "switch_rate": statistics.fmean(row["always_switch_accepted"] for row in decision_rows if row["first_status"] == status) if any(row["first_status"] == status for row in decision_rows) else None} for status in ("INCONCLUSIVE", "REJECTED")}, "continuous_signal_auc_retry_only": aucs, "cluster_bootstrap_status_rule_difference": {"vs_always_repeat": _cluster_bootstrap(difference_rows, "status_minus_repeat", seed=seed, resamples=int(config["analysis"]["bootstrap_resamples"])), "vs_always_switch": _cluster_bootstrap(difference_rows, "status_minus_switch", seed=seed + 1, resamples=int(config["analysis"]["bootstrap_resamples"]))}, "integrity_complete": complete, "status_instability_detected": instability, "continuous_signal_candidate": candidate_signal, "selector_authorized": False, "glm_authorized": False, "memory_authorized": False, "validation_authorized": False, "heldout_authorized": False, "api_calls": 0}
    _write_json(run_dir / "analysis_summary.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.run_dir.resolve()), indent=2))
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
