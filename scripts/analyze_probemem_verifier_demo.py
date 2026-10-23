"""Analyze ProbeMem verifier Demo runs without modifying frozen decisions."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import statistics
from typing import Any


FROZEN = "FROZEN_DETERMINISTIC"
ALWAYS = "ALWAYS_ON_VERIFIER"
BUDGETED = "BUDGETED_VERIFIER"
ORACLE = "EVALUATOR_ONLY_ORACLE"
ORDER = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "REJECTED": 0}


def analyze(run_dir: Path) -> dict[str, Any]:
    decisions = _csv(run_dir / "decisions.csv")
    candidates = _csv(run_dir / "candidate_outcomes.csv")
    memory = _json(run_dir / "operational_memory_records.json", [])
    status = _json(run_dir / "run_status.json", {})
    by_method: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in decisions:
        by_method[row["method"]].append(row)
    candidate_map = {(int(row["episode_id"]), row["candidate_skill"]): row for row in candidates}
    methods: dict[str, Any] = {}
    for method, rows in sorted(by_method.items()):
        operational_rows = [row for row in rows if not _bool(row.get("evaluator_only", False)) or method == ORACLE]
        distances = [float(row["final_object_goal_distance"]) for row in operational_rows]
        methods[method] = {
            "cases": len(operational_rows),
            "accepted": sum(row["verification_status"] == "ACCEPTED" for row in operational_rows),
            "exclusive_case_selection_accuracy": _exclusive_accuracy(operational_rows, candidate_map),
            "harmful_selections": sum(_harmful(row, candidate_map) for row in operational_rows if method != ORACLE),
            "mean_final_distance": None if not distances else statistics.fmean(distances),
            "environment_steps": sum(int(float(row["environment_steps"])) for row in operational_rows),
            "verifier_calls": sum(_bool(row.get("verifier_called", False)) for row in operational_rows),
            "overrides": sum(_bool(row.get("override_applied", False)) for row in operational_rows),
        }
    changes = {
        ALWAYS: _changes(by_method.get(FROZEN, []), by_method.get(ALWAYS, [])),
        BUDGETED: _changes(by_method.get(FROZEN, []), by_method.get(BUDGETED, [])),
    }
    for method in (ALWAYS, BUDGETED):
        denominator = changes[method]["helpful"] + changes[method]["harmful"]
        changes[method]["override_precision"] = None if denominator == 0 else changes[method]["helpful"] / denominator
    operational = len(by_method.get(FROZEN, []))
    exclusive = sum(_exclusive_episode(episode, candidate_map) for episode in {key[0] for key in candidate_map})
    budgeted_calls = methods.get(BUDGETED, {}).get("verifier_calls", 0)
    always_calls = methods.get(ALWAYS, {}).get("verifier_calls", 0)
    budgeted_call_rate = None if operational == 0 else budgeted_calls / operational
    call_reduction = None if always_calls == 0 else 1.0 - budgeted_calls / always_calls
    budgeted_rows = by_method.get(BUDGETED, [])
    latencies = [float(row["verifier_latency_ms"]) for row in budgeted_rows if _bool(row.get("verifier_called", False))]
    blocked = _blocked_overrides(budgeted_rows, candidate_map)
    integrity_names = (
        "chronology_violations", "oracle_leakage_events", "budget_violations",
        "random_namespace_violations", "future_memory_access", "counterfactual_memory_writes",
        "invalid_memory_ids", "invalid_skill_executions",
    )
    integrity = {name: int(status.get(name, 0)) for name in integrity_names}
    population_complete = status.get("status") == "COMPLETED"
    route_a = (
        methods.get(BUDGETED, {}).get("accepted", -1) >= methods.get(FROZEN, {}).get("accepted", 10**9)
        and changes[BUDGETED]["helpful"] > changes[BUDGETED]["harmful"]
    )
    route_b = (
        methods.get(BUDGETED, {}).get("accepted", -10**9) >= methods.get(ALWAYS, {}).get("accepted", 0) - 1
        and call_reduction is not None and call_reduction >= 0.50
    )
    gate_checks = {
        "population_complete": population_complete,
        "integrity_zero": not any(integrity.values()),
        "budgeted_call_rate_at_most_50_percent": budgeted_call_rate is not None and budgeted_call_rate <= 0.50,
        "route_a_or_b": route_a or route_b,
    }
    coverage_values = [float(row["memory_coverage"]) for row in budgeted_rows]
    summary = {
        "run_status": status.get("status", "UNKNOWN"),
        "experiment_run_id": status.get("experiment_run_id", run_dir.name),
        "manifest_id": status.get("manifest_id"),
        "source_git_commit": status.get("source_git_commit"),
        "initial_units": int(status.get("initial_units", 0)),
        "operational_cases": operational,
        "exclusive_recovery_cases": exclusive,
        "methods": methods,
        "overrides_vs_frozen": changes,
        "blocked_budgeted_overrides": blocked,
        "verifier_budget": {
            "budgeted_call_rate": budgeted_call_rate,
            "call_reduction_vs_always_on": call_reduction,
            "admission_scans": operational,
            "budgeted_full_candidate_retrievals": 2 * budgeted_calls,
            "always_on_full_candidate_retrievals": 2 * always_calls,
            "glm_api_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "timeout_or_fail_closed_count": sum("FAIL_CLOSED" in row.get("override_reason", "") for row in budgeted_rows),
            "deterministic_latency_ms": _latency(latencies),
        },
        "memory": {
            "mean_coverage": None if not coverage_values else statistics.fmean(coverage_values),
            "conflict_rate": None if operational == 0 else sum(_bool(row["memory_conflict"]) for row in budgeted_rows) / operational,
            "recent_contradiction_rate": None if operational == 0 else sum(_bool(row["recent_contradiction"]) for row in budgeted_rows) / operational,
            "growth_by_method": {method: sum(row["method"] == method for row in memory) for method in (FROZEN, ALWAYS, BUDGETED)},
        },
        "integrity": integrity,
        "demo_gate": {"evaluated": population_complete, "passed": all(gate_checks.values()), "checks": gate_checks, "route_a": route_a, "route_b": route_b},
        "claim_boundary": "engineering/research feasibility Demo; deterministic verifier only; no live GLM, validation, held-out, or statistical superiority claim",
    }
    return summary


def _changes(baseline: list[dict[str, str]], method: list[dict[str, str]]) -> dict[str, int]:
    left = {int(row["episode_id"]): row for row in baseline}
    right = {int(row["episode_id"]): row for row in method}
    result = {"changed": 0, "helpful": 0, "harmful": 0, "tie": 0}
    for episode in sorted(left.keys() & right.keys()):
        if left[episode]["final_skill"] == right[episode]["final_skill"]:
            continue
        result["changed"] += 1
        delta = ORDER[right[episode]["verification_status"]] - ORDER[left[episode]["verification_status"]]
        result["helpful" if delta > 0 else "harmful" if delta < 0 else "tie"] += 1
    return result


def _blocked_overrides(rows: list[dict[str, str]], candidates: dict[tuple[int, str], dict[str, str]]) -> dict[str, int]:
    result = {"blocked": 0, "blocked_helpful": 0, "blocked_harmful": 0, "blocked_tie": 0}
    for row in rows:
        if not _bool(row.get("verifier_called", False)) or _bool(row.get("override_applied", False)):
            continue
        alternative = next(skill for skill in ("BOUNDED_PLANAR_COMPENSATION", "INDEPENDENT_STOCHASTIC_RETRY") if skill != row["default_skill"])
        result["blocked"] += 1
        delta = ORDER[candidates[(int(row["episode_id"]), alternative)]["verification_status"]] - ORDER[row["verification_status"]]
        result["blocked_helpful" if delta > 0 else "blocked_harmful" if delta < 0 else "blocked_tie"] += 1
    return result


def _exclusive_accuracy(rows: list[dict[str, str]], candidates: dict[tuple[int, str], dict[str, str]]) -> float | None:
    scored = []
    for row in rows:
        episode = int(row["episode_id"])
        if not _exclusive_episode(episode, candidates):
            continue
        accepted = next(skill for (case, skill), candidate in candidates.items() if case == episode and candidate["verification_status"] == "ACCEPTED")
        scored.append(row["final_skill"] == accepted)
    return None if not scored else sum(scored) / len(scored)


def _exclusive_episode(episode: int, candidates: dict[tuple[int, str], dict[str, str]]) -> bool:
    statuses = [row["verification_status"] for (case, _), row in candidates.items() if case == episode]
    return len(statuses) == 2 and statuses.count("ACCEPTED") == 1


def _harmful(row: dict[str, str], candidates: dict[tuple[int, str], dict[str, str]]) -> bool:
    if row["verification_status"] == "ACCEPTED":
        return False
    return any(
        candidate["verification_status"] == "ACCEPTED"
        for (episode, skill), candidate in candidates.items()
        if episode == int(row["episode_id"]) and skill != row["final_skill"]
    )


def _latency(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p90": None, "maximum": None}
    ordered = sorted(values)
    return {"p50": statistics.median(ordered), "p90": ordered[max(0, (9 * len(ordered) + 9) // 10 - 1)], "maximum": max(ordered)}


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
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    run_dirs = sorted({path.parent for path in root.rglob("immutable_manifest.json")})
    if not run_dirs:
        raise FileNotFoundError("no verifier Demo manifests found")
    index = []
    for run_dir in run_dirs:
        result = analyze(run_dir)
        output = run_dir / "analysis_summary.json"
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        index.append({"run_dir": str(run_dir), **result})
        print(f"analysis: {output}")
    (root / "analysis_index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
