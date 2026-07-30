"""Analyze paired active-evidence outcomes and select a development threshold."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--frozen-threshold", type=float)
    return parser.parse_args()


def load_ledger(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def split_job_id(job_id: str) -> tuple[str, str]:
    prefix, separator, method = job_id.rpartition("__")
    if not separator or not prefix or not method:
        raise ValueError(f"invalid campaign job ID: {job_id}")
    return prefix, method


def select_development_threshold(
    passive: Mapping[str, Mapping[str, Any]],
    probed: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Choose success first, then minimum real environment cost on development cases."""

    if set(passive) != set(probed) or not passive:
        raise ValueError("paired passive and probed outcomes are required")
    uncertainty_values = sorted(
        {float(row["metrics"]["uncertainty"]) for row in passive.values()}
    )
    candidates = [
        uncertainty_values[0] - 1e-12,
        *[
            (lower + upper) / 2.0
            for lower, upper in zip(uncertainty_values, uncertainty_values[1:])
        ],
        uncertainty_values[-1] + 1e-12,
    ]
    evaluated = []
    for threshold in candidates:
        selected = []
        requested = 0
        for key in sorted(passive):
            uncertainty = float(passive[key]["metrics"]["uncertainty"])
            use_probe = uncertainty >= threshold
            requested += int(use_probe)
            selected.append(probed[key] if use_probe else passive[key])
        successes = sum(bool(row["success"]) for row in selected)
        mean_steps = mean(int(row["environment_steps"]) for row in selected)
        evaluated.append((successes, mean_steps, requested, threshold))
    successes, mean_steps, requested, threshold = min(
        evaluated,
        key=lambda row: (-row[0], row[1], row[2], -row[3]),
    )
    return {
        "threshold": threshold,
        "development_cases": len(passive),
        "development_successes": successes,
        "development_success_rate": successes / len(passive),
        "development_mean_environment_steps": mean_steps,
        "development_probe_requests": requested,
        "selection_rule": (
            "maximize paired verification successes, then minimize mean real "
            "environment steps, then probe requests; development split only"
        ),
    }


def evaluate_frozen_threshold(
    passive: Mapping[str, Mapping[str, Any]],
    gated: Mapping[str, Mapping[str, Any]],
    *,
    threshold: float,
) -> dict[str, Any]:
    if set(passive) != set(gated) or not passive:
        raise ValueError("paired passive and gated outcomes are required")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("frozen threshold must be in [0, 1]")
    matches = 0
    for key in passive:
        expected = float(passive[key]["metrics"]["uncertainty"]) >= threshold
        actual = bool(gated[key]["metrics"].get("probe_requested"))
        matches += int(expected == actual)
    outcomes = list(gated.values())
    passive_outcomes = list(passive.values())
    probes = sum(bool(row["metrics"].get("probe_requested")) for row in outcomes)
    return {
        "threshold": threshold,
        "heldout_retuning": False,
        "cases": len(outcomes),
        "decision_rule_matches": matches,
        "probe_requests": probes,
        "probe_request_rate": probes / len(outcomes),
        "verification_successes": sum(bool(row["success"]) for row in outcomes),
        "verification_success_rate": sum(bool(row["success"]) for row in outcomes) / len(outcomes),
        "passive_successes": sum(bool(row["success"]) for row in passive_outcomes),
        "success_gain_over_passive": (
            sum(bool(row["success"]) for row in outcomes)
            - sum(bool(row["success"]) for row in passive_outcomes)
        ),
        "mean_environment_steps": mean(int(row["environment_steps"]) for row in outcomes),
        "passive_mean_environment_steps": mean(
            int(row["environment_steps"]) for row in passive_outcomes
        ),
    }


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    rows = load_ledger(run_dir / "run_ledger.jsonl")
    grouped: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        key, method = split_job_id(str(row["job_id"]))
        grouped.setdefault(method, {})[key] = row
    passive = grouped.get("passive", {})
    always = grouped.get("always_probe", {})
    threshold = (
        evaluate_frozen_threshold(
            passive, grouped.get("uncertainty_gated", {}),
            threshold=args.frozen_threshold,
        )
        if args.frozen_threshold is not None
        else select_development_threshold(passive, always)
    )

    method_rows = []
    for method in sorted(grouped):
        outcomes = list(grouped[method].values())
        probes = [row for row in outcomes if row["metrics"].get("probe_requested")]
        paired_passive_failures = sum(
            not bool(passive[key]["success"])
            for key, row in grouped[method].items()
            if row["metrics"].get("probe_requested") and key in passive
        )
        method_rows.append(
            {
                "method": method,
                "cases": len(outcomes),
                "successes": sum(bool(row["success"]) for row in outcomes),
                "success_rate": sum(bool(row["success"]) for row in outcomes) / len(outcomes),
                "probe_requests": len(probes),
                "probe_request_rate": len(probes) / len(outcomes),
                "probes_on_paired_passive_failures": paired_passive_failures,
                "probe_relevance_precision": (
                    paired_passive_failures / len(probes) if probes else ""
                ),
                "mean_environment_steps": mean(int(row["environment_steps"]) for row in outcomes),
                "api_calls": sum(int(row["api_calls"]) for row in outcomes),
            }
        )
    atomic_csv(run_dir / "paired_method_analysis.csv", method_rows)
    artifact = (
        "frozen_threshold_evaluation.json"
        if args.frozen_threshold is not None
        else "development_threshold_selection.json"
    )
    atomic_json(run_dir / artifact, threshold)
    print(json.dumps(threshold, indent=2))
    print(f"analysis: {run_dir / 'paired_method_analysis.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
