"""Fail closed on ProbeMem-Online seed overlap with earlier protocols/artifacts."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/probemem_online/seed_registry_v1.json"


def partition_sets(registry: dict[str, Any]) -> dict[str, set[int]]:
    output: dict[str, set[int]] = {}
    for name, bounds in registry["partitions"].items():
        start, stop = map(int, bounds)
        if start <= 0 or stop < start:
            raise ValueError(f"invalid seed partition: {name}")
        output[name] = set(range(start, stop + 1))
    names = list(output)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            if output[left] & output[right]:
                raise ValueError(f"overlapping seed partitions: {left}, {right}")
    return output


def seed_values(value: Any) -> Iterable[int]:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"random_namespaces", "random_seed_namespaces"}:
                continue
            if key in {"seed", "seed_start", "seed_end", "environment_seed"} and isinstance(nested, int):
                yield nested
            elif key in {"seed_range", "heldout_seed_range"} and isinstance(nested, list) and len(nested) == 2:
                start, stop = nested
                if isinstance(start, int) and isinstance(stop, int):
                    yield from range(start, stop + 1)
            yield from seed_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from seed_values(nested)


def external_collisions(reserved: set[int]) -> list[tuple[int, str]]:
    collisions: set[tuple[int, str]] = set()
    excluded = (ROOT / "configs/probemem_online", ROOT / "outputs/probemem_online")
    for root in (ROOT / "configs", ROOT / "outputs"):
        for path in root.rglob("*"):
            if not path.is_file() or any(parent in path.parents for parent in excluded):
                continue
            try:
                if path.suffix == ".json":
                    values = seed_values(json.loads(path.read_text(encoding="utf-8")))
                elif path.suffix == ".jsonl":
                    values = (
                        seed for line in path.read_text(encoding="utf-8").splitlines()
                        if line.strip() for seed in seed_values(json.loads(line))
                    )
                elif path.suffix == ".csv":
                    with path.open("r", encoding="utf-8-sig", newline="") as handle:
                        rows = csv.DictReader(handle)
                        values = (
                            int(float(cell)) for row in rows for key, cell in row.items()
                            if key in {"seed", "seed_start", "seed_end", "environment_seed"} and cell
                        )
                else:
                    continue
                collisions.update((seed, path.relative_to(ROOT).as_posix()) for seed in values if seed in reserved)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
    return sorted(collisions)


def main() -> int:
    try:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        partitions = partition_sets(registry)
        collisions = external_collisions(set().union(*partitions.values()))
        if collisions:
            raise ValueError(f"ProbeMem-Online seed collision(s): {collisions[:20]}")
        print("ProbeMem-Online seed registry passed: " + ", ".join(f"{name}={len(values)}" for name, values in partitions.items()))
        return 0
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
