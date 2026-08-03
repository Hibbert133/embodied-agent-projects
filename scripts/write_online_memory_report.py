"""Write a claim-bounded ProbeMem-Online development report."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_online_memory import analyze  # noqa: E402


def build_report(summary: dict) -> str:
    methods = summary["methods"]
    rows = []
    for name, result in methods.items():
        rate = "N/A" if result["accepted_rate"] is None else f"{100 * result['accepted_rate']:.1f}%"
        rows.append(f"| {name} | {result['accepted']}/{result['cases']} | {rate} | {result['harmful_selections']} | {result['abstentions']} |")
    change = summary["full_vs_stateless_changes"]
    api = summary["api"]
    latency = api["latency_ms"]
    complete = summary["run_status"] == "COMPLETED" and summary["operational_cases"] == summary["target_operational_cases"]
    claim = (
        "This completed development run may be interpreted only according to the preregistered promotion gate."
        if complete else
        "The run is incomplete. All method differences below are descriptive and support no memory-benefit or GLM-performance claim."
    )
    return f"""# ProbeMem-Online Chronological Development Result

## Status

Run status: `{summary['run_status']}`

Operational cases: `{summary['operational_cases']}/{summary['target_operational_cases']}`

{claim}

## Recovery and harmful transfer

| Method | Accepted | Rate | Harmful selections | Abstentions |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

## Memory decision pathway

Relative to stateless GLM, the full resonance Agent changed the selected action
in {change['changed']} cases: {change['helpful']} helpful, {change['harmful']}
harmful, and {change['tie']} verification-status ties.

These counts require an actual registered-skill change. Changes in explanation,
confidence, or prediction without an action change are not counted as memory
benefit.

## Online model operation

* API calls: {api['calls']}
* Valid structured outputs: {api['valid']}
* Schema-repair calls: {api['repairs']}
* Median latency: {latency['median']} ms
* p90 latency: {latency['p90']} ms
* Maximum latency: {latency['max']} ms

API latency is reported separately from robot environment interaction.

## Integrity and claim boundary

Integrity counters: `{summary['integrity']}`

Promotion gate: `{summary['promotion_gate']}`

This development run does not establish validation, held-out generalization,
policy learning, VLA improvement, or cross-task transfer. Evaluator-only paired
outcomes are never written to operational memory.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = analyze(args.run_dir.resolve())
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(build_report(summary), encoding="utf-8")
    print(f"report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
