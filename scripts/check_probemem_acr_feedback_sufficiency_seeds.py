"""Reject episode-seed collisions for the feedback-sufficiency audit."""

from __future__ import annotations

import json
import csv
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/probemem_acr/verification_feedback_sufficiency_development_v1.json"


def development_seeds(config: dict[str, object]) -> list[int]:
    start, end = config["seed_partitions"]["development"]  # type: ignore[index]
    return list(range(int(start), int(end) + 1))


def external_seed_hits(seeds: set[int]) -> list[str]:
    hits: list[str] = []
    seed_pattern = re.compile(
        r'(?i)(?:environment_seed|episode_seed|seed)[^\d\r\n]{0,12}(\d{1,9})'
    )
    for root_name in ("configs", "reports", "outputs"):
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or "probemem_acr" in path.parts:
                continue
            matched: list[int] = []
            try:
                if path.suffix.lower() == ".csv":
                    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
                        rows = csv.DictReader(handle)
                        seed_fields = [name for name in (rows.fieldnames or []) if "seed" in name.lower()]
                        values = {int(row[name]) for row in rows for name in seed_fields if row.get(name, "").isdigit()}
                else:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    values = {int(value) for value in seed_pattern.findall(text)}
                matched = sorted(values & seeds)
            except (OSError, UnicodeError, ValueError):
                continue
            if matched:
                hits.append(f"{path.relative_to(ROOT).as_posix()}: {matched}")
    return hits


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    seeds = development_seeds(config)
    if seeds != list(range(3300, 3500)):
        print("[FAIL] frozen development range changed", file=sys.stderr)
        return 1
    hits = external_seed_hits(set(seeds))
    if hits:
        print("[FAIL] external episode-seed collisions:\n" + "\n".join(hits), file=sys.stderr)
        return 1
    print("feedback-sufficiency seeds: 3300-3499; no external collision")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
