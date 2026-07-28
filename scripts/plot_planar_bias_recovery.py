"""Plot planar-bias recovery rate and interaction cost from real summaries."""

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
        rows = [row for row in csv.DictReader(file) if int(row["evaluated_failures"]) > 0]
    if not rows:
        raise ValueError("summary contains no evaluated failures")
    image = Image.new("RGB", (1500, 850), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 25), "Held-out 2-D bias recovery: success and interaction cost", fill="black")
    left, top, right, bottom = 120, 100, 1420, 700
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    group_width = (right - left) / len(rows)
    max_steps = max(float(row["mean_total_environment_steps"]) for row in rows)
    for index, row in enumerate(rows):
        x = left + index * group_width
        recovery = float(row["conditional_recovery_rate"])
        steps = float(row["mean_total_environment_steps"])
        recovery_height = recovery * (bottom - top)
        step_height = steps / max_steps * (bottom - top)
        draw.rectangle((x + 35, bottom - recovery_height, x + 120, bottom), fill="#2563eb")
        draw.rectangle((x + 140, bottom - step_height, x + 225, bottom), fill="#dc2626")
        draw.text((x + 35, bottom - recovery_height - 22), f"{recovery:.0%}", fill="black")
        draw.text((x + 140, bottom - step_height - 22), f"{steps:.1f}", fill="black")
        draw.text((x + 25, bottom + 15), row["method"], fill="black")
    draw.text((left, 62), "blue: conditional recovery rate   red: mean total env steps (relative scale)", fill="black")
    draw.text((left, 755), "Total steps include 32 active-probe steps; sequential includes prior failed repair rollout.", fill="black")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, dpi=(150, 150))
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
