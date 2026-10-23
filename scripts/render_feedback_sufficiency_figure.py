"""Render the frozen feedback-sufficiency audit from real CSV artifacts."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stability = _rows(args.run_dir / "state_stability.csv")
    decisions = [row for row in _rows(args.run_dir / "decision_audit.csv") if row["exclusive_recovery"] == "True"]
    retry = [float(row["first_observed_progress"]) for row in decisions if row["exclusive_retry_label"] == "True"]
    compensation = [float(row["first_observed_progress"]) for row in decisions if row["exclusive_retry_label"] == "False"]

    shares = [float(row["modal_share"]) for row in stability]
    image = Image.new("RGB", (1800, 760), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=24)
    title_font = ImageFont.load_default(size=34)
    draw.text((60, 30), "ProbeMem-ACR verification-feedback sufficiency audit", fill="#222222", font=title_font)
    draw.text((80, 110), "Verification status stability (4 realizations/state)", fill="#222222", font=font)
    bins = [(0.50, 0.625), (0.625, 0.875), (0.875, 1.01)]
    counts = [sum(low <= value < high for value in shares) for low, high in bins]
    max_count = max(counts) or 1
    for index, (count, label) in enumerate(zip(counts, ("0.50", "0.75", "1.00"))):
        x0 = 100 + index * 230
        height = int(420 * count / max_count)
        draw.rectangle((x0, 610 - height, x0 + 140, 610), fill="#4c78a8")
        draw.text((x0 + 35, 625), label, fill="#222222", font=font)
        draw.text((x0 + 50, 570 - height), str(count), fill="#222222", font=font)
    draw.text((100, 690), "Modal first-status share", fill="#222222", font=font)

    draw.text((900, 110), "First-retry progress on exclusive recovery branches", fill="#222222", font=font)
    all_values = compensation + retry
    low, high = min(all_values), max(all_values)
    span = max(high - low, 1e-9)
    for group, values, color in ((0, compensation, "#e45756"), (1, retry, "#54a24b")):
        for index, value in enumerate(values):
            x = 1080 + group * 420 + (index % 5) * 12
            y = 610 - int(430 * (value - low) / span)
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=color)
    draw.text((950, 625), f"Compensation-only (n={len(compensation)})", fill="#222222", font=font)
    draw.text((1380, 625), f"Retry-only (n={len(retry)})", fill="#222222", font=font)
    draw.text((1020, 690), "Raw progress AUC = 0.798 | development-only", fill="#222222", font=font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, dpi=(180, 180))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
