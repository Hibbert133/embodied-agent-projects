"""Audit inferred corrections against hidden single-axis fault labels."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-csv", type=Path, nargs="+", required=True)
    parser.add_argument("--audit-jsonl", type=Path, nargs="+", required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--summary-csv", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if len(args.trial_csv) != len(args.audit_jsonl):
        raise ValueError("trial CSV and audit JSONL lists must have equal length")
    output_rows: list[dict[str, object]] = []
    for trial_path, audit_path in zip(args.trial_csv, args.audit_jsonl):
        with trial_path.open(encoding="utf-8", newline="") as file:
            trials = list(csv.DictReader(file))
        audits = [
            json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        audit_by_key = {(int(row["seed"]), int(row["trial"])): row for row in audits}
        for row in trials:
            if int(row["trial"]) <= 1:
                continue
            key = (int(row["seed"]), int(row["trial"]))
            audit = audit_by_key[key]
            proposal = audit["proposal"]
            expected_direction = (
                "negative" if row["injected_bias_sign"] == "positive" else "positive"
            )
            output_rows.append(
                {
                    "seed": row["seed"],
                    "fault_axis": row["injected_bias_axis"],
                    "fault_sign": row["injected_bias_sign"],
                    "fault_magnitude": row["injected_bias_magnitude"],
                    "correction_axis": proposal["correction_axis"],
                    "correction_direction": proposal["correction_direction"],
                    "correction_magnitude": proposal["correction_magnitude"],
                    "magnitude_absolute_error": abs(
                        float(proposal["correction_magnitude"])
                        - float(row["injected_bias_magnitude"])
                    ),
                    "axis_correct": proposal["correction_axis"] == row["injected_bias_axis"],
                    "direction_correct": proposal["correction_direction"] == expected_direction,
                    "recovery_success": row["success"],
                }
            )
    if not output_rows:
        raise ValueError("no recovery proposals found")
    output = args.output_csv.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    axis_correct = sum(bool(row["axis_correct"]) for row in output_rows)
    direction_correct = sum(bool(row["direction_correct"]) for row in output_rows)
    print(f"axis correct: {axis_correct}/{len(output_rows)}")
    print(f"direction correct: {direction_correct}/{len(output_rows)}")
    print(f"summary: {output}")
    if args.summary_csv is not None:
        groups: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in output_rows:
            key = f"{row['fault_axis']}_{row['fault_sign']}_{float(row['fault_magnitude']):g}"
            groups[key].append(row)
            groups["all"].append(row)
        summaries: list[dict[str, object]] = []
        for condition, group in sorted(groups.items()):
            successes = sum(str(row["recovery_success"]).lower() == "true" for row in group)
            rate = successes / len(group)
            z = 1.959963984540054
            denominator = 1.0 + z * z / len(group)
            center = (rate + z * z / (2 * len(group))) / denominator
            margin = z * math.sqrt(
                rate * (1 - rate) / len(group) + z * z / (4 * len(group) ** 2)
            ) / denominator
            summaries.append(
                {
                    "condition": condition,
                    "recovery_cases": len(group),
                    "axis_correct": sum(bool(row["axis_correct"]) for row in group),
                    "direction_correct": sum(bool(row["direction_correct"]) for row in group),
                    "recovery_successes": successes,
                    "recovery_rate": rate,
                    "recovery_wilson_low": center - margin,
                    "recovery_wilson_high": center + margin,
                    "mean_magnitude_absolute_error": mean(
                        float(row["magnitude_absolute_error"]) for row in group
                    ),
                }
            )
        summary_output = args.summary_csv.expanduser().resolve()
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        with summary_output.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(summaries[0]))
            writer.writeheader()
            writer.writerows(summaries)
        print(f"aggregate summary: {summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
