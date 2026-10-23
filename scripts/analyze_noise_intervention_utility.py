"""Analyze preregistered Agent-visible scores without fitting a selector."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation import average_precision, roc_auc  # noqa: E402


RETRY = "stochastic_retry"
FEATURES = (
    "phase_inconsistency",
    "temporal_uncertainty",
    "probe_score",
    "probe_relative_bias_std",
    "probe_mean_estimation_residual",
    "probe_sign_disagreement",
)


def analyze_feature_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparable = [
        row
        for row in rows
        if str(row.get("paired_comparable", "")).lower() == "true"
        and "," not in str(row.get("best_candidate_ids", ""))
    ]
    labels = [str(row["best_candidate_ids"]) == RETRY for row in comparable]
    positives = sum(labels)
    negatives = len(labels) - positives
    features: dict[str, Any] = {}
    for feature in FEATURES:
        scores = [float(row[feature]) for row in comparable]
        positive_scores = [score for score, label in zip(scores, labels) if label]
        negative_scores = [score for score, label in zip(scores, labels) if not label]
        features[feature] = {
            "registered_direction": "higher predicts retry preference",
            "retry_preferred_median": median(positive_scores) if positive_scores else None,
            "compensation_preferred_median": (
                median(negative_scores) if negative_scores else None
            ),
            "roc_auc": roc_auc(labels, scores),
            "pr_auc": average_precision(labels, scores),
        }
    return {
        "paired_comparable_units": len(comparable),
        "retry_preferred_units": positives,
        "compensation_preferred_units": negatives,
        "retry_prevalence": positives / len(labels) if labels else None,
        "status": (
            "COMPLETE_FOR_FEATURE_CHARACTERIZATION"
            if positives and negatives
            else "INCOMPLETE_SINGLE_CLASS_LABEL"
        ),
        "threshold_fitted": False,
        "features": features,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run = args.run_dir.resolve()
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        with (run / "case_results.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        analysis = {
            "experiment_run_id": manifest["experiment_run_id"],
            "source_git_commit": manifest["source_git_commit"],
            "config_sha256": manifest["config_sha256"],
            **analyze_feature_rows(rows),
        }
        output = run / "feature_analysis.json"
        output.write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
        print(
            f"status={analysis['status']} comparable={analysis['paired_comparable_units']} "
            f"retry_preferred={analysis['retry_preferred_units']}"
        )
        print(f"analysis: {output}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
