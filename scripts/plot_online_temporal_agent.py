"""Plot deterministic and online evidence allocation on development cases."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deterministic-summary",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/temporal_gate_development_v1/development_summary.csv",
    )
    parser.add_argument(
        "--online-summary",
        type=Path,
        default=ROOT
        / "outputs/online_evidence_agent/glm52_temporal_development_v1/summary.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/figures/online_temporal_agent_development.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from PIL import Image, ImageDraw, ImageFont

        with args.deterministic_summary.open("r", encoding="utf-8", newline="") as handle:
            deterministic = list(csv.DictReader(handle))
        online = json.loads(args.online_summary.read_text(encoding="utf-8"))
        rows = [
            {
                "method": row["method"],
                "accuracy": float(row["accuracy"]),
                "probe_steps": int(row["probe_environment_steps"]),
                "api_calls": 0,
            }
            for row in deterministic
        ]
        rows.append(
            {
                "method": "online_glm52",
                "accuracy": float(online["accuracy"]),
                "probe_steps": int(online["probe_environment_steps"]),
                "api_calls": int(online["api_calls"]),
            }
        )
        image = Image.new("RGB", (1600, 760), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=18)
        small = ImageFont.load_default(size=14)
        title = ImageFont.load_default(size=27)
        colors = ["#64748b", "#2563eb", "#7c3aed", "#0f766e"]
        draw.text(
            (800, 30),
            "Online GLM-5.2 does not improve selective evidence allocation",
            fill="#0f172a",
            font=title,
            anchor="ma",
        )

        def panel(left: int, heading: str, field: str, maximum: float, suffix: str) -> None:
            top, right, bottom = 135, left + 700, 620
            axis_left, axis_right = left + 70, right - 20
            draw.text(((left + right) // 2, 90), heading, fill="#0f172a", font=font, anchor="ma")
            draw.line((axis_left, top, axis_left, bottom), fill="#334155", width=2)
            draw.line((axis_left, bottom, axis_right, bottom), fill="#334155", width=2)
            slot = (axis_right - axis_left) / len(rows)
            for index, row in enumerate(rows):
                value = float(row[field])
                bar_left = int(axis_left + index * slot + 20)
                bar_right = int(axis_left + (index + 1) * slot - 20)
                bar_top = int(bottom - (bottom - top) * value / maximum)
                draw.rectangle((bar_left, bar_top, bar_right, bottom), fill=colors[index])
                label_value = 100 * value if field == "accuracy" else value
                draw.text(
                    ((bar_left + bar_right) // 2, bar_top - 10),
                    f"{label_value:.0f}{suffix}",
                    fill="#0f172a",
                    font=font,
                    anchor="ms",
                )
                label = str(row["method"]).replace("temporal_uncertainty_gated", "temporal_gate")
                draw.text(
                    ((bar_left + bar_right) // 2, bottom + 22),
                    label,
                    fill="#334155",
                    font=small,
                    anchor="ma",
                )

        panel(35, "Mechanism diagnosis (10 development cases)", "accuracy", 1.1, "%")
        panel(835, "Selected diagnostic evidence cost", "probe_steps", 700.0, "")
        draw.text(
            (800, 710),
            "Online GLM-5.2: 10 API calls, 100% probe requests; probe outcomes reused from real 64-step records",
            fill="#475569",
            font=font,
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
