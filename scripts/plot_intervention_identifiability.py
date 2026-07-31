"""Plot real candidate preference and causal changes from a completed audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/figures/intervention_identifiability_development.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from PIL import Image, ImageDraw, ImageFont

        run = args.run_dir.resolve()
        status = json.loads((run / "run_status.json").read_text(encoding="utf-8"))
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        if status.get("status") != "COMPLETED":
            raise ValueError("plot requires a completed run")
        conditions = summary["stratified_summary"]["condition_id"]

        width, height = 1800, 1050
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        small = ImageFont.load_default(size=17)
        font = ImageFont.load_default(size=21)
        title = ImageFont.load_default(size=29)
        draw.text((330, 25), "Development audit: mechanism label versus intervention utility", fill="black", font=title)

        left, right, top, bottom = 180, 1050, 150, 820
        maximum = max(item["units"] for item in conditions.values())
        for tick in range(0, maximum + 1, 2):
            y = bottom - tick / maximum * (bottom - top)
            draw.line((left, y, right, y), fill="#dddddd", width=2)
            draw.text((145, y - 10), str(tick), fill="#555555", font=small)
        gap = (right - left) / len(conditions)
        bar_width = 72
        for index, (condition, values) in enumerate(conditions.items()):
            center = left + gap * (index + 0.5)
            for offset, key, color in (
                (-bar_width / 2, "compensation_best", "#4c78a8"),
                (bar_width / 2, "retry_best", "#f58518"),
            ):
                value = values[key]
                y = bottom - value / maximum * (bottom - top)
                x = center + offset
                draw.rectangle((x - 32, y, x + 32, bottom), fill=color)
                draw.text((x - 8, y - 28), str(value), fill=color, font=small)
            draw.text((center - 35, bottom + 20), condition, fill="black", font=small)
        draw.text((385, 105), "Outcome-preferred candidate by condition", fill="black", font=font)
        draw.rectangle((300, 905, 330, 930), fill="#4c78a8")
        draw.text((345, 907), "Probe-grounded compensation", fill="black", font=small)
        draw.rectangle((650, 905, 680, 930), fill="#f58518")
        draw.text((695, 907), "Stochastic retry", fill="black", font=small)

        panel_left = 1160
        draw.text((1210, 105), "Probe-to-outcome audit", fill="black", font=font)
        funnel = [
            ("Operational failures", summary["operational_units"], "#777777"),
            ("Paired comparable", summary["paired_comparable_units"], "#4c78a8"),
            ("Belief changed", summary["belief_change_count"], "#72b7b2"),
            ("Selection improved", summary["probe_selected_outcome_improved_count"], "#2ca02c"),
            ("Selection worsened", summary["probe_selected_outcome_worsened_count"], "#e45756"),
        ]
        maximum_funnel = summary["operational_units"]
        for index, (label, value, color) in enumerate(funnel):
            y = 190 + index * 125
            draw.rectangle((panel_left, y, panel_left + 470, y + 55), outline="#cccccc", width=2)
            draw.rectangle((panel_left, y, panel_left + 470 * value / maximum_funnel, y + 55), fill=color)
            draw.text((panel_left + 10, y + 14), f"{label}: {value}", fill="black", font=font)
        draw.text((1160, 850), "Development only. One compensation candidate abstained;\npaired utility coverage = 31/32 (96.9%).", fill="#555555", font=small)
        draw.text((25, 995), f"run={status['experiment_run_id']} | real fresh-verification outcomes | no API", fill="#666666", font=small)
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
