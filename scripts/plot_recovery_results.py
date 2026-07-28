"""Create recovery comparison PNGs directly from one or more real trial CSVs."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "recovery" / "figures")
    return parser.parse_args()


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.expanduser().resolve().open(encoding="utf-8", newline="") as file:
            rows.extend(csv.DictReader(file))
    if not rows:
        raise ValueError("input CSV files contain no rows")
    return rows


def episode_groups(rows: list[dict[str, str]]) -> dict[str, list[list[dict[str, str]]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        schedule = row.get("correction_schedule", "")
        method = f"{row['planner']}:{schedule}" if schedule else row["planner"]
        grouped[(method, row["episode_id"], row["seed"])].append(row)
    result: dict[str, list[list[dict[str, str]]]] = defaultdict(list)
    for (planner, _, _), trials in grouped.items():
        result[planner].append(sorted(trials, key=lambda row: int(row["trial"])))
    return dict(result)


def bar_chart(values: dict[str, float], title: str, y_label: str, path: Path, percent: bool = False) -> None:
    image = Image.new("RGB", (1400, 850), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 25), title, fill="black")
    draw.text((60, 55), y_label, fill="black")
    left, top, right, bottom = 110, 100, 1340, 730
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    maximum = max(values.values(), default=1.0) or 1.0
    width = (right - left) / max(1, len(values))
    for index, (label, value) in enumerate(sorted(values.items())):
        x0 = left + (index + 0.15) * width
        x1 = left + (index + 0.85) * width
        y = bottom - value / maximum * (bottom - top)
        draw.rectangle((x0, y, x1, bottom), fill="#2563eb")
        draw.text((x0, bottom + 12), label, fill="black")
        shown = f"{value:.1%}" if percent else f"{value:.2f}"
        draw.text((x0, max(top, y - 22)), shown, fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, dpi=(150, 150))


def recovery_curve(groups: dict[str, list[list[dict[str, str]]]], path: Path) -> None:
    image = Image.new("RGB", (1400, 850), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 25), "Cumulative recovery success by rollout budget", fill="black")
    left, top, right, bottom = 110, 90, 1340, 730
    draw.line((left, top, left, bottom, right, bottom), fill="black", width=3)
    maximum_trial = max(len(trials) for episodes in groups.values() for trials in episodes)
    colors = ("#2563eb", "#dc2626", "#16a34a", "#9333ea", "#f59e0b")
    for color, (planner, episodes) in zip(colors, sorted(groups.items())):
        points = []
        for trial in range(1, maximum_trial + 1):
            successes = sum(
                any(row["success"].lower() == "true" for row in episode[:trial])
                for episode in episodes
            )
            x = left + (trial - 1) / max(1, maximum_trial - 1) * (right - left)
            y = bottom - successes / len(episodes) * (bottom - top)
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=color, width=4)
        for x, y in points:
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color)
        draw.text((right - 180, top + 25 * sorted(groups).index(planner)), planner, fill=color)
    for trial in range(1, maximum_trial + 1):
        x = left + (trial - 1) / max(1, maximum_trial - 1) * (right - left)
        draw.text((x - 4, bottom + 12), str(trial), fill="black")
    draw.text((left, bottom + 45), "Total rollout budget", fill="black")
    draw.text((left, top - 20), "100%", fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, dpi=(150, 150))


def main() -> int:
    args = parse_args()
    groups = episode_groups(read_rows(args.input_csv))
    success_rates = {
        planner: mean(any(row["success"].lower() == "true" for row in episode) for episode in episodes)
        for planner, episodes in groups.items()
    }
    mean_trials = {
        planner: mean(len(episode) for episode in episodes)
        for planner, episodes in groups.items()
    }
    mean_final_distance = {
        planner: mean(float(episode[-1]["final_object_goal_distance"]) for episode in episodes)
        for planner, episodes in groups.items()
    }
    mean_total_steps = {
        planner: mean(
            sum(int(row["steps"]) for row in episode)
            + max(int(row.get("probe_environment_steps", 0) or 0) for row in episode)
            for episode in episodes
        )
        for planner, episodes in groups.items()
    }
    output = args.output_dir.expanduser().resolve()
    bar_chart(success_rates, "Recovery success rate", "Fraction of episodes", output / "recovery_success_rate.png", True)
    bar_chart(mean_trials, "Mean rollout trials used", "Rollouts", output / "recovery_mean_trials.png")
    recovery_curve(groups, output / "recovery_curve.png")
    bar_chart(mean_final_distance, "Mean final object-goal distance", "Distance (metres)", output / "recovery_final_distance.png")
    bar_chart(mean_total_steps, "Mean total environment interaction budget", "Rollout + probe steps", output / "recovery_total_environment_steps.png")
    print(f"figures: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
