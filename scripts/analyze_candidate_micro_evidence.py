"""Analyze every registered horizon in a candidate micro-evidence run."""

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

from src.evaluation.allocation_metrics import (  # noqa: E402
    paired_win_tie_loss,
    stratified_paired_bootstrap_difference,
    wilson_interval,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _as_bool(value: object) -> bool:
    return str(value).strip().lower() == "true"


def summarize_horizon(
    rows: Sequence[Mapping[str, str]],
    candidate_outcomes: Mapping[tuple[str, str], bool],
) -> dict[str, Any]:
    """Return paired recovery and interaction-cost metrics for one horizon."""

    if not rows:
        raise ValueError("horizon summary requires result rows")
    selected = [_as_bool(row["selected_recovery_success"]) for row in rows]
    compensation = [
        candidate_outcomes[(row["case_id"], "probe_grounded_compensation")]
        for row in rows
    ]
    retry = [candidate_outcomes[(row["case_id"], "stochastic_retry")] for row in rows]
    agreements = sum(_as_bool(row["utility_agreement"]) for row in rows)
    recoveries = sum(selected)
    return {
        "horizon": int(rows[0]["horizon"]),
        "cases": len(rows),
        "utility_agreement_count": agreements,
        "utility_agreement_rate": agreements / len(rows),
        "utility_agreement_wilson95": wilson_interval(agreements, len(rows)),
        "selected_recovery_count": recoveries,
        "selected_recovery_rate": recoveries / len(rows),
        "selected_recovery_wilson95": wilson_interval(recoveries, len(rows)),
        "versus_fixed_compensation": paired_win_tie_loss(selected, compensation),
        "versus_fixed_retry": paired_win_tie_loss(selected, retry),
        "recovery_difference_vs_compensation": stratified_paired_bootstrap_difference(
            selected, compensation, ["stochastic_noise"] * len(rows), repetitions=10_000, seed=5005
        ),
        "recovery_difference_vs_retry": stratified_paired_bootstrap_difference(
            selected, retry, ["stochastic_noise"] * len(rows), repetitions=10_000, seed=5006
        ),
        "mean_prefix_environment_steps": sum(int(row["prefix_environment_steps"]) for row in rows)
        / len(rows),
        "mean_total_additional_steps": sum(
            int(row["prefix_environment_steps"]) + int(row["selected_verification_steps"])
            for row in rows
        )
        / len(rows),
    }


def _plot(analysis: Mapping[str, Any], output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1700, 950
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    small = ImageFont.load_default(size=17)
    font = ImageFont.load_default(size=21)
    title = ImageFont.load_default(size=29)
    draw.text((380, 25), "Candidate-conditioned micro-evidence: cost versus outcome", fill="black", font=title)
    panels = ((110, 900, "Utility agreement", "utility_agreement_rate"), (925, 1650, "Recovery rate", "selected_recovery_rate"))
    horizons = analysis["horizons"]
    for left, right, label, key in panels:
        top, bottom = 135, 760
        draw.rectangle((left, top, right, bottom), outline="#777777", width=2)
        draw.text((left + 235, 90), label, fill="black", font=font)
        for tick in range(0, 6):
            value = tick / 5
            y = bottom - value * (bottom - top)
            draw.line((left, y, right, y), fill="#e5e5e5", width=1)
            draw.text((left - 55, y - 9), f"{value:.1f}", fill="#555555", font=small)
        max_cost = max(float(row["mean_prefix_environment_steps"]) for row in horizons)
        points = []
        for row in horizons:
            cost = float(row["mean_prefix_environment_steps"])
            x = left + 35 + cost / max_cost * (right - left - 70)
            y = bottom - float(row[key]) * (bottom - top)
            points.append((x, y))
            draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill="#4c78a8")
            draw.text(
                (x + 12, y - 25),
                f"h={row['horizon']} ({cost:g} steps)",
                fill="#4c78a8",
                font=small,
            )
        if len(points) > 1:
            draw.line(points, fill="#4c78a8", width=4)
        if key == "selected_recovery_rate":
            baseline_y = bottom - float(analysis["fixed_recovery_rate"]) * (bottom - top)
            draw.line((left, baseline_y, right, baseline_y), fill="#e45756", width=3)
            draw.text((left + 20, baseline_y + 10), "fixed candidates: 0.40", fill="#e45756", font=small)
            oracle_y = bottom - float(analysis["oracle_candidate_recovery_rate"]) * (bottom - top)
            draw.line((left, oracle_y, right, oracle_y), fill="#54a24b", width=3)
            draw.text((left + 20, oracle_y - 30), "post-hoc candidate oracle: 0.65", fill="#54a24b", font=small)
        draw.text((left + 245, 800), "Mean prefix environment steps", fill="black", font=small)
    draw.text((80, 885), f"run={analysis['experiment_run_id']} | n=20 development cases | all horizons reported | no fitted threshold", fill="#666666", font=small)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", dpi=(180, 180), optimize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-figure", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run = args.run_dir.resolve()
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        results = _read_csv(run / "results.csv")
        config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
        source = (ROOT / config["source_run"]).resolve()
        source_rows = _read_csv(source / "candidate_results.csv")
        outcomes = {
            (row["case_id"], row["candidate_id"]): _as_bool(row["verification_success"])
            for row in source_rows
        }
        horizons = [
            summarize_horizon(
                [row for row in results if int(row["horizon"]) == horizon], outcomes
            )
            for horizon in config["prefix_horizons"]
        ]
        analysis = {
            **manifest,
            "split": "development",
            "source_population_cases": int(config["expected_cases"]),
            "fixed_recovery_rate": sum(
                outcomes[(row["case_id"], "probe_grounded_compensation")]
                for row in results
                if int(row["horizon"]) == int(config["prefix_horizons"][0])
            )
            / int(config["expected_cases"]),
            "oracle_candidate_recovery_rate": sum(
                outcomes[(row["case_id"], "probe_grounded_compensation")]
                or outcomes[(row["case_id"], "stochastic_retry")]
                for row in results
                if int(row["horizon"]) == int(config["prefix_horizons"][0])
            )
            / int(config["expected_cases"]),
            "horizons": horizons,
            "claim_status": "NO_STABLE_COST_JUSTIFIED_IMPROVEMENT",
        }
        (run / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
        _plot(analysis, args.output_figure.resolve())
        print(f"analysis: {run / 'analysis.json'}")
        print(f"figure: {args.output_figure.resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
