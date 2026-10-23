"""Render the completed ACR distributional development comparison from CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


LABELS = {
    "always_compensation": "Always\ncompensation",
    "always_retry": "Always\nretry",
    "accepted_only_last": "Accepted-only\nlast",
    "posterior_greedy": "Posterior\ngreedy",
    "posterior_abstain": "Posterior\nabstain",
}
COLORS = ("#7895CB", "#4D9078", "#D19A66", "#9C6ADE", "#C45C66")


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    names = ("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _centered(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font: ImageFont.ImageFont, fill: str) -> None:
    box = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=4)
    draw.multiline_text((xy[0] - (box[2] - box[0]) / 2, xy[1]), text, font=font, fill=fill, align="center", spacing=4)


def render(summary_csv: Path, output: Path) -> None:
    with summary_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if [row["method"] for row in rows] != list(LABELS):
        raise ValueError("method summary does not match the frozen registry")

    image = Image.new("RGB", (1600, 900), "#F8FAFC")
    draw = ImageDraw.Draw(image)
    title, subtitle = _font(40, bold=True), _font(23)
    axis, label, value = _font(21), _font(19), _font(20, bold=True)
    draw.text((80, 48), "ProbeMem-ACR distributional memory: development result", font=title, fill="#172033")
    draw.text((80, 105), "40 chronological operational cases; promotion gate failed", font=subtitle, fill="#4A5568")

    left, right, top, bottom = 105, 790, 205, 690
    draw.text((left, 160), "Fresh-verification accepted rate", font=_font(27, bold=True), fill="#172033")
    draw.line((left, bottom, right, bottom), fill="#64748B", width=2)
    draw.line((left, top, left, bottom), fill="#64748B", width=2)
    for tick in range(0, 81, 20):
        y = bottom - (bottom - top) * tick / 80
        draw.line((left, y, right, y), fill="#D7DEE8", width=1)
        draw.text((55, y - 12), f"{tick}%", font=axis, fill="#4A5568")
    width, gap = 92, 35
    for index, row in enumerate(rows):
        x = left + 40 + index * (width + gap)
        rate = float(row["accepted_rate"]) * 100
        y = bottom - (bottom - top) * rate / 80
        draw.rounded_rectangle((x, y, x + width, bottom), radius=8, fill=COLORS[index])
        _centered(draw, (x + width / 2, y - 34), f"{int(row['accepted_cases'])}/40", value, "#172033")
        _centered(draw, (x + width / 2, bottom + 18), LABELS[row["method"]], label, "#334155")

    left2, right2 = 900, 1530
    draw.text((left2, 160), "Failure cost of the decision", font=_font(27, bold=True), fill="#172033")
    draw.line((left2, bottom, right2, bottom), fill="#64748B", width=2)
    draw.line((left2, top, left2, bottom), fill="#64748B", width=2)
    max_count = 32
    for tick in range(0, 33, 8):
        y = bottom - (bottom - top) * tick / max_count
        draw.line((left2, y, right2, y), fill="#D7DEE8", width=1)
        draw.text((860, y - 12), str(tick), font=axis, fill="#4A5568")
    group_width = 105
    for index, row in enumerate(rows):
        x = left2 + 22 + index * 122
        harmful = int(row["harmful_transfer_cases"])
        abstentions = int(row["abstentions"])
        for offset, count, color in ((0, harmful, "#D97757"), (48, abstentions, "#64748B")):
            y = bottom - (bottom - top) * count / max_count
            draw.rectangle((x + offset, y, x + offset + 38, bottom), fill=color)
            if count:
                _centered(draw, (x + offset + 19, y - 27), str(count), label, "#172033")
        _centered(draw, (x + group_width / 2, bottom + 18), LABELS[row["method"]], label, "#334155")
    draw.rectangle((1060, 752, 1090, 782), fill="#D97757")
    draw.text((1102, 754), "harmful transfer", font=label, fill="#334155")
    draw.rectangle((1280, 752, 1310, 782), fill="#64748B")
    draw.text((1322, 754), "abstention", font=label, fill="#334155")
    draw.text((80, 836), "Source: immutable method_summary.csv; paired counterfactual development audit only.", font=_font(19), fill="#64748B")

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, dpi=(180, 180))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.summary_csv.resolve(), args.output.resolve())
    print(f"figure: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
