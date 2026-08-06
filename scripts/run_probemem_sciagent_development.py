"""Guarded entry point for the blocked SciAgent prospective development run."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "configs/probemem_sciagent/development_v1.json").read_text(encoding="utf-8"))
if config.get("execution_authorized") is not True:
    print("[BLOCKED] development is not authorized until calibration passes", file=sys.stderr)
    raise SystemExit(2)
raise SystemExit("authorized development runner must be frozen after calibration")
