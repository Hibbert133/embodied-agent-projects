"""Render figures directly from the real ProbeMem-ACR development outputs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _bar_figure(summary: dict, output: Path) -> None:
    methods = summary["method_results"]
    labels = list(methods)
    width, height = 1800, 900
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 35), "ProbeMem-ACR development: accepted recovery", fill="#172554", font=_font(32))
    maximum = max(item["operational_cases"] for item in methods.values())
    y = 120
    for name in labels:
        count = methods[name]["accepted_count"]
        length = int(1050 * count / maximum)
        color = "#2a9d8f" if name == "deterministic_action_conditional" else "#457b9d"
        draw.text((55, y + 8), name, fill="#374151", font=_font(20))
        draw.rounded_rectangle((520, y, 520 + max(4, length), y + 45), 7, fill=color)
        draw.text((540 + length, y + 8), f"{count}/{maximum}", fill="#111827", font=_font(20))
        y += 100
    draw.text((55, 830), "Development-only paired counterfactual feasibility; no online-learning claim", fill="#7f1d1d", font=_font(18))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", dpi=(180, 180))


def _risk_figure(summary: dict, output: Path) -> None:
    methods = summary["method_results"]
    width, height = 1800, 900
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 35), "Coverage and harmful transfer", fill="#172554", font=_font(32))
    y = 125
    for name, values in methods.items():
        coverage = float(values["coverage"])
        harmful = int(values["harmful_transfer_count"])
        draw.text((55, y + 5), name, fill="#374151", font=_font(20))
        draw.rectangle((520, y, 520 + int(700 * coverage), y + 32), fill="#4cc9f0")
        draw.text((1235, y + 4), f"coverage {coverage:.0%}", fill="#111827", font=_font(18))
        draw.rectangle((520, y + 42, 520 + harmful * 70, y + 74), fill="#d1495b")
        draw.text((1235, y + 46), f"harmful {harmful}", fill="#991b1b", font=_font(18))
        y += 110
    image.save(output, format="PNG", dpi=(180, 180))


def _calibration_figure(rows: list[dict[str, str]], output: Path) -> None:
    bins = [[] for _ in range(5)]
    for row in rows:
        probability = float(row["predicted_accept_probability"])
        bins[min(4, int(probability * 5))].append(row["observed_accepted"] == "True")
    width, height = 1100, 900
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 35), "Acceptance calibration", fill="#172554", font=_font(32))
    left, top, size = 120, 130, 650
    draw.line((left, top + size, left + size, top), fill="#94a3b8", width=3)
    draw.line((left, top, left, top + size), fill="#111827", width=3)
    draw.line((left, top + size, left + size, top + size), fill="#111827", width=3)
    for index, values in enumerate(bins):
        if not values:
            continue
        predicted = (index + 0.5) / 5
        observed = sum(values) / len(values)
        x = left + predicted * size
        y = top + (1.0 - observed) * size
        radius = 8 + min(22, len(values))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#d1495b")
        draw.text((x + radius + 4, y - 10), f"n={len(values)}", fill="#374151", font=_font(17))
    draw.text((left + 180, 820), "Predicted ACCEPTED probability", fill="#374151", font=_font(20))
    draw.text((left, 95), "Observed ACCEPTED rate", fill="#374151", font=_font(20))
    draw.text((85, top - 10), "1.0", fill="#64748b", font=_font(15))
    draw.text((85, top + size - 10), "0.0", fill="#64748b", font=_font(15))
    image.save(output, format="PNG", dpi=(180, 180))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="Accepted for command symmetry; summary outputs are manifest-bound")
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs/probemem_acr")
    args = parser.parse_args()
    try:
        output = args.output_root.resolve()
        summary = json.loads((output / "development_summary.json").read_text(encoding="utf-8"))
        with (output / "development_resonance_records.csv").open("r", encoding="utf-8", newline="") as handle:
            resonance = list(csv.DictReader(handle))
        figures = output / "figures"
        _bar_figure(summary, figures / "acr_recovery_comparison.png")
        _risk_figure(summary, figures / "acr_coverage_harmful_transfer.png")
        _calibration_figure(resonance, figures / "acr_acceptance_calibration.png")
        for path in sorted(figures.glob("acr_*.png")):
            print(f"figure: {path}")
        return 0
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
