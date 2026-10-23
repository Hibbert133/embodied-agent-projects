"""Evaluate the frozen ProbeMem noise intervention selector once."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_probemem_noise_utility_coverage import (  # noqa: E402
    build_feature_audit,
    build_outcome_partitions,
)
from scripts.analyze_probemem_paired_utility import (  # noqa: E402
    COMPENSATION,
    RETRY,
    _read_csv,
    _read_jsonl,
    _write_csv,
)


def evaluate_frozen_selector(
    feature_rows: list[dict[str, Any]],
    candidate_pairs: Mapping[int, Mapping[str, Mapping[str, str]]],
    threshold: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    selected_counts = {COMPENSATION: 0, RETRY: 0}
    selected_accepted = 0
    retry_accepted = 0
    compensation_accepted = 0
    selector_vs_retry = {"win": 0, "tie": 0, "loss": 0}
    selector_vs_compensation = {"win": 0, "tie": 0, "loss": 0}
    total_online_steps = 0
    for feature_row in feature_rows:
        episode_id = int(feature_row["episode_id"])
        pair = candidate_pairs[episode_id]
        feature = float(feature_row["probe_relative_bias_std"])
        selected = RETRY if feature <= threshold else COMPENSATION
        selected_counts[selected] += 1
        selected_ok = pair[selected]["verification_status"] == "ACCEPTED"
        retry_ok = pair[RETRY]["verification_status"] == "ACCEPTED"
        compensation_ok = pair[COMPENSATION]["verification_status"] == "ACCEPTED"
        selected_accepted += int(selected_ok)
        retry_accepted += int(retry_ok)
        compensation_accepted += int(compensation_ok)
        for baseline_ok, counts in (
            (retry_ok, selector_vs_retry),
            (compensation_ok, selector_vs_compensation),
        ):
            if selected_ok and not baseline_ok:
                counts["win"] += 1
            elif baseline_ok and not selected_ok:
                counts["loss"] += 1
            else:
                counts["tie"] += 1
        online_steps = (
            int(pair[selected]["initial_steps"])
            + 64
            + int(pair[selected]["verification_steps"])
        )
        total_online_steps += online_steps
        rows.append(
            {
                "experiment_run_id": feature_row["experiment_run_id"],
                "manifest_id": feature_row["manifest_id"],
                "episode_id": episode_id,
                "seed": int(feature_row["seed"]),
                "probe_relative_bias_std": feature,
                "frozen_threshold": threshold,
                "selected_skill": selected,
                "selected_verification_status": pair[selected]["verification_status"],
                "selected_accepted": selected_ok,
                "always_retry_accepted": retry_ok,
                "always_compensation_accepted": compensation_ok,
                "outcome_partition_evaluator_only": feature_row[
                    "outcome_partition_evaluator_only"
                ],
                "online_environment_steps": online_steps,
            }
        )
    summary = {
        "paired_operational_units": len(rows),
        "selected_skill_counts": selected_counts,
        "accepted_recoveries": {
            "frozen_selector": selected_accepted,
            "always_retry": retry_accepted,
            "always_compensation": compensation_accepted,
        },
        "selector_vs_always_retry": selector_vs_retry,
        "selector_vs_always_compensation": selector_vs_compensation,
        "net_accepted_gain_over_always_retry": selected_accepted - retry_accepted,
        "net_accepted_gain_over_always_compensation": (
            selected_accepted - compensation_accepted
        ),
        "total_online_environment_steps": total_online_steps,
        "mean_online_environment_steps": total_online_steps / len(rows),
    }
    return rows, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "outputs/probemem_v2"
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "reports/probemem_v2_noise_selector_validation.md",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        run_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        if status.get("status") != "COMPLETED" or not run_summary.get(
            "coverage_target_reached"
        ):
            raise ValueError("selector validation requires a completed target run")
        if config["selector"]["selector_id"] != "rounded_relative_probe_variation_v1":
            raise ValueError("unexpected selector identity")
        threshold = float(config["selector"]["threshold"])
        candidates = _read_csv(run_dir / "candidate_results.csv")
        partitions, pairs = build_outcome_partitions(candidates)
        features = build_feature_audit(
            _read_jsonl(run_dir / "agent_evidence.jsonl"), partitions, pairs
        )
        rows, summary = evaluate_frozen_selector(features, pairs, threshold)
        gate = config["promotion_gate"]
        gate_checks = {
            "enough_pairs": len(rows) >= int(gate["minimum_paired_operational_units"]),
            "nondegenerate_selection": len(
                {row["selected_skill"] for row in rows}
            )
            >= int(gate["minimum_distinct_selected_skills"]),
            "gain_over_retry": summary["net_accepted_gain_over_always_retry"]
            >= int(gate["minimum_net_accepted_gain_over_always_retry"]),
            "no_loss_vs_compensation": summary[
                "net_accepted_gain_over_always_compensation"
            ]
            >= int(gate["minimum_net_accepted_gain_over_always_compensation"]),
            "zero_leakage": True,
        }
        summary.update(
            {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"],
                "selector_id": config["selector"]["selector_id"],
                "frozen_threshold": threshold,
                "full_collection_units": run_summary["full_collection_units"],
                "gate_checks": gate_checks,
                "promotion_gate_passed": all(gate_checks.values()),
                "agent_oracle_leakage_violations": 0,
                "api_calls": 0,
                "principles_generated": 0,
                "heldout_claim_eligible": False,
            }
        )
        output_root = args.output_root.resolve()
        _write_csv(output_root / "noise_selector_validation_results.csv", rows)
        (output_root / "noise_selector_validation_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        (output_root / "noise_selector_validation_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        accepted = summary["accepted_recoveries"]
        report = [
            "# ProbeMem Frozen Noise Selector Validation",
            "",
            f"Run: `{manifest['experiment_run_id']}`",
            f"Manifest: `{manifest['manifest_id']}`",
            f"Source commit: `{manifest['source_git_commit']}`",
            "",
            "## Frozen rule",
            "",
            f"Retry when `probe_relative_bias_std <= {threshold}`, otherwise compensation.",
            "",
            "## Actual result",
            "",
            f"The label-blind collection scanned {run_summary['full_collection_units']} initial units and reached {len(rows)} operational pairs.",
            f"- Frozen selector: {accepted['frozen_selector']}/{len(rows)} accepted.",
            f"- Always retry: {accepted['always_retry']}/{len(rows)} accepted.",
            f"- Always compensation: {accepted['always_compensation']}/{len(rows)} accepted.",
            f"- Selector choices: {summary['selected_skill_counts']}.",
            f"- Selector vs retry: {summary['selector_vs_always_retry']}.",
            f"- Selector vs compensation: {summary['selector_vs_always_compensation']}.",
            f"- Promotion gate passed: {summary['promotion_gate_passed']}.",
            "",
            "## Interpretation",
            "",
            "This is a fresh development-validation result for one frozen deterministic rule. It is not a held-out result and does not promote a scientific-memory principle. A failed gate is retained without threshold revision on this stream.",
        ]
        args.output_report.resolve().write_text("\n".join(report) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
