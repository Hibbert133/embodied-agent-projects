"""Validate severity-stratified development seeds against the recorded baseline CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=ROOT / "configs" / "campaigns" / "active_evidence_glm52_dev5.json",
    )
    return parser.parse_args()


def select_rank_stratified(
    rows: list[dict[str, str]], count: int, *, exclude_seeds: tuple[int, ...] = ()
) -> list[int]:
    excluded = set(exclude_seeds)
    failures = sorted(
        (
            row for row in rows
            if row["success"] == "False" and int(row["seed"]) not in excluded
        ),
        key=lambda row: (float(row["final_object_goal_distance"]), int(row["seed"])),
    )
    if count < 2 or len(failures) < count:
        raise ValueError("selection requires at least two requested and available failures")
    indices = [round(index * (len(failures) - 1) / (count - 1)) for index in range(count)]
    return [int(failures[index]["seed"]) for index in indices]


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
    provenance = config["selection_provenance"]
    source = ROOT / provenance["source_csv"]
    with source.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    expected = select_rank_stratified(
        rows,
        len(config["seeds"]),
        exclude_seeds=tuple(int(seed) for seed in provenance.get("exclude_seeds", ())),
    )
    actual = [int(seed) for seed in config["seeds"]]
    if actual != expected or actual != provenance["selected_seeds"]:
        raise ValueError(f"selection mismatch: expected {expected}, config has {actual}")
    print(f"selection validated: {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
