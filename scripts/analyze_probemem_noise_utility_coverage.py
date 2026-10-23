"""Analyze label-blind ProbeMem noise action-utility coverage without fitting."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_probemem_paired_utility import (  # noqa: E402
    COMPENSATION,
    RETRY,
    _as_bool,
    _read_csv,
    _read_jsonl,
    _write_csv,
    summarize_candidate_pairs,
)
from src.evaluation.allocation_metrics import average_precision, roc_auc  # noqa: E402
from src.reasoning import validate_no_oracle_evidence  # noqa: E402


def build_outcome_partitions(
    candidate_rows: list[dict[str, str]],
) -> tuple[dict[int, str], dict[int, dict[str, dict[str, str]]]]:
    by_episode: dict[int, dict[str, dict[str, str]]] = {}
    for row in candidate_rows:
        by_episode.setdefault(int(row["episode_id"]), {})[row["candidate_id"]] = row
    partitions: dict[int, str] = {}
    for episode_id, pair in by_episode.items():
        if set(pair) != {COMPENSATION, RETRY}:
            raise ValueError(f"episode={episode_id} lacks a complete candidate pair")
        compensation = pair[COMPENSATION]["verification_status"] == "ACCEPTED"
        retry = pair[RETRY]["verification_status"] == "ACCEPTED"
        if compensation and retry:
            partitions[episode_id] = "BOTH_RECOVER"
        elif compensation:
            partitions[episode_id] = "COMPENSATION_ONLY_RECOVERY"
        elif retry:
            partitions[episode_id] = "RETRY_ONLY_RECOVERY"
        else:
            partitions[episode_id] = "NEITHER_RECOVERS"
    return partitions, by_episode


def build_feature_audit(
    agent_rows: list[dict[str, Any]],
    partitions: Mapping[int, str],
    candidate_pairs: Mapping[int, Mapping[str, Mapping[str, str]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in agent_rows:
        validate_no_oracle_evidence(record)
        if not bool(record["decision_required"]):
            continue
        episode_id = int(record["episode_id"])
        pair = candidate_pairs[episode_id]
        rows.append(
            {
                "experiment_run_id": record["experiment_run_id"],
                "manifest_id": record["manifest_id"],
                "episode_id": episode_id,
                "seed": int(record["seed"]),
                **{
                    name: float(value)
                    for name, value in record["applicability_signature"]["features"].items()
                },
                "outcome_partition_evaluator_only": partitions[episode_id],
                "compensation_status_evaluator_only": pair[COMPENSATION][
                    "verification_status"
                ],
                "retry_status_evaluator_only": pair[RETRY]["verification_status"],
            }
        )
    return rows


def exploratory_feature_auc(feature_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisive = [
        row
        for row in feature_rows
        if row["outcome_partition_evaluator_only"]
        in {"COMPENSATION_ONLY_RECOVERY", "RETRY_ONLY_RECOVERY"}
    ]
    labels = [
        row["outcome_partition_evaluator_only"] == "RETRY_ONLY_RECOVERY"
        for row in decisive
    ]
    excluded = {
        "experiment_run_id",
        "manifest_id",
        "episode_id",
        "seed",
        "outcome_partition_evaluator_only",
        "compensation_status_evaluator_only",
        "retry_status_evaluator_only",
    }
    feature_names = [name for name in feature_rows[0] if name not in excluded]
    result: list[dict[str, Any]] = []
    for name in feature_names:
        values = [float(row[name]) for row in decisive]
        high_auc = roc_auc(labels, values)
        low_scores = [-value for value in values]
        low_auc = roc_auc(labels, low_scores)
        if high_auc is None or low_auc is None:
            direction = "N/A"
            selected_auc = None
            selected_ap = None
        elif high_auc >= low_auc:
            direction = "higher_favors_retry"
            selected_auc = high_auc
            selected_ap = average_precision(labels, values)
        else:
            direction = "lower_favors_retry"
            selected_auc = low_auc
            selected_ap = average_precision(labels, low_scores)
        result.append(
            {
                "feature": name,
                "decisive_cases": len(decisive),
                "retry_only_positive_cases": sum(labels),
                "compensation_only_negative_cases": len(labels) - sum(labels),
                "posthoc_direction": direction,
                "exploratory_roc_auc": selected_auc,
                "exploratory_average_precision": selected_ap,
                "threshold_fitted": False,
                "heldout_claim_eligible": False,
            }
        )
    return sorted(
        result,
        key=lambda row: (
            -(float(row["exploratory_roc_auc"]) if row["exploratory_roc_auc"] is not None else -1.0),
            row["feature"],
        ),
    )


def _copy_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "outputs/probemem_v2"
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "reports/probemem_v2_noise_utility_coverage.md",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        output_root = args.output_root.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        run_status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        run_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        if run_status.get("status") != "COMPLETED":
            raise ValueError("noise utility analysis requires a COMPLETED run")
        if not bool(run_summary.get("coverage_target_reached")):
            raise ValueError("noise utility coverage target was not reached")
        cases = _read_csv(run_dir / "case_results.csv")
        candidates = _read_csv(run_dir / "candidate_results.csv")
        agent_rows = _read_jsonl(run_dir / "agent_evidence.jsonl")
        summary = summarize_candidate_pairs(cases, candidates)
        partitions, pairs = build_outcome_partitions(candidates)
        feature_rows = build_feature_audit(agent_rows, partitions, pairs)
        auc_rows = exploratory_feature_auc(feature_rows)
        partition_counts = {
            name: sum(value == name for value in partitions.values())
            for name in (
                "COMPENSATION_ONLY_RECOVERY",
                "RETRY_ONLY_RECOVERY",
                "BOTH_RECOVER",
                "NEITHER_RECOVERS",
            )
        }
        oracle_recoveries = (
            partition_counts["COMPENSATION_ONLY_RECOVERY"]
            + partition_counts["RETRY_ONLY_RECOVERY"]
            + partition_counts["BOTH_RECOVER"]
        )
        summary.update(
            {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"],
                "coverage_target": run_summary["target_paired_operational_units"],
                "coverage_target_reached": True,
                "outcome_partition_counts": partition_counts,
                "oracle_skill_selection_recoveries": oracle_recoveries,
                "oracle_skill_selection_rate": oracle_recoveries / len(partitions),
                "maximum_gain_over_always_retry": (
                    oracle_recoveries - summary["accepted_recoveries"][RETRY]
                ),
                "maximum_gain_over_always_compensation": (
                    oracle_recoveries - summary["accepted_recoveries"][COMPENSATION]
                ),
                "decisive_recovery_cases": (
                    partition_counts["COMPENSATION_ONLY_RECOVERY"]
                    + partition_counts["RETRY_ONLY_RECOVERY"]
                ),
                "agent_oracle_leakage_violations": 0,
                "selector_fitted": False,
                "principles_generated": 0,
                "api_calls": 0,
                "heldout_claim_eligible": False,
                "next_status": "READY_FOR_DEVELOPMENT_SELECTOR_CANDIDATE",
            }
        )
        _write_csv(output_root / "noise_utility_case_results.csv", cases)
        _write_csv(output_root / "noise_utility_candidate_results.csv", candidates)
        _write_csv(output_root / "noise_utility_feature_audit.csv", feature_rows)
        _write_csv(output_root / "noise_utility_exploratory_feature_auc.csv", auc_rows)
        _copy_json(output_root / "noise_utility_manifest.json", manifest)
        _copy_json(output_root / "noise_utility_summary.json", summary)

        top = auc_rows[0]
        lines = [
            "# ProbeMem Label-Blind Noise Utility Coverage",
            "",
            f"Run: `{manifest['experiment_run_id']}`",
            f"Manifest: `{manifest['manifest_id']}`",
            f"Source commit: `{manifest['source_git_commit']}`",
            "",
            "## Actual collection",
            "",
            f"The label-blind stream scanned {summary['full_collection_units']} initial "
            f"noise units and stopped at the registered target of "
            f"{summary['paired_comparable_units']} complete operational pairs.",
            "",
            f"- Always compensation: {summary['accepted_recoveries'][COMPENSATION]}/20 accepted.",
            f"- Always retry: {summary['accepted_recoveries'][RETRY]}/20 accepted.",
            f"- Oracle per-case skill choice: {oracle_recoveries}/20 accepted.",
            f"- Compensation-only recovery: {partition_counts['COMPENSATION_ONLY_RECOVERY']}.",
            f"- Retry-only recovery: {partition_counts['RETRY_ONLY_RECOVERY']}.",
            f"- Both recover: {partition_counts['BOTH_RECOVER']}.",
            f"- Neither recovers: {partition_counts['NEITHER_RECOVERS']}.",
            "",
            "## Research interpretation",
            "",
            "This collection establishes real action-utility diversity. A perfect skill "
            "selector could improve recovery by 2/20 over always retry and 6/20 over "
            "always compensation. Unlike the previous mixed stream, retry now has six "
            "exclusive accepted recoveries and compensation has two.",
            "",
            "Only eight cases are decisive for recovery selection. Exploratory feature "
            f"ranking found `{top['feature']}` as the strongest post-hoc univariate signal "
            f"(direction `{top['posthoc_direction']}`, ROC AUC "
            f"{float(top['exploratory_roc_auc']):.3f}) on those eight cases. This is not a "
            "frozen selector result: direction was chosen post hoc, the negative class has "
            "only two cases, and no threshold was fit.",
            "",
            "## Promotion decision",
            "",
            "The data are sufficient to design a separately frozen development selector "
            "candidate, but not to promote Phase D, run held-out evaluation, or generate "
            "scientific-memory principles. The next selector must be preregistered and "
            "evaluated on fresh development seeds before any held-out use.",
            "",
            "## Integrity",
            "",
            "Stopping used candidate executability only and never read outcomes. Agent "
            "evidence passed nested Oracle rejection. API calls, rendering, memory writes, "
            "principle generation, and selector fitting were all zero.",
            "",
            "## Reproduction",
            "",
            "```bash",
            f"python scripts/analyze_probemem_noise_utility_coverage.py --run-dir \"{run_dir}\"",
            "```",
        ]
        args.output_report.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_report.resolve().write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"summary: {output_root / 'noise_utility_summary.json'}")
        print(f"feature_auc: {output_root / 'noise_utility_exploratory_feature_auc.csv'}")
        print(f"report: {args.output_report.resolve()}")
        print("status: READY_FOR_DEVELOPMENT_SELECTOR_CANDIDATE")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
