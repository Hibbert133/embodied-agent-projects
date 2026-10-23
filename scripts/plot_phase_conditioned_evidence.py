"""Plot development-only accuracy and probe cost for evidence policies."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--global-gate-summary",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/temporal_gate_development_v1/development_summary.csv",
    )
    parser.add_argument(
        "--phase-gate-summary",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/phase_gate_development_v1/development_summary.csv",
    )
    parser.add_argument(
        "--global-online-summary",
        type=Path,
        default=ROOT
        / "outputs/online_evidence_agent/glm52_temporal_development_v1/summary.json",
    )
    parser.add_argument(
        "--phase-online-summary",
        type=Path,
        default=ROOT
        / "outputs/online_evidence_agent/glm52_phase_conditioned_development_v1/summary.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/figures/phase_conditioned_evidence_development.png",
    )
    return parser.parse_args()


def _read_csv(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["method"]: row for row in csv.DictReader(handle)}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    try:
        from PIL import Image, ImageDraw, ImageFont

        global_rows = _read_csv(args.global_gate_summary)
        phase_rows = _read_csv(args.phase_gate_summary)
        global_online = _read_json(args.global_online_summary)
        phase_online = _read_json(args.phase_online_summary)
        methods = [
            ("Passive", global_rows["passive"], 0),
            ("Always\nprobe", global_rows["always_probe"], 0),
            ("Global\ngate", global_rows["temporal_uncertainty_gated"], 0),
            ("Phase\ngate", phase_rows["phase_conditioned_gate"], 0),
            ("Global\nGLM-5.2", global_online, int(global_online["api_calls"])),
            ("Phase\nGLM-5.2", phase_online, int(phase_online["api_calls"])),
        ]

        image = Image.new("RGB", (1700, 900), "white")
        draw = ImageDraw.Draw(image)
        title_font = ImageFont.load_default(size=30)
        label_font = ImageFont.load_default(size=18)
        value_font = ImageFont.load_default(size=17)
        draw.text(
            (850, 35),
            "Development evidence allocation: accuracy versus diagnostic interaction cost",
            fill="#0f172a",
            font=title_font,
            anchor="ma",
        )

        panels = [
            (80, 125, 800, 710, "Diagnostic accuracy", "accuracy", 1.0, "%"),
            (900, 125, 1620, 710, "Probe environment steps", "probe_environment_steps", 640.0, ""),
        ]
        colors = ["#94a3b8", "#64748b", "#0ea5e9", "#16a34a", "#f59e0b", "#dc2626"]
        for left, top, right, bottom, heading, field, maximum, suffix in panels:
            draw.text(((left + right) // 2, top - 45), heading, fill="#0f172a", font=label_font, anchor="ma")
            draw.line((left, top, left, bottom), fill="#334155", width=2)
            draw.line((left, bottom, right, bottom), fill="#334155", width=2)
            width = (right - left) / len(methods)
            for index, (label, row, api_calls) in enumerate(methods):
                raw = float(row[field])
                height = (raw / maximum) * (bottom - top)
                x0 = int(left + index * width + 20)
                x1 = int(left + (index + 1) * width - 20)
                y0 = int(bottom - height)
                draw.rectangle((x0, y0, x1, bottom), fill=colors[index])
                shown = f"{raw * 100:.0f}%" if suffix == "%" else f"{raw:.0f}"
                draw.text(((x0 + x1) // 2, y0 - 10), shown, fill="#0f172a", font=value_font, anchor="ms")
                draw.multiline_text(((x0 + x1) // 2, bottom + 18), label, fill="#334155", font=value_font, anchor="ma", align="center", spacing=3)
                if api_calls:
                    draw.text(((x0 + x1) // 2, bottom + 72), f"{api_calls} API calls", fill="#7c2d12", font=value_font, anchor="ma")

        draw.text(
            (850, 830),
            "Development cases only (n=10). Accuracy uses registered probe outcomes; bars do not imply held-out generalization.",
            fill="#475569",
            font=label_font,
            anchor="ma",
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.output, format="PNG", dpi=(180, 180))
        print(f"figure: {args.output.resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
