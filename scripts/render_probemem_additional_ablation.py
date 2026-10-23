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
        label = row["policy"].replace("_", " ")
        font = ImageFont.load_default(size=14)
        width = draw.textbbox((0, 0), label, font=font)[2]
        label_x = x - width - 18 if x > 900 else x + 18
        draw.text((label_x, y - 10), label, fill=COLORS["ink"], font=font)
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
        labels = {
            "BASELINE": ("BASELINE", ""),
            "MEMORY_ONLY": ("MEMORY ONLY", ""),
            "EVIDENCE_ACQUISITION_ENABLED": ("EVIDENCE ACQUISITION", "ENABLED"),
            "PROBE_MEMORY": ("PROBE + MEMORY", ""),
            "FULL_PROBEMEM": ("FULL PROBEMEM", ""),
        }[row["method"]]
        label_font = ImageFont.load_default(size=12)
        for line_index, label in enumerate(labels):
            if not label:
                continue
            width = draw.textbbox((0, 0), label, font=label_font)[2]
            draw.text((x + 72 - width / 2, 642 + line_index * 17), label, fill=COLORS["ink"], font=label_font)
        evidence_label = f"evidence={row['total_evidence_steps']}"
        width = draw.textbbox((0, 0), evidence_label, font=label_font)[2]
        draw.text((x + 72 - width / 2, 680), evidence_label, fill=COLORS["ink"], font=label_font)
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
    lines = [
        "# Outcome-Blind Representative Case Report", "",
        "Cases are the first sequential operational episode for each registered perturbation category. "
        "Selection does not use diagnosis, recovery, Memory, or Verifier outcomes; failure labels are assigned only after selection.", "",
    ]
    for case in selected:
        episode = int(case["episode_id"])
        rows = by_episode[episode]
        row = next(item for item in rows if item["method"] == "FULL_PROBEMEM")
        baseline = next(item for item in rows if item["method"] == "BASELINE")
        trace_path = next((run_dir / "initial_trajectories").glob(f"unit*_seed{case['seed']}.jsonl"))
        trace_lines = trace_path.read_text(encoding="utf-8").splitlines()
        final_initial = json.loads(trace_lines[-1])
        metrics = final_initial["task_progress_metrics"]
        evidence_steps = int(row["evidence_steps"])
        if evidence_steps:
            relation = "changed" if baseline["mechanism_prediction"] != row["mechanism_prediction"] else "retained"
            evidence = (
                f"The registered {evidence_steps}-step diagnostic evidence {relation} the passive hypothesis "
                f"`{baseline['mechanism_prediction']}` as `{row['mechanism_prediction']}`."
            )
            probe = f"One registered fixed diagnostic evidence rollout ({evidence_steps} environment steps)."
        else:
            evidence = "No post-failure evidence was acquired; the decision used only pre-action observable rollout features."
            probe = "None."
        verifier_note = ""
        if row["method"] == "FULL_PROBEMEM":
            verifier_note = (
                f" Verifier invoked=`{row['verifier_invoked']}`, proposal=`{row['proposal_skill']}`, "
                f"selected=`{row['selected_skill']}`, reason=`{row['verifier_reason']}`."
            )
        lines += [
            f"## {case['selection_basis']}", "",
            f"- Observed case type(s): `{case['observed_case_types']}`",
            f"- Episode / seed: `{episode}` / `{case['seed']}`",
            "- Initial task description: MetaWorld `push-v3`; use the frozen SawyerPushV3Policy to push the object to the observable goal.",
            f"- Failure observation: initial rollout ended after `{len(trace_lines)}` steps without success; final object-goal distance was `{metrics['object_goal_distance']:.4f}`, progress-to-goal `{metrics['progress_to_goal']:.4f}`, lateral drift `{metrics['lateral_drift']:.4f}`.",
            f"- Agent hypothesis ({row['method']}): `{row['mechanism_prediction']}`; evaluator mechanism: `{row['mechanism_oracle']}`.",
            f"- Selected probe(s): {probe}",
            f"- Evidence obtained: {evidence}",
            f"- Final decision: execute `{row['selected_skill']}`.{verifier_note}",
            f"- Outcome: `{row['verification_status']}` after `{row['verification_steps']}` verification steps; final object-goal distance `{float(row['final_object_goal_distance']):.4f}`.",
            "", "Configuration comparison:", "",
            "| Method | Hypothesis | Evidence steps | Recovery action | Outcome |",
            "|---|---|---:|---|---|",
        ]
        for row in rows:
            lines.append(f"| `{row['method']}` | `{row['mechanism_prediction']}` | {row['evidence_steps']} | `{row['selected_skill']}` | `{row['verification_status']}` |")
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
