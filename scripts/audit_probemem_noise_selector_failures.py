"""Audit why the frozen ProbeMem noise selector failed its promotion gate.

This is a post-hoc descriptive audit. It does not fit features, thresholds, or
policies and does not execute new environment or API interactions.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
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


def classify_decision_effect(
    selected_skill: str,
    baseline_skill: str,
    selected_accepted: bool,
    baseline_accepted: bool,
) -> str:
    if selected_skill == baseline_skill:
        return "NO_DECISION_CHANGE"
    if selected_accepted and not baseline_accepted:
        return "HELPFUL_CHANGE"
    if baseline_accepted and not selected_accepted:
        return "HARMFUL_CHANGE"
    return "NEUTRAL_CHANGE"


def build_causal_audit_rows(
    selector_rows: list[dict[str, str]],
    feature_rows: list[dict[str, Any]],
    candidate_pairs: Mapping[int, Mapping[str, Mapping[str, str]]],
) -> list[dict[str, Any]]:
    features = {int(row["episode_id"]): row for row in feature_rows}
    audit: list[dict[str, Any]] = []
    for row in selector_rows:
        episode_id = int(row["episode_id"])
        selected = row["selected_skill"]
        pair = candidate_pairs[episode_id]
        selected_ok = row["selected_accepted"].lower() == "true"
        retry_ok = row["always_retry_accepted"].lower() == "true"
        compensation_ok = row["always_compensation_accepted"].lower() == "true"
        feature = features[episode_id]
        threshold = float(row["frozen_threshold"])
        relative_std = float(row["probe_relative_bias_std"])
        audit.append(
            {
                "experiment_run_id": row["experiment_run_id"],
                "manifest_id": row["manifest_id"],
                "episode_id": episode_id,
                "seed": int(row["seed"]),
                "selected_skill": selected,
                "selected_accepted": selected_ok,
                "effect_vs_always_retry": classify_decision_effect(
                    selected, RETRY, selected_ok, retry_ok
                ),
                "effect_vs_always_compensation": classify_decision_effect(
                    selected, COMPENSATION, selected_ok, compensation_ok
                ),
                "outcome_partition_evaluator_only": row[
                    "outcome_partition_evaluator_only"
                ],
                "probe_relative_bias_std": relative_std,
                "frozen_threshold": threshold,
                "absolute_threshold_margin": abs(relative_std - threshold),
                "compensation_status_evaluator_only": pair[COMPENSATION][
                    "verification_status"
                ],
                "compensation_steps_evaluator_only": int(
                    pair[COMPENSATION]["verification_steps"]
                ),
                "compensation_final_distance_evaluator_only": float(
                    pair[COMPENSATION]["final_object_goal_distance"]
                ),
                "retry_status_evaluator_only": pair[RETRY]["verification_status"],
                "retry_steps_evaluator_only": int(pair[RETRY]["verification_steps"]),
                "retry_final_distance_evaluator_only": float(
                    pair[RETRY]["final_object_goal_distance"]
                ),
                **{
                    f"agent_feature_{name}": value
                    for name, value in feature.items()
                    if name
                    not in {
                        "experiment_run_id",
                        "manifest_id",
                        "episode_id",
                        "seed",
                        "outcome_partition_evaluator_only",
                        "compensation_status_evaluator_only",
                        "retry_status_evaluator_only",
                    }
                },
            }
        )
    return audit


def summarize_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    decisive = [
        row
        for row in rows
        if row["outcome_partition_evaluator_only"]
        in {"RETRY_ONLY_RECOVERY", "COMPENSATION_ONLY_RECOVERY"}
    ]
    correct = [row for row in decisive if bool(row["selected_accepted"])]
    errors = [row for row in decisive if not bool(row["selected_accepted"])]
    return {
        "operational_cases": len(rows),
        "decisive_cases": len(decisive),
        "decisive_selector_correct": len(correct),
        "decisive_selector_errors": len(errors),
        "effect_vs_always_retry": dict(
            Counter(row["effect_vs_always_retry"] for row in rows)
        ),
        "effect_vs_always_compensation": dict(
            Counter(row["effect_vs_always_compensation"] for row in rows)
        ),
        "error_seeds": [int(row["seed"]) for row in errors],
        "error_threshold_margins": {
            str(row["seed"]): float(row["absolute_threshold_margin"])
            for row in errors
        },
        "posthoc_only": True,
        "selector_or_threshold_refit": False,
        "new_environment_rollouts": 0,
        "api_calls": 0,
        "principles_generated": 0,
        "phase_d_promoted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--selector-results",
        type=Path,
        default=ROOT / "outputs/probemem_v2/noise_selector_validation_results.csv",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=ROOT / "outputs/probemem_v2/noise_selector_causal_audit.csv",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=ROOT / "outputs/probemem_v2/noise_selector_causal_audit_summary.json",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "reports/probemem_v2_noise_selector_causal_audit.md",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        if status.get("status") != "COMPLETED":
            raise ValueError("causal audit requires a completed immutable run")
        selector_rows = _read_csv(args.selector_results.resolve())
        if {row["manifest_id"] for row in selector_rows} != {manifest["manifest_id"]}:
            raise ValueError("selector results do not match the immutable manifest")
        candidates = _read_csv(run_dir / "candidate_results.csv")
        partitions, pairs = build_outcome_partitions(candidates)
        feature_rows = build_feature_audit(
            _read_jsonl(run_dir / "agent_evidence.jsonl"), partitions, pairs
        )
        rows = build_causal_audit_rows(selector_rows, feature_rows, pairs)
        summary = summarize_audit(rows)
        summary.update(
            {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"],
            }
        )
        _write_csv(args.output_csv.resolve(), rows)
        args.output_summary.resolve().write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        report = [
            "# ProbeMem Frozen Selector Causal Audit",
            "",
            f"Run: `{manifest['experiment_run_id']}`",
            f"Manifest: `{manifest['manifest_id']}`",
            "",
            "## Result",
            "",
            f"Among {summary['decisive_cases']} exclusive-recovery cases, the frozen selector chose the accepted skill in {summary['decisive_selector_correct']} and failed in {summary['decisive_selector_errors']}.",
            f"Error seeds were {summary['error_seeds']}, with absolute threshold margins {summary['error_threshold_margins']}.",
            "",
            "The errors are not confined to a narrow threshold boundary. Low relative probe variation contains both retry-only and compensation-only recoveries, while one extreme high-variation case is retry-only. The observed intervention utility is therefore non-monotonic in this single feature.",
            "",
            "## Claim boundary",
            "",
            "This audit is descriptive and post-hoc. It executed no rollout or API call, fit no threshold or selector, generated no principle, and does not unblock Phase D. It motivates testing whether additional Agent-visible state or explicit verification-grounded surprise is necessary.",
        ]
        args.output_report.resolve().write_text("\n".join(report) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
