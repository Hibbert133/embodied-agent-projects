"""Analyze a completed or incomplete ProbeMem-Online chronological run."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
import statistics
from typing import Any, Iterable

import numpy as np


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
    common_steps = _common_environment_steps(run_dir, decisions)
    methods: dict[str, Any] = {}
    for method, rows in sorted(by_method.items()):
        accepted = sum(row["verification_status"] == "ACCEPTED" for row in rows)
        harmful = sum(_harmful(row, candidate_map) for row in rows if method != "EVALUATOR_ONLY_ORACLE")
        methods[method] = {
            "cases": len(rows), "accepted": accepted,
            "accepted_rate": accepted / len(rows) if rows else None,
            "abstentions": sum(_bool(row["abstain"]) for row in rows),
            "harmful_selections": harmful,
            "verification_steps": _verification_steps(rows, candidate_map),
            "total_environment_steps": None if common_steps is None else common_steps + _verification_steps(rows, candidate_map),
            "by_segment": _segment_summary(rows),
        }
    changes = _changes(by_method.get(STATELESS, []), by_method.get(FULL, []))
    paired = _paired_comparison(by_method.get(STATELESS, []), by_method.get(FULL, []))
    latencies = [float(row["latency_ms"]) for row in audit]
    valid = sum(bool(row.get("valid")) for row in audit)
    final_valid = len({(int(row["episode_id"]), str(row["method"])) for row in audit if row.get("valid")})
    input_tokens = sum(int(row.get("usage", {}).get("input_tokens", 0)) for row in audit)
    output_tokens = sum(int(row.get("usage", {}).get("output_tokens", 0)) for row in audit)
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
        deterministic_names = ("ALWAYS_COMPENSATION", "ALWAYS_RETRY", "FROZEN_VARIANCE_RULE", "DETERMINISTIC_ACTION_POSTERIOR")
        strongest_deterministic = max((methods[name]["accepted"] for name in deterministic_names), default=0)
        post_shift_full = _post_shift(full_result)
        post_shift_stateless = _post_shift(stateless_result)
        post_shift_gain = post_shift_full - post_shift_stateless
        full_cost = full_result.get("total_environment_steps")
        stateless_cost = stateless_result.get("total_environment_steps")
        equal_recovery_lower_cost = (
            full_result.get("accepted") == stateless_result.get("accepted")
            and full_cost is not None and stateless_cost is not None
            and full_cost <= 0.9 * stateless_cost
        )
        checks = {
            "action_change_rate_at_least_15_percent": changed_rate >= 0.15,
            "net_helpful_changes_at_least_3": net_helpful >= 3,
            "harmful_transfer_reduction_at_least_30_percent": harmful_reduction is not None and harmful_reduction >= 0.30,
            "recovery_within_one_case_of_strongest_deterministic": int(full_result["accepted"]) >= strongest_deterministic - 1,
            "post_shift_gain_or_equal_recovery_lower_cost": post_shift_gain >= 0.05 or equal_recovery_lower_cost,
        }
        gate["passed"] = all(checks.values())
        gate["checks"] = checks
        gate["diagnostics"] = {
            "strongest_deterministic_accepted": strongest_deterministic,
            "full_accepted": int(full_result["accepted"]),
            "post_shift_definition": "all frozen chronological segments after bias_dominant",
            "full_post_shift_rate": post_shift_full,
            "stateless_post_shift_rate": post_shift_stateless,
            "post_shift_rate_difference": post_shift_gain,
            "harmful_transfer_relative_reduction": harmful_reduction,
            "net_helpful_changes": net_helpful,
        }
        gate["reasons"] = [name for name, passed in checks.items() if not passed]
    else:
        gate["reasons"] = ["run_incomplete_or_integrity_not_satisfied"]
    return {
        "run_status": status.get("status", "UNKNOWN"),
        "operational_cases": operational,
        "target_operational_cases": target,
        "methods": methods,
        "full_vs_stateless_changes": changes,
        "full_vs_stateless_paired": paired,
        "api": {
            "calls": len(audit), "valid": valid,
            "valid_rate": valid / len(audit) if audit else None,
            "final_decisions_valid": final_valid,
            "expected_final_decisions": operational * 4,
            "repairs": sum(bool(row.get("repair")) for row in audit),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
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


def _paired_comparison(stateless: Iterable[dict[str, str]], full: Iterable[dict[str, str]],
                       *, samples: int = 10000, seed: int = 20260804) -> dict[str, Any]:
    left = {int(row["episode_id"]): row for row in stateless}
    right = {int(row["episode_id"]): row for row in full}
    episodes = sorted(left.keys() & right.keys())
    differences = np.asarray([
        float(right[episode]["verification_status"] == "ACCEPTED")
        - float(left[episode]["verification_status"] == "ACCEPTED")
        for episode in episodes
    ], dtype=float)
    ordinal = [STATUSES[right[episode]["verification_status"]] - STATUSES[left[episode]["verification_status"]]
               for episode in episodes]
    if not len(differences):
        return {"cases": 0, "accepted_rate_difference": None, "bootstrap_95_ci": None,
                "wins": 0, "ties": 0, "losses": 0}
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, len(differences), size=(samples, len(differences)))
    estimates = differences[indices].mean(axis=1)
    lower, upper = np.quantile(estimates, [0.025, 0.975])
    return {
        "cases": len(differences),
        "accepted_rate_difference": float(differences.mean()),
        "bootstrap_95_ci": [float(lower), float(upper)],
        "bootstrap_samples": samples,
        "bootstrap_seed": seed,
        "wins": sum(value > 0 for value in ordinal),
        "ties": sum(value == 0 for value in ordinal),
        "losses": sum(value < 0 for value in ordinal),
    }


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


def _post_shift(method: dict[str, Any]) -> float:
    segments = method.get("by_segment", {})
    selected = [value for name, value in segments.items() if name != "bias_dominant"]
    cases = sum(int(value["cases"]) for value in selected)
    return 0.0 if cases == 0 else sum(int(value["accepted"]) for value in selected) / cases


def _verification_steps(rows: Iterable[dict[str, str]], candidates: dict[tuple[int, str], dict[str, str]]) -> int:
    total = 0
    for row in rows:
        skill = row.get("selected_skill", "")
        candidate = candidates.get((int(row["episode_id"]), skill))
        if candidate is not None:
            total += int(candidate["steps"])
    return total


def _common_environment_steps(run_dir: Path, decisions: list[dict[str, str]]) -> int | None:
    seeds = {int(row["seed"]) for row in decisions}
    if not seeds:
        return 0
    trajectories = run_dir / "initial_trajectories"
    steps_by_seed: dict[int, int] = {}
    for path in trajectories.glob("unit*_seed*.jsonl"):
        try:
            seed = int(path.stem.rsplit("seed", 1)[1])
        except (IndexError, ValueError):
            continue
        if seed in seeds:
            with path.open(encoding="utf-8") as handle:
                steps_by_seed[seed] = sum(1 for line in handle if line.strip())
    if set(steps_by_seed) != seeds:
        return None
    return sum(steps_by_seed.values()) + 64 * len(seeds)


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
