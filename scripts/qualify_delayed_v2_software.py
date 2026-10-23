"""Persist v2 pipeline software checks, source snapshots and native costs."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
import unittest

ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0, str(ROOT))
from tests import test_delayed_intervention_qualification_v2 as tests


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False);handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args();folder = (ROOT / args.output).resolve();allowed = ROOT / "outputs/continuous_state_witness/software_v1"
    if not folder.is_relative_to(allowed) or folder == allowed or folder.exists(): parser.error("fresh task-local directory required")
    folder.mkdir(parents=True)
    files = ["src/analysis/continuous_state_witness_v1.py", "src/analysis/delayed_qualification_io_v2.py", "scripts/qualify_delayed_intervention_v2.py",
        "scripts/audit_delayed_intervention_v2.py", "scripts/qualify_delayed_v2_software.py", "tests/test_delayed_intervention_qualification_v2.py",
        "configs/delayed_intervention/qualification_v2.json", "docs/protocols/delayed_intervention_qualification_v2.md"]
    hashes = {name: sha(ROOT / name) for name in files}
    for name in files:
        target = folder / "source_snapshot" / name;target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes((ROOT / name).read_bytes())
    tests.PIPELINE_RECEIPTS.clear();tests.PIPELINE_DATA.clear();start = perf_counter_ns()
    with (folder / "tests.txt").open("x", encoding="utf-8", newline="\n") as handle:
        result = unittest.TextTestRunner(stream=handle, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    write(folder / "native_cost_receipts.json", tests.PIPELINE_RECEIPTS)
    with gzip.open(folder / "pipeline_data.jsonl.gz", "xt", encoding="utf-8") as handle:
        for row in tests.PIPELINE_DATA: handle.write(json.dumps(row, allow_nan=False) + "\n")
    changed = [name for name, value in hashes.items() if sha(ROOT / name) != value]
    receipt = {"status": "PASSED" if result.wasSuccessful() and not changed else "FAILED", "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors), "source_sha256": hashes, "source_changed_during_run": changed,
        "artifact_sha256": {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob("*") if p.is_file()},
        "native_frames": sum(r["native_frames"] for r in tests.PIPELINE_RECEIPTS),
        "actual_policy_queries": sum(r["actual_policy_queries"] for r in tests.PIPELINE_RECEIPTS),
        "new_metaworld_steps": 0, "new_scientific_seeds": 0, "new_api_calls": 0, "wall_ns": perf_counter_ns() - start,
        "source_was_uncommitted_development": True, "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "scope": "One 15-case software pipeline with real RecordEpisodeStatistics and tiny physics; mocked estimators/policy and synthetic seed/ending rule."}
    write(folder / "receipt.json", receipt);print(json.dumps({k: receipt[k] for k in ("status", "tests_run", "failures", "errors", "native_frames")}))
    raise SystemExit(receipt["status"] != "PASSED")


if __name__ == "__main__": main()
