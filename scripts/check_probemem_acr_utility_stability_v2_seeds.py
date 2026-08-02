"""Check fresh seed reservations for utility-stability protocol v2."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_probemem_acr_seed_registry import _external_seed_hits  # noqa: E402


CONFIG = ROOT / "configs/probemem_acr/utility_realization_stability_v2.json"


def main() -> int:
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        partitions = {
            name: set(range(int(bounds[0]), int(bounds[1]) + 1))
            for name, bounds in config["seed_partitions"].items()
        }
        names = list(partitions)
        for index, left in enumerate(names):
            for right in names[index + 1 :]:
                if partitions[left] & partitions[right]:
                    raise ValueError(f"utility-stability v2 partitions overlap: {left}, {right}")
        reserved = set().union(*partitions.values())
        if reserved & set(range(1100, 1800)):
            raise ValueError("utility-stability v2 overlaps earlier ACR reservations")
        hits = _external_seed_hits(reserved)
        if hits:
            raise ValueError(f"utility-stability v2 seed collision(s): {hits[:20]}")
        print("ProbeMem-ACR utility-stability v2 seeds: passed")
        return 0
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
