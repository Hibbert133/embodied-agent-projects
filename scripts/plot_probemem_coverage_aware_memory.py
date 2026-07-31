"""Render the real coverage-aware memory decision funnel as PNG."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "outputs/probemem_v2/coverage_aware_memory_summary.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "outputs/probemem_v2/figures/coverage_aware_memory_funnel.png",
    )
    args = parser.parse_args()
    try:
        summary = json.loads(args.summary.resolve().read_text(encoding="utf-8"))
        reasons = summary["decision_reason_counts"]
        width, height = 1500, 820
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        title = ImageFont.load_default(size=32)
        font = ImageFont.load_default(size=23)
        small = ImageFont.load_default(size=19)
        draw.text(
            (65, 42),
            "Coverage-aware verified memory: fresh development outcome",
            fill="#1f2937",
            font=title,
        )
        stages = [
            ("Operational queries", summary["operational_cases"], "#457b9d"),
            ("Skill conflict -> abstain", reasons.get("CONFLICTING_VERIFIED_EPISODES", 0), "#f4a261"),
            ("Outside coverage -> abstain", reasons.get("OUTSIDE_VERIFIED_COVERAGE", 0), "#e9c46a"),
            ("Memory used", summary["memory_use_count"], "#2a9d8f"),
            ("Accepted after use", summary["selective_accepted_count"], "#3a86ff"),
            ("Wrong-memory application", summary["wrong_memory_application_count"], "#d1495b"),
        ]
        max_count = max(count for _, count, _ in stages)
        y = 145
        for label, count, color in stages:
            bar_width = int(950 * count / max_count) if max_count else 0
            draw.text((65, y + 12), label, fill="#374151", font=font)
            draw.rounded_rectangle(
                (430, y, 430 + max(bar_width, 4), y + 55),
                radius=10,
                fill=color,
            )
            draw.text((445 + bar_width, y + 12), str(count), fill="#111827", font=font)
            y += 92
        draw.text(
            (65, height - 72),
            "Frozen gate failed: 2 memory uses, 0 accepted, 2 harmful transfers; no retuning",
            fill="#991b1b",
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
