"""Select representative active-probe videos from real per-trial CSV rows."""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-csv", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "outputs" / "active_probes" / "representative_videos",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected: list[dict[str, str]] = []
    for path in args.trial_csv:
        with path.expanduser().resolve().open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        if not rows:
            raise ValueError(f"trial CSV is empty: {path}")
        corrected = max(rows, key=lambda row: int(row["trial"]))
        if int(corrected["trial"]) <= 1:
            raise ValueError(f"no corrected trial in {path}")
        source = Path(corrected["video_path"])
        if not source.is_file() or source.stat().st_size == 0:
            raise FileNotFoundError(f"video is missing or empty: {source}")
        result = "success" if corrected["success"].lower() == "true" else "failure"
        name = (
            f"probe_rule_x_negative_0.10_seed{corrected['seed']}_"
            f"trial{int(corrected['trial']):02d}_{result}.mp4"
        )
        output = args.output_dir.expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        destination = output / name
        shutil.copy2(source, destination)
        selected.append(
            {
                "video_path": destination.relative_to(ROOT).as_posix(),
                "seed": corrected["seed"],
                "planner": corrected["planner"],
                "trial": corrected["trial"],
                "correction": "x_negative_0.10",
                "success": corrected["success"],
                "steps": corrected["steps"],
                "final_object_goal_distance": corrected["final_object_goal_distance"],
                "probe_environment_steps": corrected.get("probe_environment_steps", "0"),
            }
        )
    manifest = args.output_dir.expanduser().resolve() / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(selected[0]))
        writer.writeheader()
        writer.writerows(selected)
    print(f"selected videos: {len(selected)}")
    print(f"manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
