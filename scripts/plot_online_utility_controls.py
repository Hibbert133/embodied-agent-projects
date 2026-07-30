"""Plot recovery and interaction-cost controls from a real utility-Agent CSV."""

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


def draw_panel(
    draw: ImageDraw.ImageDraw,
    rows: list[dict[str, str]],
    *,
    bounds: tuple[int, int, int, int],
    value_field: str,
    maximum: float,
    title: str,
    formatter,
) -> None:
    left, top, right, bottom = bounds
    draw.text((left, top - 38), title, fill="black")
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    width = (right - left) / len(rows)
    colors = ("#4C78A8", "#F58518", "#54A24B", "#E45756", "#8C6BB1")
    for index, row in enumerate(rows):
        value = float(row[value_field])
        bar_left = left + index * width + 28
        bar_right = left + (index + 1) * width - 28
        bar_height = value / maximum * (bottom - top)
        draw.rectangle(
            (bar_left, bottom - bar_height, bar_right, bottom),
            fill=colors[index % len(colors)],
        )
        draw.text(
            (bar_left, bottom - bar_height - 22), formatter(value), fill="black"
        )
        label = row["method"].replace("_", " ")
        draw.text((bar_left, bottom + 14), label, fill="black")


def main() -> int:
    args = parse_args()
    with args.summary_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("summary CSV is empty")
    image = Image.new("RGB", (1800, 850), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (55, 25),
        "Online candidate-utility Agent: frozen six-case development controls",
        fill="black",
    )
    draw_panel(
        draw,
        rows,
        bounds=(90, 135, 850, 700),
        value_field="conditional_recovery_rate",
        maximum=1.0,
        title="Conditional recovery rate",
        formatter=lambda value: f"{value:.1%}",
    )
    maximum_steps = max(
        float(row["mean_total_recovery_environment_steps"]) for row in rows
    )
    draw_panel(
        draw,
        rows,
        bounds=(990, 135, 1750, 700),
        value_field="mean_total_recovery_environment_steps",
        maximum=maximum_steps * 1.08,
        title="Mean recovery environment steps (lower is better)",
        formatter=lambda value: f"{value:.1f}",
    )
    draw.text(
        (55, 800),
        "Online GLM-5.1 matches probe-greedy (6/6 choices); tuning evidence only, not held-out.",
        fill="black",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, dpi=(180, 180))
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
