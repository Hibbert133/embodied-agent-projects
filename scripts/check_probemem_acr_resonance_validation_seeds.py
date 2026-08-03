"""Fail closed on validation/held-out overlap or prior seed use."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_probemem_acr_seed_registry import _external_seed_hits  # noqa: E402


CONFIG = ROOT / "configs/probemem_acr/resonance_validation_v1.json"
REGISTRY = ROOT / "docs/protocols/seed_registry.json"
EARLIER_ACR_SEEDS = set(range(1100, 3050))


def validation_seeds(config: dict[str, object]) -> list[int]:
    seeds: list[int] = []
    for bounds in config["validation_seed_blocks"]:  # type: ignore[index]
        start, stop = map(int, bounds)
        seeds.extend(range(start, stop + 1))
    return seeds


def main() -> int:
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        seeds = validation_seeds(config)
        seed_set = set(seeds)
        heldout_start, heldout_stop = map(int, config["heldout_reserved_not_executed"])
        heldout = set(range(heldout_start, heldout_stop + 1))
        if seeds != [*range(3050, 3100), *range(3200, 3300)] or len(seed_set) != 150:
            raise ValueError("validation requires the frozen 150 unique seeds in order")
        if seed_set & EARLIER_ACR_SEEDS or seed_set & heldout:
            raise ValueError("validation overlaps earlier or held-out seeds")
        if [heldout_start, heldout_stop] != [3100, 3199]:
            raise ValueError("held-out reservation must remain 3100--3199")
        if registry["validation_seed_blocks"] != config["validation_seed_blocks"]:
            raise ValueError("seed registry differs from validation config")
        hits = _external_seed_hits(seed_set | heldout)
        if hits:
            raise ValueError(f"validation seed collision(s): {hits[:20]}")
        print("ProbeMem-ACR resonance validation seeds: passed")
        return 0
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
