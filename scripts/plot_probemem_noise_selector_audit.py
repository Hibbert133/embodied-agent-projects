"""Render the frozen-selector causal audit as PNG without optional plotting deps."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=ROOT / "outputs/probemem_v2/noise_selector_causal_audit.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "outputs/probemem_v2/figures/noise_selector_causal_audit.png",
    )
    args = parser.parse_args()
    try:
        with args.input_csv.resolve().open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        decisive = [
            row
            for row in rows
            if row["outcome_partition_evaluator_only"]
            in {"RETRY_ONLY_RECOVERY", "COMPENSATION_ONLY_RECOVERY"}
        ]
        if not decisive:
            raise ValueError("audit plot requires decisive recovery cases")

        width, height = 1600, 850
        left, right, top, bottom = 280, 80, 130, 170
        plot_width = width - left - right
        plot_height = height - top - bottom
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=24)
        small = ImageFont.load_default(size=19)
        title = ImageFont.load_default(size=31)

        xmin, xmax = math.log10(0.35), math.log10(16.0)

        def x_pixel(value: float) -> int:
            return int(left + (math.log10(value) - xmin) / (xmax - xmin) * plot_width)

        y_positions = {
            "COMPENSATION_ONLY_RECOVERY": top + int(plot_height * 0.72),
            "RETRY_ONLY_RECOVERY": top + int(plot_height * 0.28),
        }
        draw.text(
            (left, 35),
            "Frozen selector errors reveal non-monotonic intervention utility",
            fill="#1f2937",
            font=title,
        )
        draw.line((left, top, left, top + plot_height), fill="#374151", width=2)
        draw.line(
            (left, top + plot_height, left + plot_width, top + plot_height),
            fill="#374151",
            width=2,
        )
        for tick in (0.5, 1.0, 2.0, 5.0, 10.0, 15.0):
            x = x_pixel(tick)
            draw.line((x, top, x, top + plot_height), fill="#e5e7eb", width=2)
            draw.text((x - 14, top + plot_height + 18), f"{tick:g}", fill="#374151", font=small)
        for label, y in y_positions.items():
            display = "Compensation-only recovery" if label.startswith("COMP") else "Retry-only recovery"
            draw.text((20, y - 14), display, fill="#374151", font=small)
            draw.line((left, y, left + plot_width, y), fill="#d1d5db", width=2)

        threshold = float(decisive[0]["frozen_threshold"])
        tx = x_pixel(threshold)
        for y in range(top, top + plot_height, 18):
            draw.line((tx, y, tx, min(y + 10, top + plot_height)), fill="#264653", width=4)
        draw.text((tx + 10, top + 10), "frozen threshold = 2.0", fill="#264653", font=small)

        point_offsets: dict[str, int] = {row["episode_id"]: 0 for row in decisive}
        for category in y_positions:
            category_rows = sorted(
                (row for row in decisive if row["outcome_partition_evaluator_only"] == category),
                key=lambda row: x_pixel(float(row["probe_relative_bias_std"])),
            )
            for first, second in zip(category_rows, category_rows[1:]):
                if abs(
                    x_pixel(float(first["probe_relative_bias_std"]))
                    - x_pixel(float(second["probe_relative_bias_std"]))
                ) < 45:
                    point_offsets[first["episode_id"]] = -24
                    point_offsets[second["episode_id"]] = 24

        for row in decisive:
            x = x_pixel(float(row["probe_relative_bias_std"]))
            y = (
                y_positions[row["outcome_partition_evaluator_only"]]
                + point_offsets[row["episode_id"]]
            )
            correct = row["selected_accepted"].lower() == "true"
            color = "#2a9d8f" if correct else "#d1495b"
            if correct:
                draw.ellipse((x - 13, y - 13, x + 13, y + 13), fill=color, outline="black", width=2)
            else:
                draw.line((x - 15, y - 15, x + 15, y + 15), fill=color, width=8)
                draw.line((x - 15, y + 15, x + 15, y - 15), fill=color, width=8)
            draw.text((x + 10, y - 47), f"seed {row['seed']}", fill="#111827", font=small)

        draw.text(
            (left + 260, height - 82),
            "Agent-visible probe relative bias standard deviation (log scale)",
            fill="#111827",
            font=font,
        )
        draw.text(
            (left, height - 135),
            "green circle: accepted choice    red X: wrong choice    vertical jitter: display only",
            fill="#4b5563",
            font=small,
        )
        args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
        image.save(args.output.resolve(), format="PNG", dpi=(180, 180))
        print(f"figure: {args.output.resolve()}")
        return 0
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
