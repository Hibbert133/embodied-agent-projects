"""Render marginal versus state-conditional retry identifiability."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "first_observed_progress": "First progress",
    "negative_first_final_object_goal_distance": "Negative final distance",
    "categorical_status": "Categorical status",
}


def render(summary_path: Path, output_path: Path) -> None:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    image = Image.new("RGB", (1400, 850), "white")
    draw = ImageDraw.Draw(image)
    title = ImageFont.load_default(size=28)
    font = ImageFont.load_default(size=22)
    small = ImageFont.load_default(size=18)
    left, right, top, bottom = 150, 1320, 150, 700
    draw.text((275, 45), "Does first-retry feedback predict an independent retry?", fill="black", font=title)
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = bottom - tick * (bottom - top)
        draw.line((left, y, right, y), fill="#d1d5db", width=1)
        draw.text((85, y - 12), f"{tick:.2f}", fill="black", font=small)
    group_width = (right - left) / len(LABELS)
    colors = ("#60a5fa", "#f97316")
    for index, (name, label) in enumerate(LABELS.items()):
        values = (summary["analyses"][name]["marginal_roc_auc"], summary["analyses"][name]["conditional"]["observed_auc"])
        center = left + group_width * (index + 0.5)
        for offset, (value, color) in enumerate(zip(values, colors)):
            x0 = center - 100 + offset * 110
            y0 = bottom - float(value) * (bottom - top)
            draw.rectangle((x0, y0, x0 + 90, bottom), fill=color)
            draw.text((x0 + 12, y0 - 30), f"{value:.3f}", fill="black", font=small)
        draw.text((center - 150, bottom + 20), label, fill="black", font=small)
    draw.rectangle((850, 105, 880, 130), fill=colors[0])
    draw.text((890, 105), "Marginal ROC AUC", fill="black", font=small)
    draw.rectangle((1080, 105, 1110, 130), fill=colors[1])
    draw.text((1120, 105), "Within-state AUC", fill="black", font=small)
    draw.text((420, 785), "Within-state result: 9 informative states, 14 positive-negative pairs", fill="black", font=font)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, dpi=(180, 180))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=ROOT / "outputs/probemem_acr/conditional_retry_audit_v1/conditional_retry_summary.json")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/probemem_acr/figures/conditional_retry_identifiability_v1.png")
    args = parser.parse_args()
    render(args.summary.resolve(), args.output.resolve())
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
