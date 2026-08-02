"""Render contextual utility recovery and decision-change results from artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


LABELS = {
    "always_compensation": "Always\ncompensation",
    "always_retry": "Always\nretry",
    "accepted_only_last": "Accepted-only\nlast",
    "posterior_greedy": "Global\nposterior",
    "contextual_greedy": "Contextual\ngreedy",
    "contextual_abstain": "Contextual\nabstain",
}
COLORS = ("#7895CB", "#4D9078", "#D19A66", "#8B7AC8", "#4776B4", "#C45C66")


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    names = ("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _center(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, font: ImageFont.ImageFont) -> None:
    box = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=4)
    draw.multiline_text((x - (box[2] - box[0]) / 2, y), text, font=font, fill="#334155", align="center", spacing=4)


def render(summary_csv: Path, changes_json: Path, output: Path) -> None:
    with summary_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if [row["method"] for row in rows] != list(LABELS):
        raise ValueError("contextual method summary differs from the frozen registry")
    changes = json.loads(changes_json.read_text(encoding="utf-8"))
    image = Image.new("RGB", (1600, 900), "#F8FAFC")
    draw = ImageDraw.Draw(image)
    draw.text((75, 48), "ProbeMem-ACR contextual action utility: development result", font=_font(39, bold=True), fill="#172033")
    draw.text((75, 105), "60 chronological cases; contextual decisions changed behavior but not net recovery", font=_font(22), fill="#4A5568")

    left, right, top, bottom = 100, 940, 205, 690
    draw.text((left, 160), "Fresh-verification accepted rate", font=_font(27, bold=True), fill="#172033")
    draw.line((left, bottom, right, bottom), fill="#64748B", width=2)
    draw.line((left, top, left, bottom), fill="#64748B", width=2)
    for tick in range(0, 81, 20):
        y = bottom - (bottom - top) * tick / 80
        draw.line((left, y, right, y), fill="#D7DEE8", width=1)
        draw.text((50, y - 12), f"{tick}%", font=_font(20), fill="#4A5568")
    width, gap = 92, 38
    for index, row in enumerate(rows):
        x = left + 35 + index * (width + gap)
        rate = float(row["accepted_rate"]) * 100
        y = bottom - (bottom - top) * rate / 80
        draw.rounded_rectangle((x, y, x + width, bottom), radius=8, fill=COLORS[index])
        _center(draw, x + width / 2, y - 32, f"{row['accepted_cases']}/60", _font(19, bold=True))
        _center(draw, x + width / 2, bottom + 18, LABELS[row["method"]], _font(18))

    left2, top2 = 1040, 235
    draw.text((1000, 160), "Contextual vs global decision changes", font=_font(27, bold=True), fill="#172033")
    items = (
        ("Helpful", int(changes["helpful_changes"]), "#4D9078"),
        ("Harmful", int(changes["harmful_changes"]), "#D97757"),
        ("Neutral", int(changes["neutral_changes"]), "#7895CB"),
    )
    maximum = max(value for _, value, _ in items)
    for index, (name, value, color) in enumerate(items):
        y = top2 + index * 125
        draw.text((left2, y + 15), name, font=_font(23, bold=True), fill="#334155")
        draw.rounded_rectangle((left2 + 125, y, left2 + 125 + 390 * value / maximum, y + 65), radius=8, fill=color)
        draw.text((left2 + 535, y + 14), str(value), font=_font(25, bold=True), fill="#172033")
    draw.text((1000, 640), f"17 changes = {changes['helpful_changes']} helpful + {changes['harmful_changes']} harmful + {changes['neutral_changes']} neutral", font=_font(20), fill="#4A5568")
    draw.text((75, 835), "Source: immutable contextual method summary and matched decision-change audit; development only.", font=_font(18), fill="#64748B")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, dpi=(180, 180))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-csv", type=Path, required=True)
    parser.add_argument("--changes-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.summary_csv.resolve(), args.changes_json.resolve(), args.output.resolve())
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
