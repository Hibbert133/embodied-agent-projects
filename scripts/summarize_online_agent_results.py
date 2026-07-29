"""Summarize a completed online-agent run from raw CSV and audit JSONL."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-csv", type=Path, required=True)
    parser.add_argument("--audit-jsonl", type=Path, required=True)
    parser.add_argument("--method", required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser.parse_args()


def as_bool(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def main() -> int:
    args = parse_args()
    with args.results_csv.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    audits = [
        json.loads(line) for line in args.audit_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("results CSV is empty")
    failures = [row for row in rows if not as_bool(row["initial_success"])]
    recovered = sum(as_bool(row["recovery_success"]) for row in failures)
    summary = {
        "method": args.method,
        "episodes": len(rows),
        "initial_failures": len(failures),
        "recovered": recovered,
        "conditional_recovery_rate": recovered / len(failures) if failures else 0.0,
        "mean_total_recovery_environment_steps": mean(
            float(row["total_recovery_environment_steps"]) for row in failures
        ) if failures else 0.0,
        "mean_final_object_goal_distance": mean(
            float(row["final_object_goal_distance"]) for row in failures
        ) if failures else 0.0,
        "mean_api_latency_ms": mean(
            float(row["request_audit"]["latency_ms"]) for row in audits
        ) if audits else 0.0,
        "total_input_tokens": sum(
            int(row["request_audit"]["usage"].get("input_tokens", 0)) for row in audits
        ),
        "total_output_tokens": sum(
            int(row["request_audit"]["usage"].get("output_tokens", 0)) for row in audits
        ),
    }
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary))
        writer.writeheader()
        writer.writerow(summary)
    print(json.dumps(summary, indent=2))
    print(f"summary: {args.output_csv.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
