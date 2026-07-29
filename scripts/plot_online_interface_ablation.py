"""Plot the real 2x2 model-by-interface online recovery ablation."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with args.summary_csv.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if len(rows) != 4:
        raise ValueError("2x2 ablation requires exactly four rows")
    image = Image.new("RGB", (1500, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 25), "Online recovery: model x interface development ablation", fill="black")
    left, top, right, bottom = 120, 105, 1420, 730
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    width = (right - left) / len(rows)
    max_steps = max(float(row["mean_total_recovery_environment_steps"]) for row in rows)
    for index, row in enumerate(rows):
        x = left + index * width
        rate = float(row["conditional_recovery_rate"])
        steps = float(row["mean_total_recovery_environment_steps"])
        rate_height = rate * (bottom - top)
        step_height = steps / max_steps * (bottom - top)
        draw.rectangle((x + 35, bottom - rate_height, x + 120, bottom), fill="#2563eb")
        draw.rectangle((x + 140, bottom - step_height, x + 225, bottom), fill="#dc2626")
        draw.text((x + 35, bottom - rate_height - 23), f"{rate:.0%}", fill="black")
        draw.text((x + 140, bottom - step_height - 23), f"{steps:.1f}", fill="black")
        draw.text((x + 35, bottom + 14), f"{row['model']} {row['interface']}", fill="black")
    draw.text((left, 64), "blue: conditional recovery   red: mean recovery env steps (relative)", fill="black")
    draw.text((left, 800), "Development seeds 250-254; descriptive n=5 per cell; no generalization claim.", fill="black")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, dpi=(150, 150))
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
