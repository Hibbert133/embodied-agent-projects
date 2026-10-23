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
        cost = "N/A" if result.get("total_environment_steps") is None else str(result["total_environment_steps"])
        rows.append(f"| {name} | {result['accepted']}/{result['cases']} | {rate} | {result['harmful_selections']} | {result['abstentions']} | {cost} |")
    change = summary["full_vs_stateless_changes"]
    paired = summary["full_vs_stateless_paired"]
    api = summary["api"]
    latency = api["latency_ms"]
    gate = summary["promotion_gate"]
    gate_rows = "\n".join(
        f"| {name} | {'PASS' if passed else 'FAIL'} |"
        for name, passed in gate.get("checks", {}).items()
    )
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

| Method | Accepted | Rate | Harmful selections | Abstentions | Total environment steps |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

## Memory decision pathway

Relative to stateless GLM, the full resonance Agent changed the selected action
in {change['changed']} cases: {change['helpful']} helpful, {change['harmful']}
harmful, and {change['tie']} verification-status ties.

These counts require an actual registered-skill change. Changes in explanation,
confidence, or prediction without an action change are not counted as memory
benefit.

Paired accepted-rate difference: {100 * paired['accepted_rate_difference']:.1f}
percentage points, paired bootstrap 95% CI
[{100 * paired['bootstrap_95_ci'][0]:.1f}, {100 * paired['bootstrap_95_ci'][1]:.1f}].
Status-utility win/tie/loss: {paired['wins']}/{paired['ties']}/{paired['losses']}.

## Online model operation

* API calls: {api['calls']}
* Valid structured outputs: {api['valid']}
* Valid final decisions: {api['final_decisions_valid']}/{api['expected_final_decisions']}
* Schema-repair calls: {api['repairs']}
* Input/output tokens: {api['input_tokens']} / {api['output_tokens']}
* Median latency: {latency['median'] / 1000:.1f} s
* p90 latency: {latency['p90'] / 1000:.1f} s
* Maximum latency: {latency['max'] / 1000:.1f} s

API latency is reported separately from robot environment interaction.

## Integrity and claim boundary

Integrity counters: `{summary['integrity']}`

## Promotion gate

Overall promotion: **{'PASS' if gate['passed'] else 'FAIL'}**

| Check | Result |
| --- | --- |
{gate_rows}

Diagnostics:

* Full accepted: {gate.get('diagnostics', {}).get('full_accepted', 'N/A')}
* Strongest deterministic accepted: {gate.get('diagnostics', {}).get('strongest_deterministic_accepted', 'N/A')}
* Net helpful changes: {gate.get('diagnostics', {}).get('net_helpful_changes', 'N/A')}
* Harmful-transfer reduction: {gate.get('diagnostics', {}).get('harmful_transfer_relative_reduction', 'N/A')}
* Full post-shift rate: {gate.get('diagnostics', {}).get('full_post_shift_rate', 'N/A')}
* Stateless post-shift rate: {gate.get('diagnostics', {}).get('stateless_post_shift_rate', 'N/A')}

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
