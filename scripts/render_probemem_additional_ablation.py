"""Render tables, plots, and representative cases for additional experiments."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageFont


COLORS = {"navy": "#16324F", "blue": "#2A6FBB", "green": "#3A9D5D", "red": "#C84C4C", "gray": "#D8DEE6", "ink": "#1E252B"}


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.stat().st_size:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _canvas(title: str, subtitle: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1280, 760), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 35), title, fill=COLORS["navy"], font=ImageFont.load_default(size=30))
    if subtitle:
        draw.text((55, 78), subtitle, fill=COLORS["ink"], font=ImageFont.load_default(size=17))
    return image, draw


def _acquisition(run_dir: Path, path: Path) -> Path:
    rows = _csv(run_dir / "evidence_acquisition_policy_table.csv")
    image, draw = _canvas("Evidence acquisition cost-efficiency frontier", "Fixed 64-step evidence action space")
    for index, row in enumerate(rows):
        x = 120 + float(row["mean_evidence_steps"]) / 64.0 * 950
        y = 650 - float(row["diagnosis_accuracy"]) * 500
        color = (COLORS["gray"], COLORS["red"], COLORS["green"])[index]
        draw.ellipse((x - 13, y - 13, x + 13, y + 13), fill=color, outline=COLORS["navy"])
        draw.text((x + 18, y - 10), row["policy"].replace("_", " "), fill=COLORS["ink"], font=ImageFont.load_default(size=14))
    draw.line((120, 650, 1100, 650), fill=COLORS["ink"], width=2)
    draw.line((120, 650, 120, 130), fill=COLORS["ink"], width=2)
    draw.text((490, 700), "Mean evidence steps", fill=COLORS["ink"], font=ImageFont.load_default(size=18))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def _ablation(run_dir: Path, path: Path) -> Path:
    rows = _csv(run_dir / "ablation_result_table.csv")
    image, draw = _canvas("Five-configuration ablation", "Common denominator: all retained initial failures")
    maximum = max(1, max(int(row["initial_failed_episodes"]) for row in rows))
    for index, row in enumerate(rows):
        x = 85 + index * 235
        recovery = int(row["successful_recoveries"])
        height = 430 * recovery / maximum
        draw.rectangle((x, 620 - height, x + 145, 620), fill=COLORS["blue"] if index < 4 else COLORS["green"])
        draw.text((x + 45, 585 - height), f"{recovery}/{maximum}", fill=COLORS["ink"], font=ImageFont.load_default(size=18))
        draw.text((x, 645), row["method"].replace("_", " ")[:22], fill=COLORS["ink"], font=ImageFont.load_default(size=13))
        draw.text((x, 670), f"evidence={row['total_evidence_steps']}", fill=COLORS["ink"], font=ImageFont.load_default(size=12))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def _memory(summary: dict[str, Any], path: Path) -> Path:
    data = summary["memory_retrieval_utility"]["PROBE_MEMORY_VS_EVIDENCE_ACQUISITION"]["counts"]
    labels = ["NO_RETRIEVAL", "USEFUL_TRANSFER", "HARMFUL_TRANSFER", "NEUTRAL_TRANSFER"]
    colors = [COLORS["gray"], COLORS["green"], COLORS["red"], COLORS["blue"]]
    image, draw = _canvas("Memory retrieval utility", "Retrieval frequency is separated from transfer outcome")
    maximum = max(1, max(data[label] for label in labels))
    for index, (label, color) in enumerate(zip(labels, colors)):
        x = 130 + index * 275
        height = 420 * data[label] / maximum
        draw.rectangle((x, 610 - height, x + 160, 610), fill=color)
        draw.text((x + 65, 575 - height), str(data[label]), fill=COLORS["ink"], font=ImageFont.load_default(size=20))
        draw.text((x, 640), label.replace("_", " "), fill=COLORS["ink"], font=ImageFont.load_default(size=14))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def _verifier(summary: dict[str, Any], path: Path) -> Path:
    verifier = summary["verifier"]
    image, draw = _canvas("Verifier coverage and intervention outcomes", verifier["coverage_caveat"])
    eligible = max(1, verifier["eligible_cases"])
    coverages = [("Proposal", verifier["valid_proposals"]), ("Invoked", verifier["invocations"])]
    for index, (label, value) in enumerate(coverages):
        x = 120 + index * 240
        height = 420 * value / eligible
        draw.rectangle((x, 610 - height, x + 150, 610), fill=COLORS["blue"])
        draw.text((x + 25, 575 - height), f"{value}/{eligible}", fill=COLORS["ink"], font=ImageFont.load_default(size=18))
        draw.text((x + 35, 640), label, fill=COLORS["ink"], font=ImageFont.load_default(size=16))
    outcomes = verifier["intervention_outcomes"]
    labels = ["CORRECT_REJECTION", "FALSE_REJECTION", "CORRECT_ACCEPTANCE", "FALSE_ACCEPTANCE", "NO_NET_EFFECT"]
    for index, label in enumerate(labels):
        draw.text((600, 175 + index * 75), f"{label.replace('_', ' ')}: {outcomes.get(label, 0)}", fill=COLORS["green"] if label.startswith("CORRECT") else COLORS["red"] if label.startswith("FALSE") else COLORS["ink"], font=ImageFont.load_default(size=19))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def _cases(run_dir: Path, path: Path) -> Path:
    selected = _csv(run_dir / "selected_failure_cases.csv")
    decisions = _csv(run_dir / "decisions.csv")
    by_episode: dict[int, list[dict[str, str]]] = {}
    for row in decisions:
        by_episode.setdefault(int(row["episode_id"]), []).append(row)
    lines = ["# Representative Failure Cases", ""]
    for case in selected:
        episode = int(case["episode_id"])
        rows = by_episode[episode]
        lines += [f"## {case['case_type']}", "", f"- Episode: `{episode}`; seed: `{case['seed']}`"]
        for row in rows:
            lines.append(
                f"- `{row['method']}`: diagnosis `{row['mechanism_prediction']}`, "
                f"evidence steps `{row['evidence_steps']}`, action `{row['selected_skill']}`, "
                f"outcome `{row['verification_status']}`"
            )
        lines += ["", "Interpretation is restricted to this registered development case.", ""]
    if not selected:
        lines += ["No eligible representative cases were observed under the frozen selection rules.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def render(run_dir: Path) -> list[Path]:
    summary = json.loads((run_dir / "analysis_summary.json").read_text(encoding="utf-8"))
    figures = run_dir / "figures"
    return [
        _acquisition(run_dir, figures / "evidence_acquisition_frontier.png"),
        _ablation(run_dir, figures / "module_ablation.png"),
        _memory(summary, figures / "memory_retrieval_utility.png"),
        _verifier(summary, figures / "verifier_coverage_outcomes.png"),
        _cases(run_dir, run_dir / "representative_failure_cases.md"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        for path in render(args.run_dir.resolve()):
            print(f"rendered: {path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
