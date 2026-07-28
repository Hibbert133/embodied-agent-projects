"""Plot balanced held-out diagnosis and recovery results from real CSV files."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnosis-csv", type=Path, required=True)
    parser.add_argument("--summary-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def recovery_plot(rows: list[dict[str, str]], path: Path) -> None:
    rows = [row for row in rows if row["condition"] != "all"]
    image = Image.new("RGB", (1400, 850), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 25), "Conditional recovery on balanced held-out faults", fill="black")
    left, top, right, bottom = 130, 90, 1340, 730
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    width = (right - left) / len(rows)
    for index, row in enumerate(rows):
        rate = float(row["recovery_rate"])
        low = float(row["recovery_wilson_low"])
        high = float(row["recovery_wilson_high"])
        x0 = left + (index + 0.2) * width
        x1 = left + (index + 0.8) * width
        y = bottom - rate * (bottom - top)
        draw.rectangle((x0, y, x1, bottom), fill="#2563eb")
        center_x = (x0 + x1) / 2
        y_low = bottom - low * (bottom - top)
        y_high = bottom - high * (bottom - top)
        draw.line((center_x, y_low, center_x, y_high), fill="black", width=4)
        draw.line((center_x - 12, y_low, center_x + 12, y_low), fill="black", width=4)
        draw.line((center_x - 12, y_high, center_x + 12, y_high), fill="black", width=4)
        draw.text((x0, bottom + 12), row["condition"], fill="black")
        draw.text((x0, max(top, y - 24)), f"{rate:.0%}", fill="black")
    draw.text((left, 55), "Error bars: 95% Wilson confidence interval", fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, dpi=(150, 150))


def magnitude_plot(rows: list[dict[str, str]], path: Path) -> None:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[f"{row['fault_axis']}_{row['fault_sign']}"].append(row)
    values = {
        condition: (
            float(group[0]["fault_magnitude"]),
            mean(float(row["correction_magnitude"]) for row in group),
        )
        for condition, group in grouped.items()
    }
    image = Image.new("RGB", (1400, 850), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 25), "Injected bias magnitude vs selected correction magnitude", fill="black")
    left, top, right, bottom = 130, 90, 1340, 730
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    maximum = max(max(pair) for pair in values.values()) * 1.15
    group_width = (right - left) / len(values)
    for index, (condition, (injected, correction)) in enumerate(sorted(values.items())):
        for offset, value, color in ((0.18, injected, "#dc2626"), (0.52, correction, "#16a34a")):
            x0 = left + (index + offset) * group_width
            x1 = x0 + group_width * 0.25
            y = bottom - value / maximum * (bottom - top)
            draw.rectangle((x0, y, x1, bottom), fill=color)
            draw.text((x0, y - 22), f"{value:.3f}", fill="black")
        draw.text((left + (index + 0.18) * group_width, bottom + 12), condition, fill="black")
    draw.text((right - 300, 35), "red=injected  green=correction", fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, dpi=(150, 150))


def main() -> int:
    args = parse_args()
    with args.summary_csv.open(encoding="utf-8", newline="") as file:
        summary = list(csv.DictReader(file))
    with args.diagnosis_csv.open(encoding="utf-8", newline="") as file:
        diagnosis = list(csv.DictReader(file))
    if not summary or not diagnosis:
        raise ValueError("input CSV files must be non-empty")
    output = args.output_dir.expanduser().resolve()
    recovery_plot(summary, output / "balanced_fault_recovery_rate.png")
    magnitude_plot(diagnosis, output / "bias_vs_correction_magnitude.png")
    print(f"figures: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
