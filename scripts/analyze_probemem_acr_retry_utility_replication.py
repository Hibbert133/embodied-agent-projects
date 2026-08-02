"""Evaluate the two frozen ACR retry-utility replication endpoints."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_probemem_acr_failure_localization import (  # noqa: E402
    COMPENSATION,
    RETRY,
    outcome_partition,
    rank_probability,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _bootstrap_rank_ci(positive: list[float], negative: list[float], *, seed: int, resamples: int) -> dict[str, float]:
    rng = random.Random(seed)
    samples = []
    for _ in range(resamples):
        left = [positive[rng.randrange(len(positive))] for _ in positive]
        right = [negative[rng.randrange(len(negative))] for _ in negative]
        samples.append(rank_probability(left, right))
    samples.sort()
    return {
        "low": samples[int(0.025 * resamples)],
        "high": samples[min(resamples - 1, int(0.975 * resamples))],
    }


def analyze(run_dir: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    if status.get("status") != "COMPLETED" or int(status["initial_units"]) != 100:
        raise RuntimeError("replication analysis requires a completed 100-unit run")
    candidates_by_episode: dict[int, list[dict[str, str]]] = {}
    for row in _read_csv(run_dir / "candidate_results.csv"):
        candidates_by_episode.setdefault(int(row["episode_id"]), []).append(row)
    evidence = {int(row["episode_id"]): row for row in _read_jsonl(run_dir / "evidence_signatures.jsonl")}
    exclusive_rows: list[dict[str, Any]] = []
    partitions: dict[str, int] = {}
    for episode_id, group in sorted(candidates_by_episode.items()):
        if len(group) != 2 or len({row["paired_verification_seed"] for row in group}) != 1:
            raise ValueError("replication candidate pair is incomplete or not randomness-matched")
        if any(int(row["outcome_timestamp_ns"]) <= int(evidence[episode_id]["evidence_timestamp_ns"]) for row in group):
            raise ValueError("replication candidate outcome precedes evidence")
        partition = outcome_partition({row["candidate_id"]: row["verification_status"] for row in group})
        partitions[partition] = partitions.get(partition, 0) + 1
        if partition in {"COMPENSATION_ONLY_RECOVERY", "RETRY_ONLY_RECOVERY"}:
            exclusive_rows.append({
                "episode_id": episode_id,
                "seed": int(group[0]["seed"]),
                "partition": partition,
                **evidence[episode_id]["evidence_signature"]["features"],
            })
    retry = [row for row in exclusive_rows if row["partition"] == "RETRY_ONLY_RECOVERY"]
    compensation = [row for row in exclusive_rows if row["partition"] == "COMPENSATION_ONLY_RECOVERY"]
    endpoints = {}
    endpoint_passes = []
    for index, feature in enumerate(config["registered_directional_hypotheses"]):
        positive = [float(row[feature]) for row in retry]
        negative = [float(row[feature]) for row in compensation]
        probability = rank_probability(positive, negative) if positive and negative else None
        endpoint_pass = probability is not None and probability >= float(config["replication_gate"]["rank_probability_retry_greater_minimum_per_feature"])
        endpoint_passes.append(endpoint_pass)
        endpoints[feature] = {
            "registered_direction": "RETRY_ONLY_HIGHER_THAN_COMPENSATION_ONLY",
            "rank_probability_retry_greater": probability,
            "retry_only_mean": statistics.fmean(positive) if positive else None,
            "compensation_only_mean": statistics.fmean(negative) if negative else None,
            "bootstrap_ci95": (
                _bootstrap_rank_ci(
                    positive, negative,
                    seed=int(config["bootstrap"]["seed"]) + index,
                    resamples=int(config["bootstrap"]["resamples"]),
                ) if positive and negative else None
            ),
            "passed": endpoint_pass,
        }
    gate = config["replication_gate"]
    integrity = {
        "operational_cases": int(status["operational_cases"]) >= int(gate["operational_cases_minimum"]),
        "retry_only_cases": len(retry) >= int(gate["retry_only_cases_minimum"]),
        "compensation_only_cases": len(compensation) >= int(gate["compensation_only_cases_minimum"]),
        "zero_chronology_violations": int(status["chronology_violations"]) == 0,
        "zero_oracle_leakage": int(status["oracle_leakage_events"]) == 0,
        "zero_budget_violations": int(status["budget_violations"]) == 0,
    }
    passed = all(integrity.values()) and all(endpoint_passes)
    summary = {
        "experiment_run_id": manifest["experiment_run_id"],
        "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"],
        "claim_scope": config["claim_scope"],
        "initial_units": int(status["initial_units"]),
        "operational_cases": int(status["operational_cases"]),
        "outcome_partitions": dict(sorted(partitions.items())),
        "exclusive_recovery_cases": len(exclusive_rows),
        "retry_only_cases": len(retry),
        "compensation_only_cases": len(compensation),
        "registered_endpoints": endpoints,
        "integrity_and_population_checks": integrity,
        "replication_gate_passed": passed,
        "selector_fitting_authorized": passed,
        "validation_authorized": False,
        "threshold_fitted": False,
        "api_calls": 0,
    }
    (run_dir / "replication_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (run_dir / "exclusive_recovery_cases.csv").open("w", encoding="utf-8", newline="") as handle:
        if exclusive_rows:
            writer = csv.DictWriter(handle, fieldnames=list(exclusive_rows[0]))
            writer.writeheader()
            writer.writerows(exclusive_rows)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = analyze(args.run_dir.resolve())
        print(json.dumps(summary, indent=2))
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
