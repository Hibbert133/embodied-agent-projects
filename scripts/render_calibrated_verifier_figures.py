"""Render dependency-free SVG figures for Calibrated Verifier v2."""

from __future__ import annotations
import argparse
import html
import json
from pathlib import Path


def _svg(title: str, body: str, *, width: int = 900, height: int = 520) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/><text x="30" y="35" font-family="sans-serif" font-size="22">{html.escape(title)}</text>{body}</svg>\n'''


def _bars(labels: list[str], series: list[tuple[str, list[float], str]], title: str, ylabel: str) -> str:
    maximum = max((sum(values[index] for _, values, _ in series) for index in range(len(labels))), default=1) or 1
    body = f'<text x="20" y="70" font-family="sans-serif" font-size="13">{html.escape(ylabel)}</text>'
    bar_width = 90
    for index, label in enumerate(labels):
        x, bottom = 90 + index * 180, 450
        for name, values, color in series:
            height = 340 * values[index] / maximum
            bottom -= height
            body += f'<rect x="{x}" y="{bottom}" width="{bar_width}" height="{height}" fill="{color}"><title>{html.escape(name)}: {values[index]}</title></rect>'
        body += f'<text x="{x}" y="475" font-family="sans-serif" font-size="10">{html.escape(label)}</text>'
    return _svg(title, body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    summary = json.loads((run_dir / "analysis_summary.json").read_text(encoding="utf-8"))
    figure_dir = run_dir / "figures"
    figure_dir.mkdir(exist_ok=False)
    methods = [(key, value) for key, value in summary["methods"].items() if key != "EVALUATOR_ONLY_ORACLE"]
    labels = [key.replace("_", " ") for key, _ in methods]
    recovery = [float(value.get("accepted_recovery", 0)) for _, value in methods]
    calls = [float(value.get("verifier_calls", 0)) for _, value in methods]
    max_x, max_y = max(calls, default=1) or 1, max(recovery, default=1) or 1
    points = '<line x1="80" y1="450" x2="850" y2="450" stroke="black"/><line x1="80" y1="450" x2="80" y2="70" stroke="black"/>'
    for label, x_value, y_value in zip(labels, calls, recovery):
        x, y = 80 + 740 * x_value / max_x, 450 - 350 * y_value / max_y
        points += f'<circle cx="{x}" cy="{y}" r="6" fill="#2563eb"/><text x="{x + 8}" y="{y}" font-family="sans-serif" font-size="10">{html.escape(label)}</text>'
    (figure_dir / "recovery_vs_calls.svg").write_text(_svg("Recovery versus verifier calls", points), encoding="utf-8")
    helpful = [float(value.get("helpful_overrides", 0)) for _, value in methods]
    harmful = [float(value.get("harmful_overrides", 0)) for _, value in methods]
    (figure_dir / "override_outcomes.svg").write_text(_bars(labels, [("Helpful", helpful, "#16a34a"), ("Harmful", harmful, "#dc2626")], "Override outcomes", "Count"), encoding="utf-8")
    reference = summary["reference_calibration"]
    brier = [reference["unweighted"]["pooled"]["brier"], reference["weighted"]["pooled"]["brier"]]
    (figure_dir / "reference_brier.svg").write_text(_bars(["Unweighted", "Weighted"], [("Brier", brier, "#7c3aed")], "Reference-cohort Brier score", "Lower is better"), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
