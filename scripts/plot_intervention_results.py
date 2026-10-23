"""Render recovery/cost and causal-decision evidence from a completed P1 run."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "no_intervention": "No intervention",
    "bias_compensation_for_all": "Bias compensation",
    "stochastic_retry_for_all": "Stochastic retry",
    "passive_diagnosis_intervention": "Passive diagnosis",
    "active_evidence_intervention": "Active evidence",
    "oracle_mechanism_intervention": "Oracle mechanism",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/figures/evidence_grounded_intervention.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from PIL import Image, ImageDraw, ImageFont

        run = args.run_dir.resolve()
        status = json.loads((run / "run_status.json").read_text(encoding="utf-8"))
        if status["status"] != "COMPLETED":
            raise ValueError("plot requires a completed intervention run")
        with (run / "method_summary.csv").open("r", encoding="utf-8", newline="") as handle:
            summaries = list(csv.DictReader(handle))
        funnel = json.loads((run / "causal_funnel.json").read_text(encoding="utf-8"))
        by_method = {row["method"]: row for row in summaries}
        if set(by_method) != set(LABELS):
            raise ValueError("summary does not contain the six frozen methods")

        width, height = 1800, 1050
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=20)
        small = ImageFont.load_default(size=17)
        title = ImageFont.load_default(size=29)
        draw.text((390, 25), "Evidence-grounded intervention: frozen held-out result", fill="black", font=title)

        methods = list(LABELS)
        colors = ["#4c78a8", "#f58518", "#e45756", "#72b7b2", "#2ca02c", "#777777"]
        chart_left, chart_right, chart_top, chart_bottom = 250, 1050, 120, 850
        for tick in (0, 25, 50, 75, 100):
            y = chart_bottom - tick / 100 * (chart_bottom - chart_top)
            draw.line((chart_left, y, chart_right, y), fill="#dddddd", width=2)
            draw.text((190, y - 10), f"{tick}%", fill="black", font=small)
        bar_width = 90
        gap = (chart_right - chart_left) / len(methods)
        for index, method in enumerate(methods):
            value = 100 * float(by_method[method]["recovery_rate"])
            center = chart_left + gap * (index + 0.5)
            y = chart_bottom - value / 100 * (chart_bottom - chart_top)
            draw.rectangle((center - bar_width / 2, y, center + bar_width / 2, chart_bottom), fill=colors[index])
            draw.text((center - 30, y - 30), f"{value:.1f}%", fill=colors[index], font=small)
            words = LABELS[method].split()
            for line, word in enumerate(words):
                draw.text((center - 50, chart_bottom + 15 + 22 * line), word, fill="black", font=small)
        draw.text((420, 80), "Fresh-verification recovery rate", fill="black", font=font)

        panel_left = 1180
        draw.text((1240, 115), "Requested-probe causal audit", fill="black", font=font)
        audit = [
            ("Probe requested", funnel["probe_requested"], "#4c78a8"),
            ("Belief changed", funnel["belief_changed"], "#f58518"),
            ("Intervention changed", funnel["intervention_changed"], "#72b7b2"),
            ("Useful probe", funnel["useful_probes"], "#e45756"),
        ]
        for index, (label, count, color) in enumerate(audit):
            y = 215 + index * 145
            max_width = 430
            draw.rectangle((panel_left, y, panel_left + max_width, y + 58), outline="#cccccc", width=2)
            fill_width = max_width * count / max(1, funnel["probe_requested"])
            draw.rectangle((panel_left, y, panel_left + fill_width, y + 58), fill=color)
            draw.text((panel_left + 10, y + 15), f"{label}: {count}/7", fill="black", font=font)
        draw.text(
            (1160, 830),
            "Counts are parallel audits among requested probes;\nintervention change can occur without a mechanism-label change.",
            fill="#555555",
            font=small,
        )
        draw.text(
            (25, 990),
            f"run={status['experiment_run_id']} | promotion={status['promotion_status']} | matched fresh verification",
            fill="#666666",
            font=small,
        )
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, format="PNG", dpi=(180, 180), optimize=True)
        print(f"figure: {output}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
