"""Audit whether first-verification feedback ranks one additional retry's value."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import _write_csv, _write_json  # noqa: E402
from src.probemem.retry_value_audit import average_precision, binary_roc_auc, finite, threshold_frontier  # noqa: E402


RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _truth(value: str) -> bool:
    return value.strip().lower() == "true"


def _describe(labels: list[bool], scores: list[float], name: str) -> dict[str, Any]:
    positive = [value for label, value in zip(labels, scores) if label]
    negative = [value for label, value in zip(labels, scores) if not label]
    return {
        "score_name": name,
        "roc_auc": binary_roc_auc(labels, scores),
        "pr_auc_average_precision": average_precision(labels, scores),
        "positive_mean": statistics.fmean(positive),
        "positive_median": statistics.median(positive),
        "negative_mean": statistics.fmean(negative),
        "negative_median": statistics.median(negative),
    }


def analyze(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source_dir = ROOT / config["source_run_directory"]
    manifest = json.loads((source_dir / "immutable_manifest.json").read_text(encoding="utf-8"))
    if manifest["experiment_run_id"] != config["source_run_id"] or manifest["manifest_id"] != config["source_manifest_id"]:
        raise ValueError("source run identity differs from the frozen audit config")
    cases = {
        int(row["episode_id"]): row
        for row in _read_csv(source_dir / "case_results.csv")
        if _truth(row["second_decision_required"])
    }
    retries = {
        int(row["episode_id"]): row
        for row in _read_csv(source_dir / "second_candidate_results.csv")
        if row["candidate_id"] == RETRY
    }
    if set(cases) != set(retries):
        raise ValueError("second-decision cases and paired retry outcomes do not match")
    episode_ids = sorted(cases)
    labels = [retries[episode]["verification_status"] == "ACCEPTED" for episode in episode_ids]
    progress = finite(float(cases[episode]["first_observed_progress"]) for episode in episode_ids)
    negative_distance = finite(-float(cases[episode]["first_final_object_goal_distance"]) for episode in episode_ids)
    status_mapping = config["registered_scores"]["categorical_status"]["mapping"]
    status = finite(float(status_mapping[cases[episode]["first_verification_status"]]) for episode in episode_ids)
    costs = [int(retries[episode]["verification_steps"]) for episode in episode_ids]
    score_sets = {
        "first_observed_progress": progress,
        "negative_first_final_distance": negative_distance,
        "categorical_status": status,
    }
    summary = {
        "audit_protocol": config["protocol"],
        "source_run_id": manifest["experiment_run_id"],
        "source_manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"],
        "population_size": len(labels),
        "positive_repeat_accepted": sum(labels),
        "negative_repeat_not_accepted": len(labels) - sum(labels),
        "positive_prevalence": statistics.fmean(labels),
        "scores": {name: _describe(labels, values, name) for name, values in score_sets.items()},
        "new_environment_interactions": 0,
        "api_calls": 0,
        "threshold_selected": False,
        "claim_scope": config["claim_scope"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "retry_value_summary.json", summary)
    frontier_rows: list[dict[str, Any]] = []
    for name, values in score_sets.items():
        frontier_rows.extend(threshold_frontier(labels=labels, scores=values, costs=costs, score_name=name))
    for row in frontier_rows:
        row.update({"source_run_id": manifest["experiment_run_id"], "source_manifest_id": manifest["manifest_id"]})
    _write_csv(output_dir / "retry_cost_recovery_frontier.csv", frontier_rows)
    case_rows = []
    for index, episode in enumerate(episode_ids):
        case_rows.append({
            "source_run_id": manifest["experiment_run_id"], "source_manifest_id": manifest["manifest_id"],
            "episode_id": episode, "seed": int(cases[episode]["seed"]),
            "first_verification_status": cases[episode]["first_verification_status"],
            "first_observed_progress": progress[index],
            "first_final_object_goal_distance": -negative_distance[index],
            "paired_retry_status_evaluator_only": retries[episode]["verification_status"],
            "paired_retry_accepted_evaluator_only": labels[index],
            "paired_retry_steps_evaluator_only": costs[index],
        })
    _write_csv(output_dir / "retry_value_cases.csv", case_rows)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/probemem_acr/retry_value_identifiability_audit_v1.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/probemem_acr/retry_value_audit_v1")
    args = parser.parse_args()
    try:
        result = analyze(args.config.resolve(), args.output_dir.resolve())
        print(json.dumps(result, indent=2))
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
