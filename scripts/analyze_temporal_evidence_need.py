"""Tune a causal temporal-uncertainty probe gate on development cases only."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_ambiguity_agents import fit_passive_centroid  # noqa: E402


def select_temporal_threshold(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Select a high-uncertainty probe rule using development labels only."""
    if not rows:
        raise ValueError("development rows are required")
    scores = sorted({float(row["temporal_uncertainty"]) for row in rows})
    candidates = [
        scores[0] - 1e-12,
        *[(lower + upper) / 2.0 for lower, upper in zip(scores, scores[1:])],
        scores[-1] + 1e-12,
    ]
    evaluated = []
    for threshold in candidates:
        correct = 0
        requests = 0
        for row in rows:
            request = float(row["temporal_uncertainty"]) >= threshold
            predicted = row["probe_prediction"] if request else row["passive_prediction"]
            correct += int(predicted == row["mechanism_class_oracle"])
            requests += int(request)
        evaluated.append((correct, requests, threshold))
    correct, requests, threshold = min(
        evaluated, key=lambda item: (-item[0], item[1], -item[2])
    )
    return {
        "threshold": threshold,
        "selection_direction": "request probe when temporal_uncertainty >= threshold",
        "selection_rule": (
            "maximize development diagnostic accuracy, then minimize probe requests; "
            "higher threshold tie-break"
        ),
        "development_cases": len(rows),
        "development_correct": correct,
        "development_accuracy": correct / len(rows),
        "development_probe_requests": requests,
        "development_probe_request_rate": requests / len(rows),
    }


def roc_auc_for_probe_need(rows: Sequence[Mapping[str, Any]]) -> float:
    positives = [row for row in rows if bool(row["probe_needed_oracle"])]
    negatives = [row for row in rows if not bool(row["probe_needed_oracle"])]
    if not positives or not negatives:
        raise ValueError("probe-need ROC AUC requires both classes")
    return sum(
        (float(positive["temporal_uncertainty"]) > float(negative["temporal_uncertainty"]))
        + 0.5
        * (
            float(positive["temporal_uncertainty"])
            == float(negative["temporal_uncertainty"])
        )
        for positive in positives
        for negative in negatives
    ) / (len(positives) * len(negatives))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def analyze(
    tuning_cases_path: Path,
    development_cases_path: Path,
    development_probe_path: Path,
    temporal_features_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    tuning_rows = _read_csv(tuning_cases_path)
    development_rows = _read_csv(development_cases_path)
    probe_by_case = {
        row["case_id"]: row["predicted_mechanism"]
        for row in _read_csv(development_probe_path)
    }
    temporal_by_case = {
        row["case_id"]: row for row in _read_csv(temporal_features_path)
    }
    model = fit_passive_centroid(tuning_rows)
    rows: list[dict[str, Any]] = []
    for development in development_rows:
        case_id = development["case_id"]
        if case_id not in probe_by_case or case_id not in temporal_by_case:
            raise ValueError(f"missing probe or temporal evidence for {case_id}")
        passive = model.predict(development)
        probe_prediction = probe_by_case[case_id]
        truth = development["mechanism_class"]
        probe_needed = passive.mechanism != truth and probe_prediction == truth
        temporal = temporal_by_case[case_id]
        rows.append(
            {
                "case_id": case_id,
                "pair_id": development["pair_id"],
                "seed": int(development["seed"]),
                "passive_prediction": passive.mechanism,
                "terminal_margin_uncertainty": passive.uncertainty,
                "temporal_uncertainty": float(temporal["temporal_uncertainty"]),
                "normalized_residual_norm": float(
                    temporal["normalized_residual_norm"]
                ),
                "probe_prediction": probe_prediction,
                "mechanism_class_oracle": truth,
                "passive_correct": passive.mechanism == truth,
                "probe_correct": probe_prediction == truth,
                "probe_needed_oracle": probe_needed,
            }
        )
    selected = select_temporal_threshold(rows)
    selected["probe_need_roc_auc"] = roc_auc_for_probe_need(rows)
    selected["probe_needed_cases"] = sum(bool(row["probe_needed_oracle"]) for row in rows)
    selected["development_tuning"] = True
    selected["heldout_evaluated"] = False
    selected["future_status"] = (
        "development-only candidate; promotion decision is documented separately"
    )

    per_method: list[dict[str, Any]] = []
    for method in ("passive", "always_probe", "temporal_uncertainty_gated"):
        predictions = []
        requests = 0
        for row in rows:
            if method == "passive":
                request = False
            elif method == "always_probe":
                request = True
            else:
                request = float(row["temporal_uncertainty"]) >= float(selected["threshold"])
            requests += int(request)
            predictions.append(
                row["probe_prediction"] if request else row["passive_prediction"]
            )
        correct = sum(
            prediction == row["mechanism_class_oracle"]
            for prediction, row in zip(predictions, rows)
        )
        per_method.append(
            {
                "method": method,
                "cases": len(rows),
                "correct": correct,
                "accuracy": correct / len(rows),
                "probe_requests": requests,
                "probe_request_rate": requests / len(rows),
                "probe_environment_steps": requests * 64,
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "per_case.csv", rows)
    _write_csv(output_dir / "development_summary.csv", per_method)
    (output_dir / "candidate_threshold.json").write_text(
        json.dumps(selected, indent=2) + "\n", encoding="utf-8"
    )
    return {"candidate": selected, "summary": per_method}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tuning-cases",
        type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/bias_noise_tuning_v1/cases.csv",
    )
    parser.add_argument(
        "--development-dir",
        type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/bias_noise_temporal_development_v1",
    )
    parser.add_argument(
        "--temporal-features",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/temporal_development_rollouts/temporal_features.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/temporal_gate_development_v1",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = analyze(
            args.tuning_cases,
            args.development_dir / "cases.csv",
            args.development_dir / "probe_audit.csv",
            args.temporal_features,
            args.output_dir.resolve(),
        )
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
