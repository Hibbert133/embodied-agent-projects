"""Plot the real evaluator-only ProbeMem contradiction audit."""

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
        default=ROOT / "outputs/probemem_v2/memory_contradiction_audit_summary.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "outputs/probemem_v2/figures/memory_contradiction_resonance.png",
    )
    args = parser.parse_args()
    try:
        summary = json.loads(args.summary.resolve().read_text(encoding="utf-8"))
        width, height = 1600, 900
        canvas = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(canvas)
        title = ImageFont.load_default(size=32)
        heading = ImageFont.load_default(size=25)
        font = ImageFont.load_default(size=21)
        small = ImageFont.load_default(size=18)
        draw.text((60, 40), "ProbeMem verified-memory contradiction audit", fill="#172554", font=title)
        draw.text((60, 92), "Post-hoc evaluator-only; frozen development run; no gate retuning", fill="#475569", font=small)

        draw.text((60, 155), "Decision path", fill="#1f2937", font=heading)
        decision_bars = [
            ("Operational queries", summary["operational_cases"], "#457b9d"),
            ("Local conflict -> abstain", summary["conflict_abstain_count"], "#f4a261"),
            ("Verified memory used", summary["memory_use_count"], "#2a9d8f"),
        ]
        maximum = max(item[1] for item in decision_bars)
        y = 215
        for label, count, color in decision_bars:
            draw.text((60, y + 10), label, fill="#374151", font=font)
            length = int(500 * count / maximum)
            draw.rounded_rectangle((345, y, 345 + max(5, length), y + 48), 8, fill=color)
            draw.text((365 + length, y + 10), str(count), fill="#111827", font=font)
            y += 78

        draw.text((940, 155), "Fresh resonance after memory use", fill="#1f2937", font=heading)
        resonance = summary["resonance_counts"]
        resonance_bars = [
            ("SUPPORTED", resonance.get("SUPPORTED", 0), "#2a9d8f"),
            ("UNRESOLVED", resonance.get("UNRESOLVED", 0), "#e9c46a"),
            ("CONTRADICTED", resonance.get("CONTRADICTED", 0), "#d1495b"),
        ]
        y = 215
        for label, count, color in resonance_bars:
            draw.text((940, y + 10), label, fill="#374151", font=font)
            length = 230 * count
            draw.rounded_rectangle((1190, y, 1190 + max(5, length), y + 48), 8, fill=color)
            draw.text((1210 + length, y + 10), str(count), fill="#111827", font=font)
            y += 78

        draw.text((60, 500), "Conflict cases contain every utility regime", fill="#1f2937", font=heading)
        partitions = summary["conflict_outcome_partitions_evaluator_only"]
        colors = {
            "BOTH_RECOVER": "#2a9d8f",
            "COMPENSATION_ONLY_RECOVERY": "#457b9d",
            "RETRY_ONLY_RECOVERY": "#9b5de5",
            "NEITHER_RECOVERS": "#d1495b",
        }
        x = 60
        total = sum(partitions.values())
        for label in colors:
            count = partitions.get(label, 0)
            segment = int(1150 * count / total) if total else 0
            draw.rectangle((x, 560, x + segment, 625), fill=colors[label])
            draw.text((x + 8, 578), str(count), fill="white", font=font)
            x += segment
        for index, label in enumerate(colors):
            x = 60 + (index % 2) * 690
            y = 660 + (index // 2) * 48
            draw.rectangle((x, y, x + 28, y + 28), fill=colors[label])
            draw.text((x + 40, y + 3), label, fill="#374151", font=small)

        draw.text(
            (60, 800),
            "Finding: geometric coverage and unanimous accepted neighbors did not predict reusable intervention utility.",
            fill="#991b1b",
            font=font,
        )
        args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
        canvas.save(args.output.resolve(), format="PNG", dpi=(180, 180))
        print(f"figure: {args.output.resolve()}")
        return 0
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
