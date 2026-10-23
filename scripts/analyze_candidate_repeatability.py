"""Analyze a frozen candidate-repeatability evidence run."""

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


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _bool(value: object) -> bool:
    return str(value).lower() == "true"


def summarize(
    rows: Sequence[Mapping[str, str]], outcomes: Mapping[tuple[str, str], bool]
) -> dict[str, Any]:
    if not rows:
        raise ValueError("repeatability summary requires rows")
    selected = [_bool(row["selected_recovery_success"]) for row in rows]
    compensation = [
        outcomes[(row["case_id"], "probe_grounded_compensation")] for row in rows
    ]
    retry = [outcomes[(row["case_id"], "stochastic_retry")] for row in rows]
    agreements = sum(_bool(row["utility_agreement"]) for row in rows)
    recoveries = sum(selected)
    return {
        "repetition_count": int(rows[0]["repetition_count"]),
        "cases": len(rows),
        "utility_agreement_count": agreements,
        "utility_agreement_rate": agreements / len(rows),
        "utility_agreement_wilson95": wilson_interval(agreements, len(rows)),
        "selected_recovery_count": recoveries,
        "selected_recovery_rate": recoveries / len(rows),
        "selected_recovery_wilson95": wilson_interval(recoveries, len(rows)),
        "versus_compensation": paired_win_tie_loss(selected, compensation),
        "versus_retry": paired_win_tie_loss(selected, retry),
        "recovery_difference_vs_retry": stratified_paired_bootstrap_difference(
            selected,
            retry,
            ["stochastic_noise"] * len(rows),
            repetitions=10_000,
            seed=5041 + int(rows[0]["repetition_count"]),
        ),
        "mean_prefix_environment_steps": sum(
            int(row["prefix_environment_steps"]) for row in rows
        )
        / len(rows),
        "mean_total_additional_steps": sum(
            int(row["prefix_environment_steps"])
            + int(row["selected_verification_steps"])
            for row in rows
        )
        / len(rows),
    }


def _transition(rows: Sequence[Mapping[str, str]], before: int, after: int) -> dict[str, int]:
    indexed = {
        (row["case_id"], int(row["repetition_count"])): row for row in rows
    }
    case_ids = sorted({row["case_id"] for row in rows})
    changed = improved = worsened = 0
    for case_id in case_ids:
        left, right = indexed[(case_id, before)], indexed[(case_id, after)]
        if left["selected_candidate"] != right["selected_candidate"]:
            changed += 1
            left_success = _bool(left["selected_recovery_success"])
            right_success = _bool(right["selected_recovery_success"])
            improved += int(right_success and not left_success)
            worsened += int(left_success and not right_success)
    return {"decision_changed": changed, "recovery_improved": improved, "recovery_worsened": worsened}


def _plot(analysis: Mapping[str, Any], output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1700, 950), "white")
    draw = ImageDraw.Draw(image)
    small = ImageFont.load_default(size=17)
    font = ImageFont.load_default(size=22)
    title = ImageFont.load_default(size=29)
    draw.text((390, 25), "Repeated candidate evidence: interaction cost versus outcome", fill="black", font=title)
    for left, right, label, field in (
        (110, 900, "Utility agreement", "utility_agreement_rate"),
        (925, 1650, "Recovery rate", "selected_recovery_rate"),
    ):
        top, bottom = 135, 760
        draw.rectangle((left, top, right, bottom), outline="#777777", width=2)
        draw.text((left + 250, 90), label, fill="black", font=font)
        for tick in range(6):
            value = tick / 5
            y = bottom - value * (bottom - top)
            draw.line((left, y, right, y), fill="#e5e5e5")
            draw.text((left - 55, y - 9), f"{value:.1f}", fill="#555555", font=small)
        points = []
        for row in analysis["repetitions"]:
            x = left + 80 + (int(row["repetition_count"]) - 1) * (right - left - 160) / 2
            y = bottom - float(row[field]) * (bottom - top)
            points.append((x, y))
            draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill="#4c78a8")
            draw.text((x - 35, y - 35), f"k={row['repetition_count']}", fill="#4c78a8", font=small)
            draw.text((x - 45, 790), f"{row['mean_prefix_environment_steps']:.0f} steps", fill="#555555", font=small)
        draw.line(points, fill="#4c78a8", width=4)
        if field == "selected_recovery_rate":
            for value, color, label_text, offset in (
                (analysis["fixed_compensation_recovery_rate"], "#e45756", "fixed compensation", 10),
                (analysis["fixed_retry_recovery_rate"], "#f58518", "fixed retry", -30),
                (analysis["oracle_candidate_recovery_rate"], "#54a24b", "candidate oracle", -30),
            ):
                y = bottom - float(value) * (bottom - top)
                draw.line((left, y, right, y), fill=color, width=3)
                draw.text((left + 15, y + offset), f"{label_text}: {value:.2f}", fill=color, font=small)
    draw.text((75, 880), f"run={analysis['experiment_run_id']} | n=20 fresh development cases | selector frozen before collection", fill="#666666", font=small)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", dpi=(180, 180), optimize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output-figure", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run, source = args.run_dir.resolve(), args.source_run.resolve()
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    rows = _csv(run / "results.csv")
    candidate_rows = _csv(source / "candidate_results.csv")
    outcomes = {
        (row["case_id"], row["candidate_id"]): _bool(row["verification_success"])
        for row in candidate_rows
    }
    case_ids = sorted({row["case_id"] for row in rows})
    repetitions = [
        summarize([row for row in rows if int(row["repetition_count"]) == count], outcomes)
        for count in (1, 2, 3)
    ]
    analysis = {
        **manifest,
        "split": "development",
        "cases": len(case_ids),
        "fixed_compensation_recovery_rate": sum(
            outcomes[(case_id, "probe_grounded_compensation")] for case_id in case_ids
        )
        / len(case_ids),
        "fixed_retry_recovery_rate": sum(
            outcomes[(case_id, "stochastic_retry")] for case_id in case_ids
        )
        / len(case_ids),
        "oracle_candidate_recovery_rate": sum(
            outcomes[(case_id, "probe_grounded_compensation")]
            or outcomes[(case_id, "stochastic_retry")]
            for case_id in case_ids
        )
        / len(case_ids),
        "repetitions": repetitions,
        "additional_evidence_transitions": {
            "k1_to_k2": _transition(rows, 1, 2),
            "k1_to_k3": _transition(rows, 1, 3),
        },
        "claim_status": "REPEATED_PREFIX_EVIDENCE_NOT_COST_JUSTIFIED",
    }
    (run / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    _plot(analysis, args.output_figure.resolve())
    print(f"analysis: {run / 'analysis.json'}")
    print(f"figure: {args.output_figure.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
