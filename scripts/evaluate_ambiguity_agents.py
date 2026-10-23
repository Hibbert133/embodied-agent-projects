"""Evaluate passive and active-evidence baselines on a frozen ambiguity split."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_bias_noise_ambiguity_benchmark import (  # noqa: E402
    PASSIVE_MATCH_FEATURES,
)


@dataclass(frozen=True)
class PassivePrediction:
    mechanism: str
    uncertainty: float


@dataclass(frozen=True)
class PassiveCentroidModel:
    centers: Mapping[str, tuple[float, ...]]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]

    def predict(self, row: Mapping[str, Any]) -> PassivePrediction:
        vector = tuple(
            (float(row[name]) - center) / scale
            for name, center, scale in zip(
                PASSIVE_MATCH_FEATURES, self.feature_means, self.feature_scales
            )
        )
        distances = {
            label: math.dist(vector, center) for label, center in self.centers.items()
        }
        ordered = sorted(distances.items(), key=lambda item: (item[1], item[0]))
        prediction = ordered[0][0]
        distance_sum = sum(distances.values())
        uncertainty = (
            1.0
            if distance_sum == 0.0
            else 1.0 - abs(ordered[0][1] - ordered[1][1]) / distance_sum
        )
        return PassivePrediction(prediction, uncertainty)


def fit_passive_centroid(
    rows: Sequence[Mapping[str, Any]],
    *,
    leave_out_case_id: str | None = None,
) -> PassiveCentroidModel:
    training = [row for row in rows if str(row["case_id"]) != leave_out_case_id]
    labels = sorted({str(row["mechanism_class"]) for row in training})
    if labels != ["stable_bias", "stochastic_noise"]:
        raise ValueError("passive centroid requires stable_bias and stochastic_noise")
    feature_means = tuple(
        mean(float(row[name]) for row in training) for name in PASSIVE_MATCH_FEATURES
    )
    feature_scales = tuple(
        pstdev(float(row[name]) for row in training) or 1.0
        for name in PASSIVE_MATCH_FEATURES
    )

    def standardize(row: Mapping[str, Any]) -> tuple[float, ...]:
        return tuple(
            (float(row[name]) - center) / scale
            for name, center, scale in zip(
                PASSIVE_MATCH_FEATURES, feature_means, feature_scales
            )
        )

    centers = {
        label: tuple(
            mean(vector[index] for vector in vectors)
            for index in range(len(PASSIVE_MATCH_FEATURES))
        )
        for label in labels
        for vectors in [
            [standardize(row) for row in training if row["mechanism_class"] == label]
        ]
    }
    return PassiveCentroidModel(centers, feature_means, feature_scales)


def leave_one_out_predictions(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, PassivePrediction]:
    counts = {
        label: sum(str(row["mechanism_class"]) == label for row in rows)
        for label in ("stable_bias", "stochastic_noise")
    }
    if min(counts.values()) < 2:
        raise ValueError("leave-one-out tuning requires at least two cases per class")
    return {
        str(row["case_id"]): fit_passive_centroid(
            rows, leave_out_case_id=str(row["case_id"])
        ).predict(row)
        for row in rows
    }


def select_gate_threshold(
    rows: Sequence[Mapping[str, Any]],
    passive: Mapping[str, PassivePrediction],
    probe_predictions: Mapping[str, str],
) -> dict[str, Any]:
    if not rows:
        raise ValueError("tuning rows are required")
    uncertainties = sorted({prediction.uncertainty for prediction in passive.values()})
    candidates = [
        uncertainties[0] - 1e-12,
        *[(a + b) / 2.0 for a, b in zip(uncertainties, uncertainties[1:])],
        uncertainties[-1] + 1e-12,
    ]
    evaluated = []
    for threshold in candidates:
        correct = 0
        requests = 0
        for row in rows:
            case_id = str(row["case_id"])
            request = passive[case_id].uncertainty >= threshold
            predicted = (
                probe_predictions[case_id] if request else passive[case_id].mechanism
            )
            requests += int(request)
            correct += int(predicted == row["mechanism_class"])
        evaluated.append((correct, requests, threshold))
    correct, requests, threshold = min(
        evaluated, key=lambda item: (-item[0], item[1], -item[2])
    )
    return {
        "threshold": threshold,
        "selection_rule": (
            "maximize leave-one-out tuning accuracy, then minimize probe requests; "
            "higher threshold tie-break"
        ),
        "tuning_cases": len(rows),
        "tuning_correct": correct,
        "tuning_accuracy": correct / len(rows),
        "tuning_probe_requests": requests,
        "tuning_probe_request_rate": requests / len(rows),
    }


def deterministic_random_request(case_id: str, probability: float, seed: int) -> bool:
    if not 0.0 <= probability <= 1.0:
        raise ValueError("random probe probability must be in [0, 1]")
    digest = hashlib.sha256(f"{seed}:{case_id}".encode("utf-8")).digest()
    draw = int.from_bytes(digest[:8], "big") / float(1 << 64)
    return draw < probability


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _probe_predictions(path: Path) -> tuple[dict[str, str], dict[str, int]]:
    rows = _read_csv(path)
    return (
        {row["case_id"]: row["predicted_mechanism"] for row in rows},
        {row["case_id"]: int(row["probe_environment_steps"]) for row in rows},
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def evaluate(
    tuning_cases_path: Path,
    tuning_probe_path: Path,
    heldout_cases_path: Path,
    heldout_probe_path: Path,
    output_dir: Path,
    *,
    random_seed: int,
) -> dict[str, Any]:
    tuning_rows = _read_csv(tuning_cases_path)
    heldout_rows = _read_csv(heldout_cases_path)
    tuning_probe, _ = _probe_predictions(tuning_probe_path)
    heldout_probe, probe_steps = _probe_predictions(heldout_probe_path)
    tuning_passive = leave_one_out_predictions(tuning_rows)
    gate = select_gate_threshold(tuning_rows, tuning_passive, tuning_probe)
    model = fit_passive_centroid(tuning_rows)
    heldout_passive = {
        row["case_id"]: model.predict(row) for row in heldout_rows
    }
    random_probability = float(gate["tuning_probe_request_rate"])

    result_rows: list[dict[str, Any]] = []
    for row in heldout_rows:
        case_id = row["case_id"]
        passive = heldout_passive[case_id]
        decisions = {
            "passive": False,
            "always_probe": True,
            "random_probe": deterministic_random_request(
                case_id, random_probability, random_seed
            ),
            "uncertainty_gated": passive.uncertainty >= float(gate["threshold"]),
        }
        for method, request in decisions.items():
            predicted = heldout_probe[case_id] if request else passive.mechanism
            result_rows.append(
                {
                    "case_id": case_id,
                    "pair_id": row["pair_id"],
                    "seed": int(row["seed"]),
                    "method": method,
                    "passive_prediction": passive.mechanism,
                    "passive_uncertainty": passive.uncertainty,
                    "probe_requested": request,
                    "prediction": predicted,
                    "mechanism_class_oracle": row["mechanism_class"],
                    "correct": predicted == row["mechanism_class"],
                    "probe_environment_steps": probe_steps[case_id] if request else 0,
                }
            )

    summary_rows: list[dict[str, Any]] = []
    passive_correct = sum(
        bool(row["correct"]) for row in result_rows if row["method"] == "passive"
    )
    for method in ("passive", "always_probe", "random_probe", "uncertainty_gated"):
        selected = [row for row in result_rows if row["method"] == method]
        correct = sum(bool(row["correct"]) for row in selected)
        steps = sum(int(row["probe_environment_steps"]) for row in selected)
        by_class = [
            [row for row in selected if row["mechanism_class_oracle"] == label]
            for label in ("stable_bias", "stochastic_noise")
        ]
        balanced = mean(
            sum(bool(row["correct"]) for row in rows) / len(rows) for rows in by_class
        )
        summary_rows.append(
            {
                "method": method,
                "cases": len(selected),
                "correct": correct,
                "accuracy": correct / len(selected),
                "balanced_accuracy": balanced,
                "probe_requests": sum(bool(row["probe_requested"]) for row in selected),
                "probe_request_rate": sum(bool(row["probe_requested"]) for row in selected)
                / len(selected),
                "probe_environment_steps": steps,
                "additional_correct_over_passive": correct - passive_correct,
                "additional_correct_per_100_probe_steps": (
                    100.0 * (correct - passive_correct) / steps if steps else 0.0
                ),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "per_case_results.csv", result_rows)
    _write_csv(output_dir / "summary.csv", summary_rows)
    protocol = {
        **gate,
        "heldout_retuning": False,
        "passive_model": "tuning-fitted standardized nearest class centroid",
        "passive_uncertainty": "one minus normalized two-centroid distance margin",
        "random_seed": random_seed,
        "random_probe_probability": random_probability,
        "probe_prediction_source": "frozen repeated-probe threshold outputs",
        "claim_boundary": "four held-out matched cases; report exact counts",
    }
    (output_dir / "protocol.json").write_text(
        json.dumps(protocol, indent=2) + "\n", encoding="utf-8"
    )
    return {"protocol": protocol, "summary": summary_rows}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tuning-dir",
        type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/bias_noise_tuning_v1",
    )
    parser.add_argument(
        "--heldout-dir",
        type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/bias_noise_heldout_v1",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/agent_comparison_v1",
    )
    parser.add_argument("--random-seed", type=int, default=20260730)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = evaluate(
            args.tuning_dir / "cases.csv",
            args.tuning_dir / "probe_audit.csv",
            args.heldout_dir / "cases.csv",
            args.heldout_dir / "probe_audit.csv",
            args.output_dir.resolve(),
            random_seed=args.random_seed,
        )
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
