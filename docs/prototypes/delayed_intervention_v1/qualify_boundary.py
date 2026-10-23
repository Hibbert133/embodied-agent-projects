"""Persist fixed-boundary composition tests before robot-task qualification."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import test_boundary_prefix as public_tests
import test_boundary_host as host_tests


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False);handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args();output = (ROOT / args.output).resolve()
    allowed = ROOT / "outputs/delayed_intervention/software_v1"
    if not output.is_relative_to(allowed) or output == allowed or output.exists():
        parser.error("fresh software-review directory required")
    output.mkdir(parents=True)
    files = [Path(__file__).parent / name for name in ("boundary_prefix.py", "boundary_host.py", "test_boundary_prefix.py",
             "test_boundary_host.py", "qualify_boundary.py", "controller.py", "session_adapter.py")]
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    host_tests.TOY_RECEIPTS.clear();host_tests.JOURNALS.clear()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in (public_tests, host_tests))
    start = perf_counter_ns()
    with (output / "tests.txt").open("x", encoding="utf-8", newline="\n") as handle:
        result = unittest.TextTestRunner(stream=handle, verbosity=2).run(suite)
    write(output / "native_cost_receipts.json", host_tests.TOY_RECEIPTS)
    with gzip.open(output / "native_journals.jsonl.gz", "xt", encoding="utf-8") as handle:
        for row in host_tests.JOURNALS:handle.write(json.dumps(row, allow_nan=False) + "\n")
    totals = {key: sum(row[key] for row in host_tests.TOY_RECEIPTS) for key in
              ("native_successful_requested_frames", "host_step_attempts", "host_returned_steps", "actual_tiny_policy_calls", "captures", "restores")}
    totals["reset_completed"] = sum(row["ledger"]["counts"].get("reset_completed", 0) for row in host_tests.TOY_RECEIPTS)
    assert all(sha(ROOT / name) == value for name, value in hashes.items())
    assert len(host_tests.TOY_RECEIPTS) == len(host_tests.JOURNALS)
    receipt = {"schema": "delayed_boundary_composition_software_v1", "status": "PASSED" if result.wasSuccessful() else "FAILED",
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "source_sha256": hashes, "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_was_uncommitted_development": True, "native_fixture_instances": len(host_tests.JOURNALS), "native_software_costs": totals,
        "prior_development_invocation": {"pure_callback_tests_passed": 7, "native_environment_steps": 0, "physical_costs": 0},
        "artifact_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()},
        "wall_ns": perf_counter_ns() - start, "new_metaworld_task_steps": 0, "new_scientific_task_seeds": 0,
        "new_api_calls": 0, "metaworld_qualification": False, "task_benefit_tested": False,
        "scope": "Artificial callback and tiny native-engine tests; mocked fits and a synthetic completion rule. Physical work deliberately injected by a policy is counted."}
    write(output / "receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "tests_run", "failures", "errors", "native_software_costs")}))
    raise SystemExit(not result.wasSuccessful())


if __name__ == "__main__":
    main()
