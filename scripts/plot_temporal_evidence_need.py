"""Plot Agent-visible temporal uncertainty on real development ambiguity cases."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--per-case",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/temporal_gate_development_v1/per_case.csv",
    )
    parser.add_argument(
        "--threshold",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/temporal_gate_development_v1/candidate_threshold.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/figures/temporal_uncertainty_development.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from PIL import Image, ImageDraw, ImageFont

        with args.per_case.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        threshold = float(json.loads(args.threshold.read_text(encoding="utf-8"))["threshold"])
        if not rows:
            raise ValueError("per-case CSV is empty")
        image = Image.new("RGB", (1400, 760), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=18)
        small = ImageFont.load_default(size=15)
        title = ImageFont.load_default(size=28)
        left, top, right, bottom = 120, 120, 1320, 620
        draw.text(
            (700, 35),
            "Temporal uncertainty does not yield selective evidence allocation",
            fill="#0f172a",
            font=title,
            anchor="ma",
        )
        draw.line((left, top, left, bottom), fill="#334155", width=2)
        draw.line((left, bottom, right, bottom), fill="#334155", width=2)
        minimum, maximum = 0.5, 1.0

        def y_position(value: float) -> int:
            return int(bottom - (value - minimum) / (maximum - minimum) * (bottom - top))

        threshold_y = y_position(threshold)
        draw.line((left, threshold_y, right, threshold_y), fill="#dc2626", width=3)
        draw.text(
            (right - 5, threshold_y - 8),
            f"development threshold = {threshold:.3f}",
            fill="#dc2626",
            font=font,
            anchor="rs",
        )
        for tick in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
            y = y_position(tick)
            draw.line((left - 6, y, left, y), fill="#334155", width=2)
            draw.text((left - 15, y), f"{tick:.1f}", fill="#334155", font=small, anchor="rm")
        spacing = (right - left) / len(rows)
        for index, row in enumerate(rows):
            x = int(left + (index + 0.5) * spacing)
            value = float(row["temporal_uncertainty"])
            y = y_position(value)
            color = "#2563eb" if row["mechanism_class_oracle"] == "stable_bias" else "#f59e0b"
            radius = 13
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
            if row["probe_needed_oracle"].lower() == "true":
                draw.ellipse(
                    (x - radius - 5, y - radius - 5, x + radius + 5, y + radius + 5),
                    outline="#111827",
                    width=4,
                )
            draw.text((x, bottom + 20), row["pair_id"], fill="#475569", font=small, anchor="ma")
        draw.text(
            (left, top - 25),
            "Agent-visible temporal uncertainty",
            fill="#0f172a",
            font=font,
            anchor="ls",
        )
        draw.text(
            (700, 690),
            "Blue: stable bias   Orange: stochastic noise   Black ring: probe corrects passive error",
            fill="#334155",
            font=font,
            anchor="ma",
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.output, format="PNG", dpi=(180, 180))
        print(f"figure: {args.output.resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
