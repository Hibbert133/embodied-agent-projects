"""Create SVG charts from the real perturbation summary CSV."""

from __future__ import annotations

import argparse
import csv
import html
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "outputs" / "perturbation_summary.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "perturbation_plots"
COLORS = {
    "action_scale": "#2563eb",
    "gaussian_noise": "#16a34a",
    "action_bias": "#dc2626",
}
LABELS = {
    "action_scale": "Action scale",
    "gaussian_noise": "Gaussian noise",
    "action_bias": "Action bias",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.expanduser().resolve().open("r", encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
    except OSError as exc:
        raise RuntimeError(f"cannot read summary CSV: {path}") from exc
    if not rows:
        raise ValueError("summary CSV contains no result rows")
    return rows


def create_chart(
    rows: list[dict[str, str]],
    *,
    metric: str,
    title: str,
    y_label: str,
    y_max: float,
    percentage: bool,
    output: Path,
) -> None:
    width, height = 960, 600
    left, right, top, bottom = 90, 35, 65, 85
    plot_width = width - left - right
    plot_height = height - top - bottom
    groups = {
        name: sorted(
            (row for row in rows if row["perturbation_type"] == name),
            key=lambda row: float(row["perturbation_level"]),
        )
        for name in COLORS
    }
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2}" y="34" text-anchor="middle" font-family="sans-serif" font-size="24" font-weight="bold">{html.escape(title)}</text>',
    ]
    for tick in range(6):
        value = y_max * tick / 5
        y = top + plot_height * (1 - tick / 5)
        label = f"{value * 100:.0f}%" if percentage else f"{value:.0f}"
        elements.extend(
            [
                f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" stroke="#e5e7eb"/>',
                f'<text x="{left - 12}" y="{y + 5:.1f}" text-anchor="end" font-family="sans-serif" font-size="13">{label}</text>',
            ]
        )
    elements.append(
        f'<text transform="translate(22 {top + plot_height / 2}) rotate(-90)" text-anchor="middle" font-family="sans-serif" font-size="15">{html.escape(y_label)}</text>'
    )
    for group_index, (name, group) in enumerate(groups.items()):
        if not group:
            continue
        x_start = left + group_index * plot_width / 3
        group_width = plot_width / 3
        points: list[str] = []
        for index, row in enumerate(group):
            x = x_start + group_width * (index + 0.5) / len(group)
            value = float(row[metric])
            y = top + plot_height * (1 - min(value, y_max) / y_max)
            points.append(f"{x:.1f},{y:.1f}")
            level = float(row["perturbation_level"])
            value_label = f"{value * 100:.0f}%" if percentage else f"{value:.1f}"
            elements.extend(
                [
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{COLORS[name]}"/>',
                    f'<text x="{x:.1f}" y="{top + plot_height + 22}" text-anchor="middle" font-family="sans-serif" font-size="11">{level:g}</text>',
                    f'<text x="{x:.1f}" y="{y - 9:.1f}" text-anchor="middle" font-family="sans-serif" font-size="10" fill="{COLORS[name]}">{value_label}</text>',
                ]
            )
        elements.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{COLORS[name]}" stroke-width="2.5"/>'
        )
        elements.append(
            f'<text x="{x_start + group_width / 2:.1f}" y="{height - 27}" text-anchor="middle" font-family="sans-serif" font-size="14" font-weight="bold" fill="{COLORS[name]}">{LABELS[name]}</text>'
        )
    elements.append("</svg>")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(elements), encoding="utf-8")


def main() -> int:
    args = parse_args()
    rows = load_rows(args.input_csv)
    output_dir = args.output_dir.expanduser().resolve()
    charts = (
        ("success_rate", "Success Rate by Perturbation Strength", "Success rate", 1.0, True, "success_rate.svg"),
        ("average_steps", "Average Episode Steps", "Average steps", 500.0, False, "average_steps.svg"),
        ("clip_fraction", "Executed-Action Clipping Fraction", "Clip fraction", 0.65, True, "clip_fraction.svg"),
    )
    for metric, title, y_label, y_max, percentage, filename in charts:
        output = output_dir / filename
        create_chart(
            rows,
            metric=metric,
            title=title,
            y_label=y_label,
            y_max=y_max,
            percentage=percentage,
            output=output,
        )
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
