"""Repair only NumPy boolean serialization in the frozen v1 auditor.

The one-shot collection and v1 auditor remain byte-identical. V1 completed all
prefix checks but could not serialize its independently computed gate bools.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import audit_cold_start_evidence as frozen


def native_booleans(value):
    if isinstance(value, np.bool_): return bool(value)
    if isinstance(value, dict): return {k: native_booleans(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [native_booleans(v) for v in value]
    return value


def same(a, b):
    if frozen.run.normal(native_booleans(a)) != frozen.run.normal(native_booleans(b)):
        raise ValueError("recorded business value differs")


def audit(path, output):
    original = frozen.same
    try:
        frozen.same = same
        frozen.audit(path, output)
    finally:
        frozen.same = original
    result = json.loads((output/"audit.json").read_text(encoding="utf-8"))
    frozen.run.write_json(output/"audit_tooling.json", {
        **{k: result[k] for k in frozen.run.IDENTITY},
        "audit_tool_version": 2,
        "v1_error": "np.bool_ in recomputed gate was not JSON serializable after all 480 prefix checks",
        "repair": "recursively convert only np.bool_ to native bool for equality comparison",
        "v1_auditor_sha256": frozen.run.digest(ROOT/"scripts/audit_cold_start_evidence.py"),
        "v2_entrypoint_sha256": frozen.run.digest(Path(__file__)),
        "invocation_git_commit": frozen.run.git("rev-parse", "HEAD"),
        "new_environment_steps": 0, "new_resets": 0,
        "frozen_collection_model_threshold_changed": False,
    })


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--manifest", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(); audit(args.manifest.resolve(), args.output.resolve())
