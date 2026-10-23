"""Analyze persistent-regime action-selection feasibility."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import _write_json  # noqa: E402


COMPENSATION = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def analyze(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "immutable_manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    if status["status"] != "COMPLETED":
        raise RuntimeError("analysis requires completed collection")
    cases = [row for row in _csv(run_dir / "case_results.csv") if row["paired_comparable"].lower() == "true"]
    grouped: dict[int, dict[str, dict[str, str]]] = {}
    for row in _csv(run_dir / "candidate_results.csv"):
        grouped.setdefault(int(row["episode_id"]), {})[row["candidate_id"]] = row
    results = {"always_compensation": [], "always_retry": [], "frozen_probe_rule": [], "oracle": []}
    exclusive = 0
    exclusive_correct = 0
    condition_operational = Counter(row["condition_id_oracle"] for row in cases)
    condition_diagnosis_correct = Counter()
    for row in cases:
        episode = int(row["episode_id"])
        pair = grouped.get(episode, {})
        if set(pair) != {COMPENSATION, RETRY}:
            raise ValueError("operational case lacks paired candidates")
        accepted = {name: pair[name]["verification_status"] == "ACCEPTED" for name in pair}
        selected = row["selected_skill"]
        expected = COMPENSATION if row["condition_id_oracle"] == "fault_01" else RETRY
        condition_diagnosis_correct[row["condition_id_oracle"]] += selected == expected
        if accepted[COMPENSATION] != accepted[RETRY]:
            exclusive += 1
            exclusive_correct += accepted[selected]
        for method, skill in (("always_compensation", COMPENSATION), ("always_retry", RETRY), ("frozen_probe_rule", selected)):
            results[method].append({"accepted": accepted[skill], "harmful": not accepted[skill] and accepted[RETRY if skill == COMPENSATION else COMPENSATION], "steps": int(pair[skill]["verification_steps"])})
        oracle_skill = min((COMPENSATION, RETRY), key=lambda name: (-int(accepted[name]), -float(pair[name]["observed_progress"]), int(pair[name]["verification_steps"]), name))
        results["oracle"].append({"accepted": accepted[oracle_skill], "harmful": False, "steps": int(pair[oracle_skill]["verification_steps"])})
    summaries = {name: {"cases": len(values), "accepted": sum(item["accepted"] for item in values), "accepted_rate": statistics.fmean(item["accepted"] for item in values), "harmful": sum(item["harmful"] for item in values), "mean_verification_steps": statistics.fmean(item["steps"] for item in values)} for name, values in results.items()}
    strongest = min(("always_compensation", "always_retry"), key=lambda name: (-summaries[name]["accepted"], summaries[name]["harmful"], name))
    completion = config["completion_gate"]
    integrity_keys = ("chronology_violations", "oracle_leakage_events", "budget_violations", "random_namespace_violations")
    population_complete = len(cases) >= int(completion["operational_cases_minimum"]) and all(condition_operational[item] >= int(completion["operational_cases_per_condition_minimum"]) for item in config["conditions"]) and exclusive >= int(completion["exclusive_recovery_cases_minimum"]) and not any(int(status[key]) for key in integrity_keys)
    gate = config["promotion_gate"]
    exclusive_accuracy = exclusive_correct / exclusive if exclusive else None
    promoted = population_complete and exclusive_accuracy is not None and exclusive_accuracy >= float(gate["exclusive_selection_accuracy_minimum"]) and summaries["frozen_probe_rule"]["accepted"] >= summaries[strongest]["accepted"] - int(gate["accepted_case_deficit_to_strongest_fixed_maximum"]) and summaries["frozen_probe_rule"]["harmful"] <= summaries[strongest]["harmful"]
    summary = {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"], "initial_units": int(status["initial_units"]), "operational_cases": len(cases), "operational_by_condition": dict(condition_operational), "exclusive_recovery_cases": exclusive, "exclusive_selection_correct": exclusive_correct, "exclusive_selection_accuracy": exclusive_accuracy, "condition_mechanism_accuracy": {name: condition_diagnosis_correct[name] / condition_operational[name] for name in condition_operational}, "method_summaries": summaries, "strongest_fixed": strongest, "population_complete": population_complete, "promotion_gate_passed": promoted, "glm_action_development_authorized": promoted, "memory_authorized": False, "validation_authorized": False, "heldout_authorized": False, "api_calls": 0, "claim_scope": config["claim_scope"]}
    _write_json(run_dir / "analysis_summary.json", summary)
    return summary


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
