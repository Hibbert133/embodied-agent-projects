"""Validate committed representative trajectories as strict schema-v2 Agent input."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.trajectory_views import FORBIDDEN_AGENT_FIELDS, build_agent_view

TRAJECTORY_DIR = PROJECT_ROOT / "outputs" / "representative_trajectories"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSONL from {path}: {exc}") from exc
    if not rows:
        raise ValueError(f"trajectory is empty: {path}")
    return rows


def validate_trajectory(path: Path) -> int:
    rows = load_jsonl(path)
    for index, row in enumerate(rows):
        line_number = index + 1
        if row.get("schema_version") != 2:
            raise ValueError(f"{path}:{line_number}: schema_version must be 2")
        agent_view = build_agent_view(row)
        leaked = FORBIDDEN_AGENT_FIELDS & set(agent_view)
        if leaked:
            raise ValueError(
                f"{path}:{line_number}: Agent View leaks {sorted(leaked)}"
            )
        if row["commanded_action"] != row["raw_action"]:
            raise ValueError(
                f"{path}:{line_number}: commanded_action differs from raw_action"
            )
        is_nonzero_bias = (
            row.get("perturbation_type") == "action_bias"
            and float(row.get("perturbation_parameters", {}).get("level", 0.0)) > 0
        )
        if is_nonzero_bias and row["commanded_action"] == row["perturbed_action"]:
            raise ValueError(
                f"{path}:{line_number}: nonzero bias did not change commanded action"
            )
        if index and rows[index - 1]["next_observation"] != row["observation"]:
            raise ValueError(
                f"{path}:{line_number}: observation is not previous next_observation"
            )
    print(f"[OK] {path.name}: {len(rows)} schema-v2 transitions")
    return len(rows)


def main() -> int:
    paths = sorted(TRAJECTORY_DIR.glob("*.jsonl"))
    if not paths:
        print(f"[FAIL] no JSONL files found in {TRAJECTORY_DIR}", file=sys.stderr)
        return 1
    try:
        total = sum(validate_trajectory(path) for path in paths)
    except (KeyError, TypeError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[PASS] validated {len(paths)} trajectories and {total} transitions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
