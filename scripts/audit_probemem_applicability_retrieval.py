"""Post-hoc nearest-reference audit of ProbeMem applicability signatures.

Historical paired outcomes are evaluator-only, so this script measures feature
separability and is not an actionable-memory implementation or online result.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_probemem_paired_utility import (  # noqa: E402
    COMPENSATION,
    RETRY,
    _read_csv,
    _write_csv,
)
from src.probemem.intervention_utility import (  # noqa: E402
    INTERVENTION_APPLICABILITY_FEATURES,
)


DECISIVE_LABEL_TO_SKILL = {
    "COMPENSATION_ONLY_RECOVERY": COMPENSATION,
    "RETRY_ONLY_RECOVERY": RETRY,
}


def fit_reference_scaler(
    rows: Sequence[Mapping[str, Any]], feature_names: Sequence[str]
) -> tuple[dict[str, float], dict[str, float]]:
    if len(rows) < 2:
        raise ValueError("reference scaler requires at least two rows")
    means: dict[str, float] = {}
    scales: dict[str, float] = {}
    for name in feature_names:
        values = [float(row[name]) for row in rows]
        means[name] = statistics.fmean(values)
        scale = statistics.pstdev(values)
        scales[name] = scale if scale > 1e-12 else 1.0
    return means, scales


def standardized_distance(
    query: Mapping[str, Any],
    reference: Mapping[str, Any],
    feature_names: Sequence[str],
    scales: Mapping[str, float],
) -> float:
    return math.sqrt(
        sum(
            ((float(query[name]) - float(reference[name])) / scales[name]) ** 2
            for name in feature_names
        )
        / len(feature_names)
    )


def retrieve_nearest_reference(
    query: Mapping[str, Any],
    references: Sequence[Mapping[str, Any]],
    feature_names: Sequence[str],
    scales: Mapping[str, float],
) -> tuple[Mapping[str, Any], float]:
    if not references:
        raise ValueError("retrieval requires at least one historical reference")
    ranked = sorted(
        (
            standardized_distance(query, reference, feature_names, scales),
            int(reference["seed"]),
            reference,
        )
        for reference in references
    )
    distance, _, reference = ranked[0]
    return reference, distance


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-csv",
        type=Path,
        default=ROOT / "outputs/probemem_v2/noise_utility_feature_audit.csv",
    )
    parser.add_argument(
        "--query-csv",
        type=Path,
        default=ROOT / "outputs/probemem_v2/noise_selector_causal_audit.csv",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=ROOT / "outputs/probemem_v2/applicability_retrieval_audit.csv",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=ROOT / "outputs/probemem_v2/applicability_retrieval_summary.json",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "reports/probemem_v2_applicability_retrieval_audit.md",
    )
    args = parser.parse_args()
    try:
        references_all = _read_csv(args.reference_csv.resolve())
        queries_all = _read_rows(args.query_csv.resolve())
        references = [
            row
            for row in references_all
            if row["outcome_partition_evaluator_only"] in DECISIVE_LABEL_TO_SKILL
        ]
        queries = [
            row
            for row in queries_all
            if row["outcome_partition_evaluator_only"] in DECISIVE_LABEL_TO_SKILL
        ]
        if not references or not queries:
            raise ValueError("retrieval audit requires decisive reference and query rows")
        if max(int(row["seed"]) for row in references) >= min(
            int(row["seed"]) for row in queries
        ):
            raise ValueError("retrieval chronology is invalid")
        reference_features = tuple(INTERVENTION_APPLICABILITY_FEATURES)
        query_features = tuple(f"agent_feature_{name}" for name in reference_features)
        means, scales = fit_reference_scaler(references, reference_features)
        audit_rows: list[dict[str, Any]] = []
        for query in queries:
            query_view = {
                name: query[prefixed]
                for name, prefixed in zip(reference_features, query_features)
            }
            reference, distance = retrieve_nearest_reference(
                query_view, references, reference_features, scales
            )
            predicted_skill = DECISIVE_LABEL_TO_SKILL[
                reference["outcome_partition_evaluator_only"]
            ]
            target_skill = DECISIVE_LABEL_TO_SKILL[
                query["outcome_partition_evaluator_only"]
            ]
            audit_rows.append(
                {
                    "query_experiment_run_id": query["experiment_run_id"],
                    "query_manifest_id": query["manifest_id"],
                    "query_episode_id": int(query["episode_id"]),
                    "query_seed": int(query["seed"]),
                    "reference_experiment_run_id": reference["experiment_run_id"],
                    "reference_manifest_id": reference["manifest_id"],
                    "reference_episode_id": int(reference["episode_id"]),
                    "reference_seed": int(reference["seed"]),
                    "standardized_distance": distance,
                    "retrieved_skill_evaluator_only": predicted_skill,
                    "target_skill_evaluator_only": target_skill,
                    "retrieval_correct_evaluator_only": predicted_skill == target_skill,
                    "frozen_selector_correct": query["selected_accepted"],
                    "reference_label_source": "paired_counterfactual_evaluator_only",
                    "actionable_memory_eligible": False,
                }
            )
        correct = sum(bool(row["retrieval_correct_evaluator_only"]) for row in audit_rows)
        frozen_correct = sum(
            str(row["frozen_selector_correct"]).lower() == "true"
            for row in audit_rows
        )
        confusion = Counter(
            f"{row['target_skill_evaluator_only']}->{row['retrieved_skill_evaluator_only']}"
            for row in audit_rows
        )
        reference_usage = Counter(int(row["reference_seed"]) for row in audit_rows)
        correct_distances = [
            float(row["standardized_distance"])
            for row in audit_rows
            if bool(row["retrieval_correct_evaluator_only"])
        ]
        error_distances = [
            float(row["standardized_distance"])
            for row in audit_rows
            if not bool(row["retrieval_correct_evaluator_only"])
        ]
        summary = {
            "reference_population": len(references),
            "query_population": len(queries),
            "reference_seed_min": min(int(row["seed"]) for row in references),
            "reference_seed_max": max(int(row["seed"]) for row in references),
            "query_seed_min": min(int(row["seed"]) for row in queries),
            "query_seed_max": max(int(row["seed"]) for row in queries),
            "feature_count": len(reference_features),
            "scaler_fit_population": "historical_reference_only",
            "nearest_reference_correct": correct,
            "nearest_reference_accuracy": correct / len(queries),
            "frozen_single_feature_selector_correct": frozen_correct,
            "frozen_single_feature_selector_accuracy": frozen_correct / len(queries),
            "confusion_counts": dict(confusion),
            "reference_seed_usage": dict(sorted(reference_usage.items())),
            "unique_references_retrieved": len(reference_usage),
            "median_standardized_distance": statistics.median(
                float(row["standardized_distance"]) for row in audit_rows
            ),
            "median_correct_distance": (
                statistics.median(correct_distances) if correct_distances else None
            ),
            "median_error_distance": (
                statistics.median(error_distances) if error_distances else None
            ),
            "reference_feature_means": means,
            "reference_feature_scales": scales,
            "query_agent_visible_only": True,
            "reference_labels_evaluator_only": True,
            "actionable_memory_eligible": False,
            "posthoc_only": True,
            "new_environment_rollouts": 0,
            "api_calls": 0,
            "phase_d_promoted": False,
        }
        _write_csv(args.output_csv.resolve(), audit_rows)
        args.output_summary.resolve().write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        report = [
            "# ProbeMem Applicability Retrieval Feasibility Audit",
            "",
            "## Setup",
            "",
            f"The audit uses {len(references)} decisive historical references from seeds {summary['reference_seed_min']}--{summary['reference_seed_max']} and {len(queries)} later decisive queries from seeds {summary['query_seed_min']}--{summary['query_seed_max']}. A single nearest reference is retrieved in the full 13-feature Agent-visible signature after scaling only on historical references.",
            "",
            "## Actual result",
            "",
            f"Nearest-reference skill agreement was {correct}/{len(queries)} ({correct / len(queries):.1%}). The frozen single-feature selector chose the accepted skill in {frozen_correct}/{len(queries)} ({frozen_correct / len(queries):.1%}).",
            f"Confusion counts: {dict(confusion)}.",
            f"The seven queries retrieved {len(reference_usage)} unique historical references; reference usage was {dict(sorted(reference_usage.items()))}.",
            f"Median standardized distance was {summary['median_standardized_distance']:.3f} (correct {summary['median_correct_distance']:.3f}, errors {summary['median_error_distance']:.3f}).",
            "",
            "## Claim boundary",
            "",
            "The query features are leakage-safe, but the historical preferred-skill labels come from evaluator-only paired counterfactual outcomes. This is therefore a post-hoc feature/retrieval feasibility audit, not operational Verified Episodic Memory, online adaptation, or a Phase-D promotion result. No rollout, API call, threshold fit, or prompt change was performed.",
        ]
        args.output_report.resolve().write_text("\n".join(report) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
