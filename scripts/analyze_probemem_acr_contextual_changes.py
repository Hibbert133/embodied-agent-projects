"""Audit whether contextual decisions helped after crossing the action boundary."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _truth(value: str) -> bool:
    if value not in {"True", "False"}:
        raise ValueError(f"invalid CSV Boolean: {value}")
    return value == "True"


def analyze(results: Path) -> dict[str, int]:
    with results.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    grouped = {}
    for row in rows:
        grouped.setdefault(row["method"], []).append(row)
    global_rows = grouped["posterior_greedy"]
    contextual_rows = grouped["contextual_greedy"]
    if len(global_rows) != len(contextual_rows):
        raise ValueError("contextual change audit requires matched method rows")
    summary = {"selection_changes": 0, "helpful_changes": 0, "harmful_changes": 0, "neutral_changes": 0}
    for global_row, contextual_row in zip(global_rows, contextual_rows):
        if global_row["episode_id"] != contextual_row["episode_id"]:
            raise ValueError("contextual change audit lost episode pairing")
        if global_row["selected_skill"] == contextual_row["selected_skill"]:
            continue
        summary["selection_changes"] += 1
        global_accepted = _truth(global_row["selected_accepted"])
        contextual_accepted = _truth(contextual_row["selected_accepted"])
        if contextual_accepted and not global_accepted:
            summary["helpful_changes"] += 1
        elif global_accepted and not contextual_accepted:
            summary["harmful_changes"] += 1
        else:
            summary["neutral_changes"] += 1
    partition = summary["helpful_changes"] + summary["harmful_changes"] + summary["neutral_changes"]
    if summary["selection_changes"] != partition:
        raise ValueError("contextual decision-change partition is incomplete")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = analyze(args.results.resolve())
    args.output.resolve().write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
