"""Render the evaluator-only retry-value cost/recovery frontier."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "first_observed_progress": "First progress",
    "negative_first_final_distance": "Negative final distance",
    "categorical_status": "Categorical status",
}


def render(input_dir: Path, output_path: Path) -> None:
    summary = json.loads((input_dir / "retry_value_summary.json").read_text(encoding="utf-8"))
    with (input_dir / "retry_cost_recovery_frontier.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    width, height = 1400, 900
    left, top, right, bottom = 130, 110, 1340, 760
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=24)
    small = ImageFont.load_default(size=20)
    colors = {
        "first_observed_progress": "#2563eb",
        "negative_first_final_distance": "#dc2626",
        "categorical_status": "#059669",
    }
    all_rows = [row for row in rows if row["score_name"] in LABELS]
    max_steps = max(int(row["additional_environment_steps"]) for row in all_rows)
    max_recovered = max(int(row["recovered_cases"]) for row in all_rows)
    to_x = lambda value: left + (right - left) * value / max_steps  # noqa: E731
    to_y = lambda value: bottom - (bottom - top) * value / max_recovered  # noqa: E731
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    for tick in range(0, max_recovered + 1, 5):
        y = to_y(tick)
        draw.line((left - 8, y, right, y), fill="#d1d5db", width=1)
        draw.text((left - 55, y - 12), str(tick), fill="black", font=small)
    for tick in range(0, max_steps + 1, 2000):
        x = to_x(tick)
        draw.line((x, bottom, x, bottom + 8), fill="black", width=2)
        draw.text((x - 35, bottom + 15), str(tick), fill="black", font=small)
    for name, label in LABELS.items():
        selected = [row for row in rows if row["score_name"] == name]
        selected.sort(key=lambda row: int(row["additional_environment_steps"]))
        points = [
            (to_x(int(row["additional_environment_steps"])), to_y(int(row["recovered_cases"])))
            for row in selected
        ]
        draw.line(points, fill=colors[name], width=4)
        for x, y in points:
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=colors[name])
    draw.text((270, 35), "Retry-value identifiability: descriptive cost-recovery frontiers", fill="black", font=font)
    draw.text((470, 825), "Additional retry environment steps (evaluator-only)", fill="black", font=small)
    y_label = Image.new("RGBA", (260, 45), (255, 255, 255, 0))
    ImageDraw.Draw(y_label).text((0, 0), "Recovered cases / 30", fill="black", font=small)
    y_label = y_label.rotate(90, expand=True)
    image.paste(y_label, (25, 320), y_label)
    legend_y = 120
    for name, label in LABELS.items():
        draw.line((850, legend_y + 10, 900, legend_y + 10), fill=colors[name], width=5)
        draw.text((915, legend_y), f"{label} (AUC={summary['scores'][name]['roc_auc']:.3f})", fill="black", font=small)
        legend_y += 35
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, dpi=(180, 180))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "outputs/probemem_acr/retry_value_audit_v1")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/probemem_acr/figures/retry_value_identifiability_v1.png")
    args = parser.parse_args()
    render(args.input_dir.resolve(), args.output.resolve())
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
