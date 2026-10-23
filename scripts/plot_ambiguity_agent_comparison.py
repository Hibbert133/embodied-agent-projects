"""Plot the real held-out ambiguity-agent comparison CSV."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary-csv",
        type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/agent_comparison_v1/summary.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/figures/heldout_method_comparison.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from PIL import Image, ImageDraw, ImageFont

        with args.summary_csv.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            raise ValueError("summary CSV is empty")
        labels = [row["method"] for row in rows]
        accuracies = [100.0 * float(row["balanced_accuracy"]) for row in rows]
        steps = [int(row["probe_environment_steps"]) for row in rows]
        colors = ["#64748b", "#2563eb", "#f59e0b", "#7c3aed"]
        image = Image.new("RGB", (1600, 720), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=20)
        title_font = ImageFont.load_default(size=28)
        draw.text(
            (800, 28),
            "Bias-noise ambiguity pilot: accuracy-evidence trade-off",
            fill="#0f172a",
            font=title_font,
            anchor="ma",
        )

        def panel(
            left: int,
            title: str,
            values: list[float],
            maximum: float,
            value_suffix: str,
        ) -> None:
            top, right, bottom = 125, left + 690, 590
            axis_left, axis_right = left + 85, right - 20
            draw.text(
                ((left + right) // 2, 85), title, fill="#0f172a", font=font, anchor="ma"
            )
            draw.line((axis_left, top, axis_left, bottom), fill="#334155", width=2)
            draw.line((axis_left, bottom, axis_right, bottom), fill="#334155", width=2)
            slot = (axis_right - axis_left) / len(values)
            for index, (label, value) in enumerate(zip(labels, values)):
                bar_left = int(axis_left + index * slot + 22)
                bar_right = int(axis_left + (index + 1) * slot - 22)
                bar_top = int(bottom - (bottom - top) * value / maximum)
                draw.rectangle(
                    (bar_left, bar_top, bar_right, bottom), fill=colors[index]
                )
                text = f"{value:.0f}{value_suffix}"
                draw.text(
                    ((bar_left + bar_right) // 2, bar_top - 12),
                    text,
                    fill="#0f172a",
                    font=font,
                    anchor="ms",
                )
                draw.text(
                    ((bar_left + bar_right) // 2, bottom + 24),
                    label,
                    fill="#334155",
                    font=ImageFont.load_default(size=15),
                    anchor="ma",
                )

        panel(45, "Mechanism diagnosis (4 held-out cases)", accuracies, 110.0, "%")
        panel(835, "Additional diagnostic evidence cost", [float(x) for x in steps], 280.0, "")
        draw.text(
            (800, 690),
            "Source: real held-out summary.csv; tuning-frozen thresholds; no API calls",
            fill="#475569",
            font=ImageFont.load_default(size=16),
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
