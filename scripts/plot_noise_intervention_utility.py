"""Plot the preregistered noise-stratum utility characterization."""

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
        default=ROOT / "outputs/figures/noise_intervention_utility.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from PIL import Image, ImageDraw, ImageFont

        run = args.run_dir.resolve()
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        analysis = json.loads((run / "feature_analysis.json").read_text(encoding="utf-8"))
        width, height = 1800, 1050
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        small = ImageFont.load_default(size=17)
        font = ImageFont.load_default(size=21)
        title = ImageFont.load_default(size=29)
        draw.text((390, 28), "Noise-stratum intervention utility: development characterization", fill="black", font=title)

        counts = summary["winner_counts"]
        labels = (("Compensation", counts["probe_grounded_compensation"], "#4c78a8"), ("Retry", counts["stochastic_retry"], "#f58518"))
        draw.text((300, 115), "Outcome-preferred candidate", fill="black", font=font)
        for index, (label, value, color) in enumerate(labels):
            x0 = 210 + index * 360
            y0 = 780 - value * 125
            draw.rectangle((x0, y0, x0 + 220, 780), fill=color)
            draw.text((x0 + 95, y0 - 35), str(value), fill=color, font=font)
            draw.text((x0 + 45, 805), label, fill="black", font=font)
        draw.text((180, 900), f"n={analysis['paired_comparable_units']} comparable failures; retry prevalence={100 * analysis['retry_prevalence']:.1f}%", fill="#555555", font=small)

        feature_labels = {
            "phase_inconsistency": "Phase inconsistency",
            "temporal_uncertainty": "Temporal uncertainty",
            "probe_score": "Probe bias std norm",
            "probe_relative_bias_std": "Relative bias std",
            "probe_mean_estimation_residual": "Probe residual",
            "probe_sign_disagreement": "Sign disagreement",
        }
        panel_left, panel_right = 1030, 1680
        draw.text((1160, 115), "Single-feature ROC AUC", fill="black", font=font)
        draw.line((panel_left + 0.5 * (panel_right - panel_left), 170, panel_left + 0.5 * (panel_right - panel_left), 880), fill="#999999", width=3)
        for index, (key, label) in enumerate(feature_labels.items()):
            value = analysis["features"][key]["roc_auc"]
            y = 205 + index * 110
            draw.text((800, y + 12), label, fill="black", font=small)
            draw.rectangle((panel_left, y, panel_right, y + 48), outline="#cccccc", width=2)
            if value is not None:
                color = "#2ca02c" if value >= 0.5 else "#e45756"
                draw.rectangle((panel_left, y, panel_left + value * (panel_right - panel_left), y + 48), fill=color)
                draw.text((panel_right + 15, y + 12), f"{value:.2f}", fill=color, font=small)
        draw.text((1270, 895), "Vertical reference: AUC 0.50", fill="#666666", font=small)
        draw.text((30, 995), f"run={analysis['experiment_run_id']} | preregistered directions | no threshold fitted | development only", fill="#666666", font=small)
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
