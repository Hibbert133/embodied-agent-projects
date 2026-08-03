"""Analyze a completed or incomplete ProbeMem-Online chronological run."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
import statistics
from typing import Any, Iterable


STATUSES = {"ACCEPTED": 2.0, "INCONCLUSIVE": 1.0, "REJECTED": 0.0, "ABSTAIN": 0.0}
STATELESS = "STATELESS_GLM"
FULL = "GLM_ONLINE_MEMORY_RESONANCE"


def analyze(run_dir: Path) -> dict[str, Any]:
    decisions = _csv(run_dir / "decisions.csv")
    candidates = _csv(run_dir / "candidate_outcomes.csv")
    audit = _json(run_dir / "api_audit.json", [])
    resonance = _json(run_dir / "resonance.json", [])
    status = _json(run_dir / "run_status.json", {})
    by_method: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in decisions:
        by_method[row["method"]].append(row)
    candidate_map = {(int(row["episode_id"]), row["candidate_skill"]): row for row in candidates}
    methods: dict[str, Any] = {}
    for method, rows in sorted(by_method.items()):
        accepted = sum(row["verification_status"] == "ACCEPTED" for row in rows)
        harmful = sum(_harmful(row, candidate_map) for row in rows if method != "EVALUATOR_ONLY_ORACLE")
        methods[method] = {
            "cases": len(rows), "accepted": accepted,
            "accepted_rate": accepted / len(rows) if rows else None,
            "abstentions": sum(_bool(row["abstain"]) for row in rows),
            "harmful_selections": harmful,
            "by_segment": _segment_summary(rows),
        }
    changes = _changes(by_method.get(STATELESS, []), by_method.get(FULL, []))
    latencies = [float(row["latency_ms"]) for row in audit]
    valid = sum(bool(row.get("valid")) for row in audit)
    operational = len({int(row["episode_id"]) for row in decisions})
    target = int(status.get("target_operational_cases", 60))
    integrity_names = (
        "chronology_violations", "oracle_leakage_events", "budget_violations",
        "random_namespace_violations", "future_memory_access",
        "counterfactual_memory_writes", "invalid_memory_ids", "invalid_skill_executions",
    )
    integrity = {name: int(status.get(name, 0)) for name in integrity_names}
    complete = status.get("status") == "COMPLETED" and operational == target
    full_result = methods.get(FULL, {})
    stateless_result = methods.get(STATELESS, {})
    gate = {
        "evaluated": complete and not any(integrity.values()),
        "passed": False,
        "reasons": [],
    }
    if gate["evaluated"]:
        changed_rate = changes["changed"] / operational
        net_helpful = changes["helpful"] - changes["harmful"]
        harmful_reduction = _relative_reduction(
            int(stateless_result["harmful_selections"]), int(full_result["harmful_selections"]),
        )
        checks = {
            "action_change_rate_at_least_15_percent": changed_rate >= 0.15,
            "net_helpful_changes_at_least_3": net_helpful >= 3,
            "harmful_transfer_reduction_at_least_30_percent": harmful_reduction is not None and harmful_reduction >= 0.30,
        }
        gate["passed"] = all(checks.values())
        gate["checks"] = checks
        gate["reasons"] = [name for name, passed in checks.items() if not passed]
    else:
        gate["reasons"] = ["run_incomplete_or_integrity_not_satisfied"]
    return {
        "run_status": status.get("status", "UNKNOWN"),
        "operational_cases": operational,
        "target_operational_cases": target,
        "methods": methods,
        "full_vs_stateless_changes": changes,
        "api": {
            "calls": len(audit), "valid": valid,
            "valid_rate": valid / len(audit) if audit else None,
            "repairs": sum(bool(row.get("repair")) for row in audit),
            "latency_ms": _latency(latencies),
        },
        "resonance": dict(Counter(row["resonance_class"] for row in resonance)),
        "integrity": integrity,
        "promotion_gate": gate,
    }


def _changes(stateless: Iterable[dict[str, str]], full: Iterable[dict[str, str]]) -> dict[str, int]:
    left = {int(row["episode_id"]): row for row in stateless}
    right = {int(row["episode_id"]): row for row in full}
    result = {"changed": 0, "helpful": 0, "harmful": 0, "tie": 0}
    for episode in sorted(left.keys() & right.keys()):
        if left[episode]["selected_skill"] == right[episode]["selected_skill"]:
            continue
        result["changed"] += 1
        delta = STATUSES[right[episode]["verification_status"]] - STATUSES[left[episode]["verification_status"]]
        if delta > 0:
            result["helpful"] += 1
        elif delta < 0:
            result["harmful"] += 1
        else:
            result["tie"] += 1
    return result


def _harmful(row: dict[str, str], candidates: dict[tuple[int, str], dict[str, str]]) -> bool:
    selected = row["selected_skill"]
    if not selected or row["verification_status"] == "ACCEPTED":
        return False
    alternatives = [candidate for (episode, skill), candidate in candidates.items()
                    if episode == int(row["episode_id"]) and skill != selected]
    return any(candidate["verification_status"] == "ACCEPTED" for candidate in alternatives)


def _segment_summary(rows: Iterable[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["segment_id_oracle"]].append(row)
    return {segment: {"cases": len(items), "accepted": sum(row["verification_status"] == "ACCEPTED" for row in items)}
            for segment, items in sorted(grouped.items())}


def _latency(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "p90": None, "max": None, "sum": None}
    ordered = sorted(values)
    index = max(0, int(0.9 * len(ordered) + 0.999999) - 1)
    return {"median": statistics.median(ordered), "p90": ordered[index], "max": max(ordered), "sum": sum(ordered)}


def _relative_reduction(before: int, after: int) -> float | None:
    return None if before == 0 else (before - after) / before


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
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
