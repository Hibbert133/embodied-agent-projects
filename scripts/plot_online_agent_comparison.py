"""Plot online-agent and deterministic recovery summaries from real CSVs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-summary", type=Path, required=True)
    parser.add_argument("--skills-summary", type=Path, required=True)
    parser.add_argument("--deterministic-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def first_row(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f"empty summary: {path}")
    return rows[0]


def main() -> int:
    args = parse_args()
    raw = first_row(args.raw_summary)
    skills = first_row(args.skills_summary)
    with args.deterministic_summary.open(encoding="utf-8", newline="") as file:
        deterministic_rows = list(csv.DictReader(file))
    deterministic = next(
        row for row in deterministic_rows if row["method"] == "simultaneous"
    )
    rows = [
        ("GLM-5.1 raw", float(raw["conditional_recovery_rate"]),
         float(raw["mean_total_recovery_environment_steps"])),
        ("GLM-5.2 skills", float(skills["conditional_recovery_rate"]),
         float(skills["mean_total_recovery_environment_steps"])),
        ("deterministic", float(deterministic["conditional_recovery_rate"]),
         float(deterministic["mean_total_environment_steps"])),
    ]
    image = Image.new("RGB", (1400, 850), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 25), "Development pilot: recovery and interaction cost", fill="black")
    left, top, right, bottom = 130, 100, 1320, 700
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    group_width = (right - left) / len(rows)
    max_steps = max(row[2] for row in rows)
    for index, (name, rate, steps) in enumerate(rows):
        x = left + index * group_width
        rate_height = rate * (bottom - top)
        step_height = steps / max_steps * (bottom - top)
        draw.rectangle((x + 50, bottom - rate_height, x + 145, bottom), fill="#2563eb")
        draw.rectangle((x + 170, bottom - step_height, x + 265, bottom), fill="#dc2626")
        draw.text((x + 50, bottom - rate_height - 24), f"{rate:.0%}", fill="black")
        draw.text((x + 170, bottom - step_height - 24), f"{steps:.1f}", fill="black")
        draw.text((x + 45, bottom + 15), name, fill="black")
    draw.text((left, 62), "blue: recovery rate   red: mean recovery environment steps (relative)", fill="black")
    draw.text((left, 760), "Development seeds 250-254; model and interface both differ between GLM bars.", fill="black")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, dpi=(150, 150))
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
