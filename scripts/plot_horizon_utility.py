"""Plot real evidence-horizon accuracy, recovery, and interaction cost."""

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


def line_plot(
    draw: ImageDraw.ImageDraw,
    rows: list[dict[str, str]],
    *,
    bounds: tuple[int, int, int, int],
    field: str,
    maximum: float,
    title: str,
    color: str,
    formatter,
) -> None:
    left, top, right, bottom = bounds
    draw.text((left, top - 38), title, fill="black")
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    horizons = [int(row["horizon"]) for row in rows]
    values = [float(row[field]) for row in rows]
    max_horizon = max(horizons)
    points = [
        (
            left + horizon / max_horizon * (right - left),
            bottom - value / maximum * (bottom - top),
        )
        for horizon, value in zip(horizons, values)
    ]
    draw.line(points, fill=color, width=5)
    for (x, y), horizon, value in zip(points, horizons, values):
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color)
        draw.text((x - 12, bottom + 12), str(horizon), fill="black")
        draw.text((x - 18, y - 25), formatter(value), fill="black")


def main() -> int:
    args = parse_args()
    with args.summary_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("summary CSV is empty")
    image = Image.new("RGB", (1700, 800), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (50, 25),
        "Candidate evidence horizon under independent probe/final stochastic streams",
        fill="black",
    )
    line_plot(
        draw,
        rows,
        bounds=(100, 140, 800, 650),
        field="conditional_recovery_rate",
        maximum=1.0,
        title="Selected-candidate full recovery rate",
        color="#E45756",
        formatter=lambda value: f"{value:.0%}",
    )
    maximum_cost = max(
        float(row["mean_total_recovery_environment_steps"]) for row in rows
    )
    line_plot(
        draw,
        rows,
        bounds=(950, 140, 1650, 650),
        field="mean_total_recovery_environment_steps",
        maximum=maximum_cost * 1.05,
        title="Mean total recovery environment steps",
        color="#4C78A8",
        formatter=lambda value: f"{value:.0f}",
    )
    draw.text((310, 700), "Candidate evidence horizon (steps)", fill="black")
    draw.text((1160, 700), "Candidate evidence horizon (steps)", fill="black")
    draw.text(
        (50, 755),
        "Six frozen tuning cases; common random numbers within probes, independent final stream.",
        fill="black",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, dpi=(180, 180))
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
