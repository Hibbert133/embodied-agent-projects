"""Run synthetic tests and durable example traces in a fresh output directory."""

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import test_controller as tests
from controller import ACTIONS, Boundary, SingleIntervention, StepObservation, StepReceipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


class DiskJournal:
    def __init__(self, path):
        self.handle = path.open("x", encoding="utf-8", newline="\n")
        self.sequence = -1

    def __call__(self, kind, payload):
        self.sequence += 1
        saved = {**deepcopy(payload), "sequence": self.sequence, "saved_ns": perf_counter_ns()}
        self.handle.write(json.dumps({"kind": kind, "payload": saved}, allow_nan=False) + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())
        return saved


def examples(output):
    results = {}
    callbacks = []
    for action in ACTIONS:
        boundary = Boundary("push-v3", 100, tests.observation(), tests.CURRENT, tests.SAVED)
        journal_path = output / (action.lower() + ".jsonl")
        journal = DiskJournal(journal_path)
        current, completed = boundary.current, boundary.completed_steps
        def step(saved):
            nonlocal current, completed
            if saved["at_calls"] != completed or saved["before"] != json.loads(json.dumps(asdict(current))):
                raise ValueError("synthetic host boundary mismatch")
            # Read the actual saved file before accepting this synthetic transition.
            persisted = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
            if persisted[-1] != {"kind": "COMMAND", "payload": saved}:
                raise ValueError("command not persisted before transition")
            before = current
            position = list(before.observation)
            for axis in range(3):
                position[axis] += .01 * saved["command"][axis]
            completed += 1
            current = StepObservation(tuple(position), False, False, completed == 102)
            callbacks.append({"action_id": action, "completed_steps": completed,
                              "observed_last_persisted_sequence": persisted[-1]["payload"]["sequence"],
                              "command": saved["command"], "before": asdict(before), "after": asdict(current)})
            return StepReceipt(before, tuple(saved["command"]), current, completed)
        try:
            executor = SingleIntervention(boundary, policy=lambda obs: [.2, -.1, -.3, 0.], step=step, emit=journal)
            results[action] = executor.execute(action)
        finally:
            journal.handle.close()
    write_json(output / "synthetic_host_callbacks.json", callbacks)
    write_json(output / "example_results.json", results)
    return results, callbacks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    allowed = ROOT / "outputs/reproduction_reviews/delayed_intervention_v1"
    if not output.is_relative_to(allowed) or output == allowed or output.exists():
        parser.error("new qualification subdirectory required")
    output.mkdir(parents=True, exist_ok=False)
    started = perf_counter_ns()
    source_files = sorted(Path(__file__).parent.glob("*.py")) + [Path(__file__).parent / ".gitattributes"]
    sources = {str(p.relative_to(ROOT).as_posix()): sha(p) for p in source_files}
    tests.TEST_ACTIVITY.clear()
    with (output / "tests.txt").open("x", encoding="utf-8", newline="\n") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    test_passed = result.wasSuccessful()
    outcomes, callbacks = examples(output) if test_passed else ({}, [])
    if any(sha(ROOT / p) != expected for p, expected in sources.items()):
        raise RuntimeError("prototype changed during qualification")
    receipt = {"schema": "single_intervention_synthetic_execution_qualification_v1",
               "status": "PASSED_SYNTHETIC_TESTS" if test_passed else "FAILED_SYNTHETIC_TESTS",
               "tests_run": result.testsRun, "test_failures": len(result.failures), "test_errors": len(result.errors),
               "test_host_activity": dict(tests.TEST_ACTIVITY), "durable_examples": len(outcomes),
               "durable_example_synthetic_transitions": len(callbacks),
               "new_environment_steps": 0, "new_environment_resets": 0, "new_api_calls": 0,
               "new_parameter_fits": 0, "physical_qualification": False, "task_benefit_tested": False,
               "detector_or_acquisition_policy_implemented": False,
               "source_sha256": sources,
               "frozen_dependency_sha256": {p: sha(ROOT / p) for p in
                    ("src/probe/continuous.py", "src/probe/operator_identification.py", "src/probe/forward_prediction.py")},
               "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "artifact_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()},
               "qualification_wall_ns": perf_counter_ns() - started,
               "development_history": "The first pre-qualification test run had 3 failures and 12 errors caused by the mock host comparing tuple observations with JSON lists. The fixture serialization check was corrected before this qualification; no physical experiment was rerun.",
               "scope": "Single-use continuous-boundary command execution with synthetic hosts and flushed/fsynced example journals. Host truth, crash recovery, MetaWorld continuity and scientific utility require separate integration and physical qualification."}
    write_json(output / "receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "tests_run", "test_host_activity", "durable_examples", "durable_example_synthetic_transitions", "physical_qualification")}))
    if not test_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
