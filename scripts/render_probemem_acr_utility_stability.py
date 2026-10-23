"""Render the frozen ACR utility-realization stability result."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path,
        default=Path("outputs/probemem_acr/figures/acr_utility_realization_stability.png"),
    )
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    summary = json.loads((run_dir / "utility_stability_summary.json").read_text(encoding="utf-8"))
    with (run_dir / "utility_stability_cases.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = sorted(csv.DictReader(handle), key=lambda row: float(row["compensation_minus_retry_utility"]))

    seeds = [row["seed"] for row in rows]
    compensation = [float(row["compensation_accept_rate"]) * 100 for row in rows]
    retry = [float(row["retry_accept_rate"]) * 100 for row in rows]
    margins = [float(row["compensation_minus_retry_utility"]) for row in rows]
    colors = ["#31688e" if value >= 0 else "#d1495b" for value in margins]

    reliability = summary["leave_one_realization_out"]
    image = Image.new("RGB", (1800, 1200), "white")
    draw = ImageDraw.Draw(image)
    title = _font(38, bold=True)
    body = _font(24)
    small = _font(19)
    draw.text((80, 35), "ProbeMem-ACR: intervention utility changes across stochastic realizations", fill="#152536", font=title)
    draw.text(
        (80, 90),
        f"Winner reversals {summary['realization_winner_reversal_cases']}/{summary['operational_cases']} | "
        f"LOO reliability {100 * reliability['winner_reliability']:.1f}% "
        f"(95% CI {100 * reliability['bootstrap_ci95']['low']:.1f}-{100 * reliability['bootstrap_ci95']['high']:.1f}%) | GATE FAILED",
        fill="#9b1c31", font=body,
    )

    left, right = 135, 1720
    upper_top, upper_bottom = 175, 565
    lower_top, lower_bottom = 710, 1080
    spacing = (right - left) / (len(rows) - 1)
    points = [left + index * spacing for index in range(len(rows))]
    for percent in (0, 25, 50, 75, 100):
        y = upper_bottom - percent / 100 * (upper_bottom - upper_top)
        draw.line((left, y, right, y), fill="#d8dee5", width=2)
        draw.text((65, y - 13), f"{percent}%", fill="#34495e", font=small)
    draw.text((135, 140), "Accepted rate across six independent realizations", fill="#152536", font=body)
    for values, color, shape in ((compensation, "#31688e", "circle"), (retry, "#e07a2d", "square")):
        series = [(x, upper_bottom - value / 100 * (upper_bottom - upper_top)) for x, value in zip(points, values)]
        draw.line(series, fill=color, width=5)
        for x, y in series:
            if shape == "circle":
                draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=color)
            else:
                draw.rectangle((x - 7, y - 7, x + 7, y + 7), fill=color)
    draw.line((1280, 155, 1335, 155), fill="#31688e", width=5)
    draw.text((1345, 141), "Bounded compensation", fill="#31688e", font=small)
    draw.line((1280, 185, 1335, 185), fill="#e07a2d", width=5)
    draw.text((1345, 171), "Independent retry", fill="#e07a2d", font=small)

    draw.text((135, 665), "Mean status-utility margin (compensation minus retry)", fill="#152536", font=body)
    center = (lower_top + lower_bottom) / 2
    scale = (lower_bottom - lower_top) / 2
    for value in (-1.0, -0.5, 0.0, 0.5, 1.0):
        y = center - value * scale
        draw.line((left, y, right, y), fill="#d8dee5" if value else "#333333", width=2)
        draw.text((65, y - 13), f"{value:+.1f}", fill="#34495e", font=small)
    for threshold in (-0.2, 0.2):
        y = center - threshold * scale
        for start in range(left, right, 20):
            draw.line((start, y, min(start + 10, right), y), fill="#777777", width=2)
    bar_width = max(12, int(spacing * 0.55))
    for x, margin, color in zip(points, margins, colors):
        y = center - margin * scale
        draw.rectangle((x - bar_width / 2, min(center, y), x + bar_width / 2, max(center, y)), fill=color)
    for x, seed in zip(points, seeds):
        draw.text((x - 20, 1090), seed, fill="#34495e", font=small)
    draw.text((80, 1135), "Blue: compensation higher expected utility | Red: retry higher expected utility | dashed: stable margin +/-0.20", fill="#34495e", font=small)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, dpi=(180, 180))
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
