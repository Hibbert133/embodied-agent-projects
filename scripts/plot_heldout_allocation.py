"""Plot the frozen held-out evidence-allocation cost-performance frontier."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METHOD_LABELS = {
    "passive": "Passive",
    "seeded_random_probe": "Random probe",
    "always_probe": "Always probe",
    "global_temporal_gate": "Global gate",
    "frozen_phase_conditioned_gate": "Phase gate (selected)",
    "oracle_audit": "Oracle audit",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs/figures/evidence_allocation_frontier.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from PIL import Image, ImageDraw, ImageFont

        run_dir = args.run_dir.resolve()
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        if status.get("status") != "COMPLETED":
            raise ValueError("frontier requires a completed frozen run")
        rows = [
            row
            for row in _read_csv(run_dir / "method_summary.csv")
            if row["population"] == "operational_decision"
        ]
        if {row["method"] for row in rows} != set(METHOD_LABELS):
            raise ValueError("method summary does not contain the registered methods")

        width, height = 1600, 1000
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=20)
        small_font = ImageFont.load_default(size=17)
        title_font = ImageFont.load_default(size=28)
        left, right, top, bottom = 155, 1530, 100, 825
        x_max, y_min, y_max = 2200.0, 84.0, 101.5

        def point(x: float, y: float) -> tuple[float, float]:
            return (
                left + (x / x_max) * (right - left),
                bottom - ((y - y_min) / (y_max - y_min)) * (bottom - top),
            )

        for y_tick in (85, 90, 95, 100):
            _, pixel_y = point(0, y_tick)
            draw.line((left, pixel_y, right, pixel_y), fill="#dddddd", width=2)
            draw.text((95, pixel_y - 11), f"{y_tick}%", fill="black", font=font)
        for x_tick in (0, 500, 1000, 1500, 2000):
            pixel_x, _ = point(x_tick, y_min)
            draw.line((pixel_x, top, pixel_x, bottom), fill="#eeeeee", width=2)
            draw.text((pixel_x - 24, bottom + 12), str(x_tick), fill="black", font=small_font)
        draw.line((left, top, left, bottom), fill="black", width=3)
        draw.line((left, bottom, right, bottom), fill="black", width=3)
        colors = {
            "passive": "#4c78a8",
            "seeded_random_probe": "#f58518",
            "always_probe": "#e45756",
            "global_temporal_gate": "#72b7b2",
            "frozen_phase_conditioned_gate": "#2ca02c",
            "oracle_audit": "#777777",
        }
        for row in rows:
            method = row["method"]
            x = int(row["probe_environment_steps"])
            y = 100.0 * float(row["mechanism_accuracy"])
            pixel_x, pixel_y = point(x, y)
            color = colors[method]
            if method == "frozen_phase_conditioned_gate":
                radius = 18
                vertices = []
                for index in range(10):
                    angle = -math.pi / 2 + index * math.pi / 5
                    distance = radius if index % 2 == 0 else radius * 0.42
                    vertices.append(
                        (pixel_x + distance * math.cos(angle), pixel_y + distance * math.sin(angle))
                    )
                draw.polygon(vertices, fill=color, outline="#145214")
            else:
                radius = 12
                draw.ellipse(
                    (pixel_x - radius, pixel_y - radius, pixel_x + radius, pixel_y + radius),
                    fill="white" if method == "oracle_audit" else color,
                    outline=color,
                    width=4,
                )
            label_x, label_y = pixel_x + 12, pixel_y + 15
            if method == "always_probe":
                label_y = pixel_y - 48
            elif method == "global_temporal_gate":
                label_x, label_y = pixel_x - 150, pixel_y - 48
            draw.text((label_x, label_y), METHOD_LABELS[method], fill=color, font=small_font)
        draw.text((420, 30), "Frozen held-out evidence-allocation frontier", fill="black", font=title_font)
        draw.text(
            (420, 875),
            "Diagnostic-probe environment steps (33 decision-required units)",
            fill="black",
            font=font,
        )
        draw.text((15, 60), "Mechanism diagnosis accuracy (%)", fill="black", font=small_font)
        draw.text(
            (25, 950),
            f"run={status['experiment_run_id']} | Phase 2 diagnosis only; no verification rollouts",
            fill="#666666",
            font=small_font,
        )
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, format="PNG", dpi=(180, 180), optimize=True)
        print(f"figure: {output}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
