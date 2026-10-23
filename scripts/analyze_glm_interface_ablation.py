"""Analyze the frozen ProbeMem-Online Gate-A shadow interface ablation."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
COMPENSATION = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"
INTERFACES = ("FULL_PAYLOAD", "COMPACT_EVIDENCE", "COMPACT_WITH_SKILL_SEMANTICS")


def _percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def analyze(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "immutable_manifest.json").read_text(encoding="utf-8"))
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    if status.get("status") != "COMPLETED":
        raise RuntimeError("Gate-A analysis requires a completed interface ablation")
    config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
    audit = json.loads((run_dir / "ablation_audit.json").read_text(encoding="utf-8"))
    source = ROOT / manifest["source_collection_run"]
    candidates = _read_csv(source / "candidate_results.csv")
    outcomes = {
        (int(row["episode_id"]), row["candidate_skill"]): row["verification_status"]
        for row in candidates
    }
    if len(audit) != 90 or len(outcomes) != 60:
        raise RuntimeError("Gate-A artifacts do not contain 90 calls and 60 paired outcomes")

    target_map = config["registered_target_mapping_evaluator_only"]
    per_interface: dict[str, Any] = {}
    for interface in INTERFACES:
        rows = [row for row in audit if row["interface"] == interface]
        stable = [row for row in rows if row["condition_id_evaluator_only"] == "fault_01"]
        stochastic = [row for row in rows if row["condition_id_evaluator_only"] == "fault_05"]
        raw_valid = sum(bool(row["base_attempt"].get("valid")) for row in rows)
        final_valid = sum(bool(row["final_valid"]) for row in rows)
        repairs = sum(row.get("repair_attempt") is not None for row in rows)
        correct = 0
        accepted = 0
        exclusive_total = 0
        exclusive_correct = 0
        latencies: list[float] = []
        input_tokens = 0
        output_tokens = 0
        invalid_skill_executions = 0
        for row in rows:
            decision = row["final_decision"]
            selected = decision["selected_skill"]
            target = target_map[row["condition_id_evaluator_only"]]
            correct += selected == target
            if selected is not None:
                accepted += outcomes[(int(row["episode_id"]), selected)] == "ACCEPTED"
            statuses = [outcomes[(int(row["episode_id"]), skill)] for skill in (COMPENSATION, RETRY)]
            if statuses.count("ACCEPTED") == 1:
                exclusive_total += 1
                winner = COMPENSATION if statuses[0] == "ACCEPTED" else RETRY
                exclusive_correct += selected == winner
            for attempt_name in ("base_attempt", "repair_attempt"):
                attempt = row.get(attempt_name)
                if not attempt:
                    continue
                if "latency_ms" in attempt:
                    latencies.append(float(attempt["latency_ms"]))
                usage = attempt.get("usage", {})
                input_tokens += int(usage.get("input_tokens", 0))
                output_tokens += int(usage.get("output_tokens", 0))
            invalid_skill_executions += int(bool(row.get("action_executed")))
        stable_comp = sum(row["final_decision"]["selected_skill"] == COMPENSATION for row in stable)
        stochastic_retry = sum(row["final_decision"]["selected_skill"] == RETRY for row in stochastic)
        stochastic_abstain = sum(bool(row["final_decision"]["abstain"]) for row in stochastic)
        per_interface[interface] = {
            "cases": len(rows),
            "raw_valid_count": raw_valid,
            "raw_valid_rate": raw_valid / len(rows),
            "post_repair_valid_count": final_valid,
            "post_repair_valid_rate": final_valid / len(rows),
            "repair_count": repairs,
            "schema_repair_rate": repairs / len(rows),
            "correct_skill_count": correct,
            "correct_skill_rate": correct / len(rows),
            "stable_bias_compensation_count": stable_comp,
            "stable_bias_compensation_rate": stable_comp / len(stable),
            "stochastic_retry_count": stochastic_retry,
            "stochastic_retry_rate": stochastic_retry / len(stochastic),
            "stochastic_abstain_count": stochastic_abstain,
            "stochastic_abstention_rate": stochastic_abstain / len(stochastic),
            "descriptive_matched_accepted_count": accepted,
            "descriptive_matched_accepted_rate": accepted / len(rows),
            "exclusive_case_count": exclusive_total,
            "exclusive_case_correct_count": exclusive_correct,
            "exclusive_case_accuracy": None if not exclusive_total else exclusive_correct / exclusive_total,
            "api_latency_ms_median": None if not latencies else statistics.median(latencies),
            "api_latency_ms_p90": _percentile(latencies, 0.90),
            "api_latency_ms_max": None if not latencies else max(latencies),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "invalid_skill_execution_count": invalid_skill_executions,
        }

    baseline = per_interface["FULL_PAYLOAD"]
    candidate = per_interface["COMPACT_WITH_SKILL_SEMANTICS"]
    net_correct = candidate["correct_skill_count"] - baseline["correct_skill_count"]
    baseline_abstain = baseline["stochastic_abstention_rate"]
    abstain_reduction = 0.0 if baseline_abstain == 0 else (baseline_abstain - candidate["stochastic_abstention_rate"]) / baseline_abstain
    gate = config["promotion_gate"]
    absolute = {
        "post_repair_validity": candidate["post_repair_valid_rate"] >= gate["post_repair_validity_minimum"],
        "stable_bias_compensation": candidate["stable_bias_compensation_rate"] >= gate["stable_bias_compensation_rate_minimum"],
        "stochastic_retry": candidate["stochastic_retry_rate"] >= gate["stochastic_retry_rate_minimum"],
        "stochastic_abstention": candidate["stochastic_abstention_rate"] <= gate["stochastic_abstention_rate_maximum"],
        "oracle_leakage": all("condition_id_evaluator_only" not in row["base_attempt"]["request_payload"] for row in audit),
        "invalid_skill_execution": sum(item["invalid_skill_execution_count"] for item in per_interface.values()) == 0,
    }
    comparative = {
        "net_correct_skill_gain": net_correct,
        "stochastic_abstention_relative_reduction": abstain_reduction,
        "net_correct_gate": net_correct >= gate["compact_semantics_correct_selection_net_gain_minimum"],
        "abstention_reduction_gate": abstain_reduction >= gate["compact_semantics_stochastic_abstention_reduction_minimum"],
    }
    passed = all(absolute.values()) and (comparative["net_correct_gate"] or comparative["abstention_reduction_gate"])
    return {
        "protocol": config["protocol"],
        "experiment_run_id": manifest["experiment_run_id"],
        "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"],
        "research_scope": "development-only shadow-mode matched audit",
        "per_interface": per_interface,
        "promotion": {"absolute": absolute, "comparative": comparative, "passed": passed},
        "gate_b_authorized": passed,
        "validation_authorized": False,
        "heldout_authorized": False,
        "claim_boundary": "No model action was executed; this result cannot support online-memory, validation, or held-out claims.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze(args.run_dir.resolve())
        path = args.run_dir.resolve() / "analysis_summary.json"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"analysis: {path}")
        print(f"Gate A passed: {result['promotion']['passed']}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
