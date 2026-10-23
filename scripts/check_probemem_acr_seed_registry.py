"""Validate ProbeMem-ACR seed partitions and immutable ProbeMem v2 inputs."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/probemem_acr/seed_registry_v1.json"
LOCK = ROOT / "configs/probemem_acr/v2_provenance_lock.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ranges(registry: dict[str, Any]) -> dict[str, set[int]]:
    output = {}
    for name, bounds in registry["episode_seed_partitions"].items():
        start, stop = (int(item) for item in bounds)
        if start <= 0 or stop < start:
            raise ValueError(f"invalid seed range: {name}")
        output[name] = set(range(start, stop + 1))
    names = list(output)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            if output[left] & output[right]:
                raise ValueError(f"seed partitions overlap: {left}, {right}")
    return output


def _seed_values(value: Any) -> Iterable[int]:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"seed", "seed_start", "seed_end"} and isinstance(nested, int):
                yield nested
            elif key in {"seed_range", "heldout_seed_range"}:
                if isinstance(nested, list) and len(nested) == 2:
                    start, stop = nested
                    if isinstance(start, int) and isinstance(stop, int):
                        yield from range(start, stop + 1)
            elif key == "seed_partitions" and isinstance(nested, dict):
                for bounds in nested.values():
                    if isinstance(bounds, list) and len(bounds) == 2:
                        start, stop = bounds
                        if isinstance(start, int) and isinstance(stop, int):
                            yield from range(start, stop + 1)
            yield from _seed_values(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _seed_values(item)


def _external_seed_hits(reserved: set[int]) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    roots = (ROOT / "configs", ROOT / "outputs")
    excluded = (ROOT / "configs/probemem_acr", ROOT / "outputs/probemem_acr")
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or any(parent in path.parents for parent in excluded):
                continue
            try:
                if path.suffix == ".json":
                    values = _seed_values(json.loads(path.read_text(encoding="utf-8")))
                elif path.suffix == ".jsonl":
                    values = (
                        seed
                        for line in path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                        for seed in _seed_values(json.loads(line))
                    )
                elif path.suffix == ".csv":
                    with path.open("r", encoding="utf-8-sig", newline="") as handle:
                        rows = list(csv.DictReader(handle))
                    values = (
                        int(float(cell))
                        for row in rows
                        for field, cell in row.items()
                        if field in {"seed", "seed_start", "seed_end"} and cell
                    )
                else:
                    continue
                for seed in values:
                    if seed in reserved:
                        hits.append((seed, path.relative_to(ROOT).as_posix()))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
    return sorted(set(hits))


def main() -> int:
    try:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        partitions = _ranges(registry)
        reserved = set().union(*partitions.values())
        hits = _external_seed_hits(reserved)
        if hits:
            raise ValueError(f"reserved episode seed collision(s): {hits[:20]}")
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        mismatches = [
            path
            for path, expected in lock["files"].items()
            if not (ROOT / path).is_file() or _sha256(ROOT / path) != expected
        ]
        if mismatches:
            raise ValueError(f"ProbeMem v2 provenance changed: {mismatches}")
        print(
            "ProbeMem-ACR seed registry: passed "
            f"development={len(partitions['development'])} "
            f"validation={len(partitions['validation_reserved'])} "
            f"heldout={len(partitions['heldout_reserved'])}"
        )
        print(f"ProbeMem v2 provenance lock: passed files={len(lock['files'])}")
        return 0
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
