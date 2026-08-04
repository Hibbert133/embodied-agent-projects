"""Render compact ProbeMem verifier Demo figures and case page."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


COLORS = {"navy": "#16324F", "blue": "#2A6FBB", "green": "#3A9D5D", "red": "#C84C4C", "gray": "#D8DEE6", "ink": "#1E252B"}


def render(run_dir: Path) -> list[Path]:
    summary = json.loads((run_dir / "analysis_summary.json").read_text(encoding="utf-8"))
    decisions = _csv(run_dir / "decisions.csv")
    timeline = json.loads((run_dir / "timeline.json").read_text(encoding="utf-8"))
    figure_dir = run_dir / "figures"
    figure_dir.mkdir(exist_ok=True)
    outputs = [
        _recovery_calls(summary, figure_dir / "recovery_vs_verifier_call_rate.png"),
        _override_figure(summary, figure_dir / "override_guard_outcomes.png"),
        _timeline_figure(timeline, figure_dir / "chronological_memory_timeline.png"),
        _case_page(summary, decisions, run_dir / "case_page.md"),
    ]
    return outputs


def _canvas(title: str, subtitle: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1200, 720), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 40), title, fill=COLORS["navy"], font=ImageFont.load_default(size=30))
    if subtitle:
        draw.text((60, 85), subtitle, fill=COLORS["ink"], font=ImageFont.load_default(size=18))
    return image, draw


def _recovery_calls(summary: dict[str, Any], path: Path) -> Path:
    image, draw = _canvas("Recovery vs verifier-call rate", "Deterministic history-aware verifier Demo")
    methods = ["FROZEN_DETERMINISTIC", "ALWAYS_ON_VERIFIER", "BUDGETED_VERIFIER"]
    display = {"FROZEN_DETERMINISTIC": "Frozen", "ALWAYS_ON_VERIFIER": "Always-on", "BUDGETED_VERIFIER": "Budgeted"}
    for index, method in enumerate(methods):
        row = summary["methods"][method]
        cases = max(1, row["cases"])
        recovery = row["accepted"] / cases
        calls = row["verifier_calls"] / cases
        x = 120 + calls * 900
        y = 620 - recovery * 450
        color = (COLORS["gray"], COLORS["red"], COLORS["green"])[index]
        draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=color, outline=COLORS["navy"])
        label = f"{display[method]}: {row['accepted']}/{row['cases']}, calls={calls:.1%}"
        label_x = x - 285 if calls > 0.80 else x + 20
        draw.text((label_x, y - 10), label, fill=COLORS["ink"], font=ImageFont.load_default(size=17))
    draw.line((120, 620, 1050, 620), fill=COLORS["ink"], width=2)
    draw.line((120, 620, 120, 140), fill=COLORS["ink"], width=2)
    draw.text((470, 660), "Verifier call rate", fill=COLORS["ink"], font=ImageFont.load_default(size=18))
    image.save(path)
    return path


def _override_figure(summary: dict[str, Any], path: Path) -> Path:
    image, draw = _canvas("Helpful, harmful, tied, and blocked overrides")
    changes = summary["overrides_vs_frozen"]["BUDGETED_VERIFIER"]
    blocked = summary["blocked_budgeted_overrides"]
    values = [changes["helpful"], changes["harmful"], changes["tie"], blocked["blocked_harmful"]]
    labels = ["Helpful", "Harmful", "Tie", "Blocked harmful"]
    colors = [COLORS["green"], COLORS["red"], COLORS["gray"], COLORS["blue"]]
    maximum = max(1, max(values))
    for index, (label, value, color) in enumerate(zip(labels, values, colors)):
        x = 160 + index * 240
        height = 400 * value / maximum
        draw.rectangle((x, 600 - height, x + 130, 600), fill=color)
        draw.text((x + 50, 570 - height), str(value), fill=COLORS["ink"], font=ImageFont.load_default(size=20))
        draw.text((x, 625), label, fill=COLORS["ink"], font=ImageFont.load_default(size=16))
    image.save(path)
    return path


def _timeline_figure(timeline: list[dict[str, Any]], path: Path) -> Path:
    image, draw = _canvas("Chronological action and memory timeline", "Selection precedes paired outcomes; selected outcome only enters each method memory")
    episodes = sorted({int(row["episode_id"]) for row in timeline})[:10]
    for index, episode in enumerate(episodes):
        y = 145 + index * 50
        draw.text((60, y), f"E{episode}", fill=COLORS["navy"], font=ImageFont.load_default(size=16))
        events = [row for row in timeline if int(row["episode_id"]) == episode]
        for event_index, event in enumerate(events):
            x = 130 + event_index * min(105, 950 // max(1, len(events)))
            color = COLORS["green"] if event["event"] == "MEMORY_APPEND" else COLORS["blue"] if "SELECTION" in event["event"] else COLORS["gray"]
            draw.ellipse((x, y, x + 12, y + 12), fill=color)
            if index == 0:
                draw.text((x - 20, 115), event["event"].replace("_", " ")[:14], fill=COLORS["ink"], font=ImageFont.load_default(size=11))
    image.save(path)
    return path


def _case_page(summary: dict[str, Any], decisions: list[dict[str, str]], path: Path) -> Path:
    budgeted = [row for row in decisions if row["method"] == "BUDGETED_VERIFIER"]
    helpful = _changed_case(budgeted, decisions, helpful=True)
    blocked_harmful = _blocked_harmful_case(budgeted, decisions)
    lines = ["# ProbeMem Verifier Demo Case Page", "", f"Run: `{summary['experiment_run_id']}`", ""]
    lines.extend(_case_section("Helpful override", helpful, "No helpful override occurred; no memory-improvement claim is made."))
    lines.extend(_case_section("Blocked harmful override", blocked_harmful, "No blocked harmful alternative was observed in this run."))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _changed_case(rows: list[dict[str, str]], all_rows: list[dict[str, str]], *, helpful: bool) -> dict[str, str] | None:
    frozen = {(row["episode_id"]): row for row in all_rows if row["method"] == "FROZEN_DETERMINISTIC"}
    order = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "REJECTED": 0}
    for row in rows:
        base = frozen[row["episode_id"]]
        if row["final_skill"] != base["final_skill"] and (order[row["verification_status"]] > order[base["verification_status"]]) == helpful:
            return row
    return None


def _blocked_harmful_case(rows: list[dict[str, str]], all_rows: list[dict[str, str]]) -> dict[str, str] | None:
    frozen = {(row["episode_id"]): row for row in all_rows if row["method"] == "FROZEN_DETERMINISTIC"}
    for row in rows:
        if row.get("verifier_called", "").lower() == "true" and row.get("override_applied", "").lower() != "true" and frozen[row["episode_id"]]["verification_status"] == "ACCEPTED":
            return row
    return None


def _case_section(title: str, row: dict[str, str] | None, missing: str) -> list[str]:
    lines = [f"## {title}", ""]
    if row is None:
        return lines + [missing, ""]
    lines.extend([
        f"- Episode: `{row['episode_id']}` / seed `{row['seed']}`",
        f"- Evidence score / margin: `{row['score']}` / `{row['confidence_margin']}`",
        f"- Deterministic default: `{row['default_skill']}`",
        f"- Admission: `{row['admission_reasons']}`",
        f"- Guard: `{row['override_reason']}`",
        f"- Executed Skill: `{row['final_skill']}`",
        f"- Fresh verification: `{row['verification_status']}`",
        "- The appended memory record contains only this method's selected outcome.",
        "",
    ])
    return lines


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    run_dirs = sorted({path.parent for path in root.rglob("analysis_summary.json")})
    if not run_dirs:
        raise FileNotFoundError("no analyzed verifier Demo runs found")
    for run_dir in run_dirs:
        for output in render(run_dir):
            print(f"rendered: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
