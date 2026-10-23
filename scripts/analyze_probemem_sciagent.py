"""Analyze one immutable ProbeMem-SciAgent Demo run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
from typing import Any


STATUS_ORDER = {"REJECTED": 0, "INCONCLUSIVE": 1, "ACCEPTED": 2}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    decisions = _read(run / "decisions.json", [])
    experiences = _read(run / "experience_memory.json", [])
    probes = _read(run / "micro_probes.json", [])
    outcomes = _read(run / "candidate_outcomes_evaluator_only.json", [])
    principles = _read(run / "principle_memory.json", [])
    api = _read(run / "api_audit.json", [])
    status = _read(run / "run_status.json", {})
    by_episode: dict[str, dict[str, dict[str, Any]]] = {}
    for row in outcomes:
        by_episode.setdefault(row["episode_id"], {})[row["candidate_skill"]] = row
    pre = {row["episode_id"]: row for row in decisions if row["stage"] == "PRE_PROBE"}
    post = {row["episode_id"]: row for row in decisions if row["stage"] == "POST_PROBE"}
    helpful = harmful = tie = changes = 0
    for episode_id, later in post.items():
        earlier = pre[episode_id]
        if earlier["selected_skill"] == later["selected_skill"]:
            continue
        changes += 1
        rows = by_episode.get(episode_id, {})
        if earlier["selected_skill"] not in rows or later["selected_skill"] not in rows: continue
        delta = STATUS_ORDER[rows[later["selected_skill"]]["verification_status"]] - STATUS_ORDER[rows[earlier["selected_skill"]]["verification_status"]]
        helpful += int(delta > 0); harmful += int(delta < 0); tie += int(delta == 0)
    latencies = sorted(float(row["latency_ms"]) for row in api if "latency_ms" in row)
    token_input = sum(int(row.get("usage", {}).get("input_tokens", 0)) for row in api)
    token_output = sum(int(row.get("usage", {}).get("output_tokens", 0)) for row in api)
    analysis = {
        "run_status": status.get("status"), "operational_cases": status.get("operational_cases", len(pre)),
        "selected_experiences": len(experiences),
        "accepted_recoveries": sum(row["verification_status"] == "ACCEPTED" for row in experiences),
        "probe_calls": len(probes), "probe_call_rate": 0.0 if not pre else len(probes) / len(pre),
        "probe_action_changes": changes, "helpful_probes": helpful, "harmful_probes": harmful,
        "tie_probe_changes": tie, "active_principles": sum(row["status"] == "ACTIVE" for row in principles),
        "restricted_principles": sum(row["status"] == "RESTRICTED" for row in principles),
        "suspended_principles": sum(row["status"] == "SUSPENDED" for row in principles),
        "glm_calls": len(api), "input_tokens": token_input, "output_tokens": token_output,
        "latency_p50_ms": _percentile(latencies, 0.5), "latency_p90_ms": _percentile(latencies, 0.9),
        "integrity": {key: status.get(key, 0) for key in (
            "chronology_violations", "oracle_leakage", "future_memory_access",
            "counterfactual_memory_writes", "invalid_principle_ids",
            "invalid_skill_execution", "probe_budget_violations",
        )},
        "claim_boundary": "engineering_feasibility_only",
    }
    (run / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(analysis, indent=2))
    return 0


def _read(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values: return None
    index = (len(values) - 1) * quantile; lower = int(index); upper = min(lower + 1, len(values) - 1); weight = index - lower
    return values[lower] * (1 - weight) + values[upper] * weight


if __name__ == "__main__": raise SystemExit(main())
