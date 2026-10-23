"""Render immutable resonance validation recovery and interaction cost."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


LABELS = {
    "single_retry": "Single\nretry", "repeat_retry": "Always\nrepeat",
    "switch_compensation": "Always\nswitch", "status_conditioned": "Frozen status\nrule",
    "rejection_abstain": "Reject ->\nabstain", "oracle_second": "Oracle\naudit",
}
COLORS = ("#7895CB", "#D19A66", "#C45C66", "#4D9078", "#8B7AC8", "#9D755D")


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    for name in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _center(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font: ImageFont.ImageFont) -> None:
    box = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=4)
    draw.multiline_text((x - (box[2] - box[0]) / 2, y), text, font=font, fill="#334155", align="center", spacing=4)


def render(summary_csv: Path, output: Path) -> None:
    with summary_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if [row["method"] for row in rows] != list(LABELS):
        raise ValueError("validation summary differs from frozen method order")
    image = Image.new("RGB", (1700, 900), "#F8FAFC")
    draw = ImageDraw.Draw(image)
    draw.text((70, 42), "ProbeMem-ACR independent validation", font=_font(40, bold=True), fill="#172033")
    draw.text((70, 100), "Frozen attempt-level status rule; held-out seeds 3100-3199 untouched", font=_font(22), fill="#4A5568")
    panels = ((90, 790, "Final accepted recovery", "final_accepted_rate", 100.0, "%"),
              (910, 1610, "Mean online environment steps", "mean_total_online_environment_steps", 1100.0, ""))
    top, bottom, width, gap = 215, 680, 74, 33
    for left, right, title, field, scale, suffix in panels:
        draw.text((left, 160), title, font=_font(26, bold=True), fill="#172033")
        draw.line((left, bottom, right, bottom), fill="#64748B", width=2)
        draw.line((left, top, left, bottom), fill="#64748B", width=2)
        for tick in range(6):
            fraction = tick / 5
            y = bottom - (bottom - top) * fraction
            draw.line((left, y, right, y), fill="#D7DEE8", width=1)
            draw.text((left - 68, y - 11), f"{scale * fraction:.0f}{suffix}", font=_font(17), fill="#4A5568")
        for index, row in enumerate(rows):
            value = float(row[field]) * (100.0 if field == "final_accepted_rate" else 1.0)
            x = left + 24 + index * (width + gap)
            y = bottom - (bottom - top) * value / scale
            draw.rounded_rectangle((x, y, x + width, bottom), radius=7, fill=COLORS[index])
            _center(draw, x + width / 2, y - 29, f"{value:.1f}{suffix}" if suffix else f"{value:.0f}", _font(17, bold=True))
            _center(draw, x + width / 2, bottom + 17, LABELS[row["method"]], _font(16))
    draw.text((70, 850), "Source: immutable validation manifest and real MuJoCo rollouts; Oracle is evaluator-only.", font=_font(18), fill="#64748B")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, dpi=(180, 180))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.run_dir.resolve() / "method_summary.csv", args.output.resolve())
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
