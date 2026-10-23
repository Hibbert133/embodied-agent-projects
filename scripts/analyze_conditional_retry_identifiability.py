"""Run the frozen state-stratified retry identifiability audit."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import _write_csv, _write_json  # noqa: E402
from src.probemem.conditional_identifiability import within_group_permutation_test  # noqa: E402
from src.probemem.retry_value_audit import average_precision, binary_roc_auc  # noqa: E402


RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def analyze(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    source = ROOT / config["source_run_directory"]
    manifest = json.loads((source / "immutable_manifest.json").read_text(encoding="utf-8"))
    if (manifest["experiment_run_id"], manifest["manifest_id"]) != (config["source_run_id"], config["source_manifest_id"]):
        raise ValueError("source run identity differs from frozen config")
    branches = {
        (int(row["episode_id"]), int(row["realization_index"])): row
        for row in _csv(source / "branch_results.csv")
        if row["first_verification_status"] != "ACCEPTED"
    }
    retry_rows = {
        (int(row["episode_id"]), int(row["realization_index"])): row
        for row in _csv(source / "second_candidate_results.csv")
        if row["candidate_id"] == RETRY
    }
    if set(branches) != set(retry_rows):
        raise ValueError("branch population lacks complete paired retry outcomes")
    keys = sorted(branches)
    groups = [key[0] for key in keys]
    labels = [retry_rows[key]["verification_status"] == "ACCEPTED" for key in keys]
    status_map = config["registered_scores"]["categorical_status"]
    scores = {
        "first_observed_progress": [float(branches[key]["first_observed_progress"]) for key in keys],
        "negative_first_final_object_goal_distance": [-float(branches[key]["first_final_object_goal_distance"]) for key in keys],
        "categorical_status": [float(status_map[branches[key]["first_verification_status"]]) for key in keys],
    }
    permutation = config["permutation_test"]
    analyses = {}
    for offset, (name, values) in enumerate(scores.items()):
        analyses[name] = {
            "marginal_roc_auc": binary_roc_auc(labels, values),
            "marginal_pr_auc": average_precision(labels, values),
            "conditional": within_group_permutation_test(
                groups, labels, values, seed=int(permutation["seed"]) + offset,
                resamples=int(permutation["resamples"]),
            ),
        }
    summary = {
        "audit_protocol": config["protocol"], "source_run_id": manifest["experiment_run_id"],
        "source_manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"],
        "branches": len(keys), "unique_initial_states": len(set(groups)),
        "repeat_accepted": sum(labels), "repeat_not_accepted": len(labels) - sum(labels),
        "analyses": analyses, "new_environment_interactions": 0, "api_calls": 0,
        "selector_authorized": False, "validation_authorized": False, "heldout_authorized": False,
        "claim_scope": config["claim_scope"],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "conditional_retry_summary.json", summary)
    _write_csv(output_dir / "conditional_retry_cases.csv", [{
        "source_run_id": manifest["experiment_run_id"], "source_manifest_id": manifest["manifest_id"],
        "episode_id": key[0], "realization_index": key[1], "seed": int(branches[key]["seed"]),
        "first_verification_status": branches[key]["first_verification_status"],
        "first_observed_progress": scores["first_observed_progress"][index],
        "first_final_object_goal_distance": -scores["negative_first_final_object_goal_distance"][index],
        "paired_retry_status_evaluator_only": retry_rows[key]["verification_status"],
        "paired_retry_accepted_evaluator_only": labels[index],
    } for index, key in enumerate(keys)])
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/probemem_acr/conditional_retry_identifiability_audit_v1.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/probemem_acr/conditional_retry_audit_v1")
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.config.resolve(), args.output_dir.resolve()), indent=2))
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
