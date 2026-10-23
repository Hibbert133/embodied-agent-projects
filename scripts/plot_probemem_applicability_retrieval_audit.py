"""Render the ProbeMem retrieval feasibility audit as a compact PNG table."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]


def _short_skill(value: str) -> str:
    return "retry" if value == "INDEPENDENT_STOCHASTIC_RETRY" else "compensation"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=ROOT / "outputs/probemem_v2/applicability_retrieval_audit.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "outputs/probemem_v2/figures/applicability_retrieval_audit.png",
    )
    args = parser.parse_args()
    try:
        with args.input_csv.resolve().open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            raise ValueError("retrieval plot requires audit rows")
        width, row_height = 1500, 72
        height = 210 + row_height * len(rows)
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        title = ImageFont.load_default(size=31)
        font = ImageFont.load_default(size=22)
        small = ImageFont.load_default(size=18)
        draw.text(
            (55, 35),
            "Historical nearest-reference retrieval under later noise cases",
            fill="#1f2937",
            font=title,
        )
        headers = ("query seed", "reference seed", "distance", "retrieved", "actual", "result")
        x_positions = (70, 275, 500, 690, 970, 1250)
        for x, header in zip(x_positions, headers):
            draw.text((x, 115), header, fill="#374151", font=font)
        draw.line((50, 155, width - 50, 155), fill="#374151", width=3)
        for index, row in enumerate(rows):
            y = 175 + index * row_height
            correct = row["retrieval_correct_evaluator_only"].lower() == "true"
            background = "#e8f5f1" if correct else "#fdecee"
            draw.rounded_rectangle(
                (45, y - 8, width - 45, y + 48), radius=8, fill=background
            )
            values = (
                row["query_seed"],
                row["reference_seed"],
                f"{float(row['standardized_distance']):.3f}",
                _short_skill(row["retrieved_skill_evaluator_only"]),
                _short_skill(row["target_skill_evaluator_only"]),
                "correct" if correct else "wrong",
            )
            for x, value in zip(x_positions, values):
                draw.text(
                    (x, y + 5),
                    value,
                    fill="#13795b" if correct else "#b4233c",
                    font=small,
                )
        draw.text(
            (55, height - 42),
            "Post-hoc evaluator-only reference labels; not actionable Verified Episodic Memory",
            fill="#6b7280",
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
