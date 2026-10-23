"""Render the real frozen ACR retry-utility replication result."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = json.loads((args.run_dir / "replication_summary.json").read_text(encoding="utf-8"))
        image = Image.new("RGB", (1500, 900), "white")
        draw = ImageDraw.Draw(image)
        draw.text((55, 40), "Prospective retry-utility replication", fill="#172554", font=_font(33))
        draw.text((55, 90), "Fresh fault_05 seeds 1400–1499; directional evidence only", fill="#475569", font=_font(19))
        left, width = 600, 700
        threshold = 0.70
        threshold_x = left + threshold * width
        draw.line((threshold_x, 165, threshold_x, 470), fill="#b91c1c", width=4)
        draw.text((threshold_x + 8, 155), "registered 0.70", fill="#b91c1c", font=_font(16))
        labels = {
            "phase_inconsistency": "Phase inconsistency",
            "probe_mean_estimation_residual": "Probe estimation residual",
        }
        for index, (feature, endpoint) in enumerate(summary["registered_endpoints"].items()):
            y = 225 + index * 145
            probability = float(endpoint["rank_probability_retry_greater"])
            color = "#2a9d8f" if endpoint["passed"] else "#d1495b"
            draw.text((55, y + 8), labels[feature], fill="#334155", font=_font(23))
            draw.rounded_rectangle((left, y, left + probability * width, y + 55), radius=10, fill=color)
            draw.text((left + probability * width + 15, y + 12), f"{probability:.3f}", fill="#111827", font=_font(20))
            ci = endpoint["bootstrap_ci95"]
            draw.text((left, y + 70), f"bootstrap 95% CI [{ci['low']:.3f}, {ci['high']:.3f}]", fill="#64748b", font=_font(16))
        partitions = summary["outcome_partitions"]
        draw.text((55, 555), "Outcome diversity", fill="#172554", font=_font(26))
        lines = [
            f"Operational pairs: {summary['operational_cases']}",
            f"Retry-only: {summary['retry_only_cases']} (minimum 8: pass)",
            f"Compensation-only: {summary['compensation_only_cases']} (minimum 8: fail)",
            f"Both recover: {partitions.get('BOTH_RECOVER', 0)}",
            f"Neither recovers: {partitions.get('NEITHER_RECOVERS', 0)}",
        ]
        for index, line in enumerate(lines):
            draw.text((55, 610 + index * 42), line, fill="#334155", font=_font(19))
        draw.text((780, 620), "REPLICATION GATE: FAILED", fill="#991b1b", font=_font(30))
        draw.text((780, 675), "No threshold, selector, GLM, validation, or held-out run authorized", fill="#991b1b", font=_font(18))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.output, format="PNG", dpi=(180, 180))
        print(f"figure: {args.output}")
        return 0
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
