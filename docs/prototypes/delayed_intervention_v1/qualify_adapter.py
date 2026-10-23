"""Persist native tiny-fixture tests and all of their physical-cost receipts."""

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
import test_session_adapter as tests


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False); handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    allowed = ROOT / "outputs/reproduction_reviews/delayed_intervention_v1"
    if not output.is_relative_to(allowed) or output == allowed or output.exists():
        parser.error("new native-software qualification directory required")
    source_files = sorted(Path(__file__).parent.glob("*.py"))
    source_hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in source_files}
    dependencies = ["tests/test_short_probe_reference_host_v1.py", "tests/test_paired_probe_host_v1.py",
                    "src/analysis/paired_probe_host_v1.py", "src/analysis/capsule_record_json_v2.py",
                    "src/analysis/state_capsule_v1.py", "src/probe/lifecycle_ledger.py", "src/rollout/chronological_faults.py"]
    dependency_hashes = {name: sha(ROOT / name) for name in dependencies}
    output.mkdir(parents=True, exist_ok=False)
    tests.TOY_RECEIPTS.clear(); tests.ADAPTER_CASES.clear(); tests.NATIVE_JOURNALS.clear()
    started = perf_counter_ns()
    with (output / "tests.txt").open("x", encoding="utf-8", newline="\n") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    write(output / "native_cost_receipts.json", tests.TOY_RECEIPTS)
    write(output / "completed_adapter_cases.json", tests.ADAPTER_CASES)
    with gzip.open(output / "native_journals.jsonl.gz", "xt", encoding="utf-8") as handle:
        for row in tests.NATIVE_JOURNALS:
            handle.write(json.dumps(row, allow_nan=False) + "\n")
    if any(sha(ROOT / name) != expected for name, expected in {**source_hashes, **dependency_hashes}.items()):
        raise RuntimeError("source changed during native software qualification")
    if len(tests.NATIVE_JOURNALS) != len(tests.TOY_RECEIPTS):
        raise RuntimeError("native journal/receipt count differs")
    totals = {field: sum(r[field] for r in tests.TOY_RECEIPTS) for field in
              ("native_successful_requested_frames", "host_step_attempts", "host_returned_steps", "actual_tiny_policy_calls", "captures", "restores")}
    totals.update(reset_completed=sum(r["ledger"]["counts"].get("reset_completed", 0) for r in tests.TOY_RECEIPTS),
                  ledger_simulation_frames_completed=sum(r["ledger"]["counts"].get("simulation_frames_completed", 0) for r in tests.TOY_RECEIPTS))
    receipt = {"schema": "delayed_intervention_native_software_qualification_v1",
               "status": "PASSED_NATIVE_SOFTWARE_TESTS" if result.wasSuccessful() else "FAILED_NATIVE_SOFTWARE_TESTS",
               "tests_run": result.testsRun, "test_failures": len(result.failures), "test_errors": len(result.errors),
               "native_fixture_instances": len(tests.TOY_RECEIPTS), "completed_adapter_cases": len(tests.ADAPTER_CASES),
               "native_software_costs_this_persisted_run": totals,
               "previous_development_run": {"test_count": 12, "tests_passed": True,
                                            "native_cost_receipts_persisted": False,
                                            "actual_native_cost_totals": None,
                                            "scope": "An earlier successful developer test invocation used the same tiny fixture. Its counters were not exported; these unrecorded prior software-test costs are unknown, not zero, and are not silently included in the measured totals above."},
               "new_metaworld_task_steps": 0, "new_metaworld_task_resets": 0,
               "new_scientific_task_seeds": 0, "new_api_calls": 0, "new_parameter_fits": 0,
               "metaworld_physical_qualification": False, "task_benefit_tested": False,
               "source_sha256": source_hashes, "frozen_dependency_sha256": dependency_hashes,
               "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "artifact_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()},
               "qualification_wall_ns": perf_counter_ns() - started,
               "scope": "Real MuJoCo steps in a small software fixture, including deliberate faults; not robot-task dynamics qualification or an independent intervention study."}
    write(output / "receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "tests_run", "native_fixture_instances", "native_software_costs_this_persisted_run", "metaworld_physical_qualification")}))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
