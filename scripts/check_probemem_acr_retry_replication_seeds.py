"""Check fresh seed reservations for the ACR retry-utility replication."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_probemem_acr_seed_registry import _external_seed_hits  # noqa: E402


CONFIG = ROOT / "configs/probemem_acr/retry_utility_replication_v1.json"


def main() -> int:
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        partitions: dict[str, set[int]] = {}
        for name, bounds in config["seed_partitions"].items():
            start, stop = (int(item) for item in bounds)
            partitions[name] = set(range(start, stop + 1))
        names = list(partitions)
        for index, left in enumerate(names):
            for right in names[index + 1 :]:
                if partitions[left] & partitions[right]:
                    raise ValueError(f"replication seed partitions overlap: {left}, {right}")
        reserved = set().union(*partitions.values())
        previous_acr = set(range(1100, 1400))
        if reserved & previous_acr:
            raise ValueError("replication seeds overlap the ACR v1 registry")
        hits = _external_seed_hits(reserved)
        if hits:
            raise ValueError(f"replication seed collision(s): {hits[:20]}")
        print(
            "ProbeMem-ACR retry replication seeds: passed "
            f"development={len(partitions['development_replication'])} "
            f"validation={len(partitions['validation_reserved'])} "
            f"heldout={len(partitions['heldout_reserved'])}"
        )
        return 0
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
