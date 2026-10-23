"""Persist software-only collector/auditor tests and their native-engine costs."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests import test_delayed_intervention_qualification_v1 as tests


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False);handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args();output = (ROOT / args.output).resolve()
    allowed = ROOT / "outputs/delayed_intervention/software_v1"
    if not output.is_relative_to(allowed) or output == allowed or output.exists():
        parser.error("fresh software-review directory required")
    output.mkdir(parents=True)
    names = ["scripts/qualify_delayed_audit_software_v1.py", "scripts/qualify_delayed_intervention_v1.py",
        "scripts/audit_delayed_intervention_v1.py", "src/analysis/delayed_qualification_io_v1.py",
        "tests/test_delayed_intervention_qualification_v1.py", "configs/delayed_intervention/qualification_v1.json",
        "docs/prototypes/delayed_intervention_v1/boundary_prefix.py", "docs/prototypes/delayed_intervention_v1/boundary_host.py",
        "docs/prototypes/delayed_intervention_v1/controller.py", "docs/prototypes/delayed_intervention_v1/session_adapter.py"]
    hashes = {name: sha(ROOT / name) for name in names}
    # Preserve failed development versions too, instead of relying on dirty Git.
    for name in names:
        target = output / "source_snapshot" / name;target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    tests.FIXTURE_RECEIPTS.clear();tests.FIXTURE_PACKETS.clear();tests.PIPELINE_RECEIPTS.clear();start = perf_counter_ns()
    suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
    with (output / "tests.txt").open("x", encoding="utf-8", newline="\n") as handle:
        result = unittest.TextTestRunner(stream=handle, verbosity=2).run(suite)
    write(output / "native_cost_receipts.json", tests.FIXTURE_RECEIPTS)
    write(output / "pipeline_receipts.json", tests.PIPELINE_RECEIPTS)
    with gzip.open(output / "native_packets.jsonl.gz", "xt", encoding="utf-8") as handle:
        for value in tests.FIXTURE_PACKETS: handle.write(json.dumps(value, allow_nan=False) + "\n")
    totals = {key: sum(r[key] for r in tests.FIXTURE_RECEIPTS) for key in (
        "native_frames", "actual_policy_calls", "host_attempts", "host_returned", "captures", "restores")}
    totals["all_reset_completed"] = sum(r["ledger"]["counts"].get("reset_completed", 0) for r in tests.FIXTURE_RECEIPTS)
    pipeline_costs = {"native_frames": sum(r["native_frames"] for r in tests.PIPELINE_RECEIPTS),
        "actual_policy_calls": sum(r["actual_policy_calls"] for r in tests.PIPELINE_RECEIPTS)}
    changed = [name for name, expected in hashes.items() if sha(ROOT / name) != expected]
    receipt = {"status": "PASSED" if result.wasSuccessful() and not changed else "FAILED", "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors), "source_sha256": hashes, "source_changed_during_tests": changed,
        "artifact_sha256": {p.relative_to(output).as_posix(): sha(p) for p in output.rglob("*") if p.is_file()},
        "native_fixture_instances": len(tests.FIXTURE_RECEIPTS), "native_software_costs": totals, "pipeline_native_costs": pipeline_costs,
        "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_was_uncommitted_development": True, "wall_ns": perf_counter_ns() - start,
        "new_metaworld_task_steps": 0, "new_scientific_task_seeds": 0, "new_api_calls": 0,
        "scope": "Tiny native physics with mocked estimators and synthetic fixed policy/ending rules; not MetaWorld qualification or task benefit."}
    write(output / "receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "tests_run", "failures", "errors", "native_software_costs")}))
    raise SystemExit(receipt["status"] != "PASSED")


if __name__ == "__main__": main()
