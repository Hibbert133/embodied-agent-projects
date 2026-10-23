"""Explicit evaluator-metadata repair; all v1 numerical code stays frozen."""
import argparse
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_cross_task_cache_validity as v1
from scripts import run_cold_start_task_bridge as original_bridge

BASE_INPUTS = tuple(v1.OWN_INPUTS)
V1_RUN = "outputs/cross_task_cache_validity/development_v1/cross_task_cache_validity_20261015T200149Z_ae7c22c393b1"


def flatten_static_a(rows):
    """Only evaluator equality checks need this view; never passed to forecast."""
    flattened = []
    for row in rows:
        states = [state for state in row["states_oracle"] if state["id"] == "A"]
        if len(states) != 1:
            raise ValueError("exactly one frozen static A state required")
        state = states[0]
        flattened.append({"matrix_xy": [list(axis) for axis in state["matrix_xy"]], "bias_xy": list(state["bias_xy"])})
    return flattened


def evaluation_operators(config):
    return flatten_static_a(original_bridge.operators(config))


def configure():
    # This replaces a local module's evaluator view, not original_bridge globals.
    # original_bridge.load therefore still verifies the original unmodified rows.
    v1.CONFIG = ROOT/"configs/cross_task_cache_validity/development_v2.json"
    v1.OWN_INPUTS = (*BASE_INPUTS, "scripts/run_cross_task_cache_validity_v2.py",
                     "scripts/audit_cross_task_cache_validity_v2.py", "tests/test_cold_cache_metadata_v2.py",
                     "configs/cross_task_cache_validity/development_v2.json",
                     "docs/protocols/cross_task_cache_validity_development_v2.md",
                     *(V1_RUN+"/"+name for name in ("manifest.json", "failure.json", "source_beliefs.json",
                                                    "unique_prefixes.jsonl.gz", "predictions_scores.jsonl.gz")))
    v1.bridge = SimpleNamespace(load=original_bridge.load, operators=evaluation_operators)
    return v1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("prepare", "run")); parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(); configured = configure()
    if args.command == "prepare":
        configured.prepare()
    elif args.manifest is None:
        parser.error("--manifest is required for run")
    else:
        try:
            configured.execute(args.manifest.resolve())
        except Exception as error:
            failure = args.manifest.resolve().parent/"failure.json"
            if not failure.exists():
                configured.write(failure, {"status": "FAILED_PRESERVE_PARTIAL", "error_type": type(error).__name__, "error": str(error)})
            raise
