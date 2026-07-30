"""Evaluate the pre-registered phase-conditioned evidence-need score."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_temporal_evidence_need import (  # noqa: E402
    roc_auc_for_probe_need,
    select_temporal_threshold,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def evaluate_promotion(
    *, auc: float, gated_accuracy: float, always_accuracy: float,
    probe_request_rate: float, promotion: Mapping[str, Any],
) -> dict[str, Any]:
    accuracy_ratio = gated_accuracy / always_accuracy if always_accuracy else 0.0
    checks = {
        "probe_need_auc": auc >= float(promotion["minimum_probe_need_roc_auc"]),
        "diagnostic_accuracy": accuracy_ratio
        >= float(promotion["minimum_diagnostic_accuracy_relative_to_always_probe"]),
        "probe_request_rate": probe_request_rate
        <= float(promotion["maximum_probe_request_rate"]),
    }
    return {
        "criteria": checks,
        "all_passed": all(checks.values()),
        "online_agent_allowed": all(checks.values()),
        "accuracy_relative_to_always_probe": accuracy_ratio,
    }


def analyze(
    temporal_case_path: Path, phase_feature_path: Path, config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    temporal_rows = _read_csv(temporal_case_path)
    phase_by_case = {row["case_id"]: row for row in _read_csv(phase_feature_path)}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for temporal in temporal_rows:
        case_id = temporal["case_id"]
        if case_id not in phase_by_case:
            raise ValueError(f"missing phase features for {case_id}")
        phase = phase_by_case[case_id]
        rows.append(
            {
                **temporal,
                "passive_correct": _as_bool(temporal["passive_correct"]),
                "probe_correct": _as_bool(temporal["probe_correct"]),
                "probe_needed_oracle": _as_bool(temporal["probe_needed_oracle"]),
                "phase_inconsistency": float(phase["phase_inconsistency"]),
                "eligible_sample_fraction": float(phase["eligible_sample_fraction"]),
                "approach_sample_count": int(phase["approach_sample_count"]),
                "approach_residual_norm": phase["approach_residual_norm"],
                "push_sample_count": int(phase["push_sample_count"]),
                "push_residual_norm": phase["push_residual_norm"],
                "near_goal_sample_count": int(phase["near_goal_sample_count"]),
                "near_goal_residual_norm": phase["near_goal_residual_norm"],
            }
        )
    selected = select_temporal_threshold(rows, score_field="phase_inconsistency")
    auc = roc_auc_for_probe_need(rows, score_field="phase_inconsistency")
    threshold = float(selected["threshold"])
    methods = []
    for method in ("passive", "always_probe", "phase_conditioned_gate"):
        correct = 0
        requests = 0
        for row in rows:
            request = method == "always_probe" or (
                method == "phase_conditioned_gate"
                and float(row["phase_inconsistency"]) >= threshold
            )
            prediction = row["probe_prediction"] if request else row["passive_prediction"]
            correct += int(prediction == row["mechanism_class_oracle"])
            requests += int(request)
        methods.append(
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
    by_method = {row["method"]: row for row in methods}
    promotion = evaluate_promotion(
        auc=auc,
        gated_accuracy=float(by_method["phase_conditioned_gate"]["accuracy"]),
        always_accuracy=float(by_method["always_probe"]["accuracy"]),
        probe_request_rate=float(by_method["phase_conditioned_gate"]["probe_request_rate"]),
        promotion=config["promotion_gate"],
    )
    decision = {
        **selected,
        "score": "phase_inconsistency",
        "probe_need_roc_auc": auc,
        "promotion_gate": config["promotion_gate"],
        "promotion_result": promotion,
        "development_only": True,
        "heldout_evaluated": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "per_case.csv", rows)
    _write_csv(output_dir / "development_summary.csv", methods)
    (output_dir / "selection_and_promotion.json").write_text(
        json.dumps(decision, indent=2) + "\n", encoding="utf-8"
    )
    return {"selection": decision, "summary": methods}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--temporal-cases", type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/temporal_gate_development_v1/per_case.csv",
    )
    parser.add_argument(
        "--phase-features", type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/temporal_development_rollouts/phase_features.csv",
    )
    parser.add_argument(
        "--config", type=Path,
        default=ROOT / "configs/benchmarks/phase_conditioned_evidence_development_v1.json",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/phase_gate_development_v1",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = analyze(
            args.temporal_cases, args.phase_features, args.config, args.output_dir.resolve()
        )
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
