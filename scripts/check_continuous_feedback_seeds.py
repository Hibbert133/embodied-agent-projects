"""Check the prospective continuous-feedback development seed partition."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_probemem_acr_feedback_sufficiency_seeds import external_seed_hits  # noqa: E402


CONFIG = ROOT / "configs/probemem_acr/continuous_feedback_development_v1.json"


def main() -> int:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    start, end = config["seed_partitions"]["development"]
    seeds = set(range(int(start), int(end) + 1))
    if seeds != set(range(3500, 3800)):
        print("[FAIL] continuous-feedback seed partition changed", file=sys.stderr)
        return 1
    hits = external_seed_hits(seeds)
    if hits:
        print("[FAIL] external seed collisions:\n" + "\n".join(hits), file=sys.stderr)
        return 1
    print("continuous-feedback seeds: 3500-3799; no external collision")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
