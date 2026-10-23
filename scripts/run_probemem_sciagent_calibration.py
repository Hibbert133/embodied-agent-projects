"""Guarded entry point for the not-yet-authorized SciAgent calibration."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "configs/probemem_sciagent/calibration_v1.json").read_text(encoding="utf-8"))
if config.get("execution_authorized") is not True:
    print("[BLOCKED] calibration is not authorized until the immutable Demo gate is recorded", file=sys.stderr)
    raise SystemExit(2)
raise SystemExit("authorized calibration runner must be frozen after the Demo result")
