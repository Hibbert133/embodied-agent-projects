"""Select per-direction bias levels closest to a target baseline failure rate."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-csv", type=Path, nargs="+", required=True)
    parser.add_argument("--target-failure-rate", type=float, default=0.5)
    parser.add_argument("--max-clipped-step-fraction", type=float, default=0.5)
    parser.add_argument("--output-csv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0.0 <= args.target_failure_rate <= 1.0:
        raise ValueError("target failure rate must be between zero and one")
    if not 0.0 <= args.max_clipped_step_fraction <= 1.0:
        raise ValueError("maximum clipped-step fraction must be between zero and one")
    rows: list[dict[str, str]] = []
    for path in args.summary_csv:
        with path.open(encoding="utf-8", newline="") as file:
            rows.extend(csv.DictReader(file))
    candidates: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (row["bias_axis"], row["bias_direction"])
        candidates.setdefault(key, []).append(row)
    selected: list[dict[str, object]] = []
    for (axis, direction), group in sorted(candidates.items()):
        unique = {
            float(row["perturbation_level"]): row for row in group
        }.values()
        eligible = [
            row for row in unique
            if float(row["clipped_step_fraction"]) <= args.max_clipped_step_fraction
        ]
        if not eligible:
            raise ValueError(f"no clipping-safe candidate for {axis}_{direction}")
        best = min(
            eligible,
            key=lambda row: (
                abs((1.0 - float(row["success_rate"])) - args.target_failure_rate),
                float(row["perturbation_level"]),
            ),
        )
        failure_rate = 1.0 - float(best["success_rate"])
        target_error = abs(failure_rate - args.target_failure_rate)
        clipping = float(best["clipped_step_fraction"])
        selected.append(
            {
                "bias_axis": axis,
                "bias_direction": direction,
                "selected_magnitude": float(best["perturbation_level"]),
                "calibration_episodes": int(best["num_episodes"]),
                "baseline_success_rate": float(best["success_rate"]),
                "baseline_failure_rate": failure_rate,
                "target_failure_rate": args.target_failure_rate,
                "absolute_target_error": target_error,
                "clipped_step_fraction": clipping,
                "clipped_element_fraction": float(best["clipped_element_fraction"]),
                "max_allowed_clipped_step_fraction": args.max_clipped_step_fraction,
                "primary_benchmark_eligible": (
                    target_error <= 0.100000001
                    and clipping <= args.max_clipped_step_fraction
                ),
            }
        )
    output = args.output_csv.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(selected[0]))
        writer.writeheader()
        writer.writerows(selected)
    for row in selected:
        print(
            f"{row['bias_axis']}_{row['bias_direction']}: "
            f"magnitude={float(row['selected_magnitude']):.3f} "
            f"failure={float(row['baseline_failure_rate']):.1%}"
        )
    print(f"selected configs: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
