"""Analyze the frozen ProbeMem-Online selective-override development run."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import statistics
from typing import Any, Iterable

import numpy as np


FROZEN = "FROZEN_VARIANCE_RULE"
PRIMARY = "AMBIGUITY_GATED_MEMORY_FALLBACK"
STATUSES = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "REJECTED": 0, "ABSTAIN": 0}


def analyze(run_dir: Path) -> dict[str, Any]:
    decisions = _csv(run_dir / "decisions.csv")
    candidates = _csv(run_dir / "candidate_outcomes.csv")
    audit = _json(run_dir / "api_audit.json", [])
    status = _json(run_dir / "run_status.json", {})
    by_method: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in decisions:
        by_method[row["method"]].append(row)
    candidate_map = {(int(row["episode_id"]), row["candidate_skill"]): row for row in candidates}
    methods: dict[str, Any] = {}
    for method, rows in sorted(by_method.items()):
        methods[method] = {
            "cases": len(rows),
            "accepted": sum(row["verification_status"] == "ACCEPTED" for row in rows),
            "abstentions": sum(_bool(row["abstain"]) for row in rows),
            "harmful_selections": sum(_harmful(row, candidate_map) for row in rows if "ORACLE" not in method),
            "api_decisions": sum(_bool(row["api_called"]) for row in rows),
        }
    changes = _changes(by_method.get(FROZEN, []), by_method.get(PRIMARY, []))
    paired = _paired(by_method.get(FROZEN, []), by_method.get(PRIMARY, []))
    operational = len({int(row["episode_id"]) for row in decisions})
    ambiguous = sum(_bool(row["ambiguous"]) for row in by_method.get(FROZEN, []))
    integrity_names = (
        "chronology_violations", "oracle_leakage_events", "budget_violations",
        "random_namespace_violations", "future_memory_access", "counterfactual_memory_writes",
        "invalid_memory_ids", "invalid_skill_executions", "high_confidence_api_calls",
    )
    integrity = {name: int(status.get(name, 0)) for name in integrity_names}
    maximum_all_case_calls = 3 * operational
    call_reduction = None if maximum_all_case_calls == 0 else 1.0 - len(audit) / maximum_all_case_calls
    complete = status.get("status") == "COMPLETED" and operational == int(status.get("target_operational_cases", 40))
    gate = {"evaluated": complete and not any(integrity.values()), "passed": False, "checks": {}, "reasons": []}
    if gate["evaluated"]:
        checks = {
            "operational_cases_at_least_40": operational >= 40,
            "ambiguous_cases_at_least_10": ambiguous >= 10,
            "net_helpful_overrides_at_least_3": changes["helpful"] - changes["harmful"] >= 3,
            "recovery_not_below_frozen_rule": methods[PRIMARY]["accepted"] >= methods[FROZEN]["accepted"],
            "api_call_reduction_at_least_50_percent": call_reduction is not None and call_reduction >= 0.50,
            "harmful_overrides_not_above_helpful": changes["harmful"] <= changes["helpful"],
        }
        gate.update({"passed": all(checks.values()), "checks": checks})
        gate["reasons"] = [name for name, passed in checks.items() if not passed]
    else:
        gate["reasons"] = ["run_incomplete_or_integrity_not_satisfied"]
    latencies = [float(row["latency_ms"]) for row in audit]
    return {
        "run_status": status.get("status", "UNKNOWN"),
        "operational_cases": operational, "ambiguous_cases": ambiguous,
        "methods": methods, "primary_vs_frozen_changes": changes,
        "primary_vs_frozen_paired": paired,
        "api": {
            "calls": len(audit), "repairs": sum(bool(row.get("repair")) for row in audit),
            "valid": sum(bool(row.get("valid")) for row in audit),
            "all_case_three_method_call_budget": maximum_all_case_calls,
            "call_reduction": call_reduction,
            "input_tokens": sum(int(row.get("usage", {}).get("input_tokens", 0)) for row in audit),
            "output_tokens": sum(int(row.get("usage", {}).get("output_tokens", 0)) for row in audit),
            "latency_ms": _latency(latencies),
        },
        "integrity": integrity, "promotion_gate": gate,
        "claim_boundary": "fresh development selective-override result; no validation, held-out, or principle claim",
    }


def _changes(baseline: Iterable[dict[str, str]], primary: Iterable[dict[str, str]]) -> dict[str, int]:
    left = {int(row["episode_id"]): row for row in baseline}
    right = {int(row["episode_id"]): row for row in primary}
    result = {"changed": 0, "helpful": 0, "harmful": 0, "tie": 0}
    for episode in sorted(left.keys() & right.keys()):
        if left[episode]["selected_skill"] == right[episode]["selected_skill"]:
            continue
        result["changed"] += 1
        delta = STATUSES[right[episode]["verification_status"]] - STATUSES[left[episode]["verification_status"]]
        result["helpful" if delta > 0 else "harmful" if delta < 0 else "tie"] += 1
    return result


def _paired(baseline: Iterable[dict[str, str]], primary: Iterable[dict[str, str]], *, samples: int = 10000) -> dict[str, Any]:
    left = {int(row["episode_id"]): row for row in baseline}
    right = {int(row["episode_id"]): row for row in primary}
    episodes = sorted(left.keys() & right.keys())
    values = np.asarray([
        float(right[episode]["verification_status"] == "ACCEPTED")
        - float(left[episode]["verification_status"] == "ACCEPTED") for episode in episodes
    ])
    if not len(values):
        return {"cases": 0, "accepted_rate_difference": None, "bootstrap_95_ci": None}
    generator = np.random.default_rng(20260805)
    indices = generator.integers(0, len(values), size=(samples, len(values)))
    low, high = np.quantile(values[indices].mean(axis=1), [0.025, 0.975])
    return {
        "cases": len(values), "accepted_rate_difference": float(values.mean()),
        "bootstrap_95_ci": [float(low), float(high)], "bootstrap_samples": samples,
    }


def _harmful(row: dict[str, str], candidates: dict[tuple[int, str], dict[str, str]]) -> bool:
    selected = row["selected_skill"]
    if not selected or row["verification_status"] == "ACCEPTED":
        return False
    return any(
        candidate["verification_status"] == "ACCEPTED"
        for (episode, skill), candidate in candidates.items()
        if episode == int(row["episode_id"]) and skill != selected
    )


def _latency(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "p90": None, "max": None}
    ordered = sorted(values)
    return {
        "median": statistics.median(ordered),
        "p90": ordered[max(0, int(0.9 * len(ordered) + 0.999999) - 1)],
        "max": max(ordered),
    }


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.stat().st_size:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() and path.stat().st_size else default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.run_dir.resolve())
    output = args.run_dir.resolve() / "analysis_summary.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"analysis: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
