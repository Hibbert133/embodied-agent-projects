from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from src.rollout import chronological_cache_execution as execution
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.chronological_cache_reference import VerifiedPoint
from tests.test_chronological_cache_reference import cache_fixture
from tests.test_cold_start_task_bridge import VisibleResetEnv
from tests.test_acquisition_value import FakeEnv, FakeSimulator, FixedPolicy, model
from scripts import audit_chronological_cache_reference as audit
from collections import deque


class ChronologicalExecutionTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        def emit(kind, payload):
            event = {"event": kind, "sequence": len(self.events)+1, "saved_ns": execution.perf_counter_ns(), **execution.prior.normal(payload)}
            self.events.append(event); return event
        self.emit = emit; self.ledger = LifecycleLedger(emit, 1000000)
        self.joint, self.cache = cache_fixture()
        self.key = {"experiment_run_id": "unit", "manifest_id": "unit", "source_git_commit": "unit", "phase": "SMOKE", "stream": 0,
                    "episode": 1, "task": "push-v3", "method": "UNCERTAINTY4", "seed": 17001}
        self.fault = {"matrix_xy": np.eye(2).tolist(), "bias_xy": [0., 0.], "deadzone_xy": [0., 0.]}
        self.fit = {"valid": True, "matrix_xy": [[1.4, 0.], [0., 1.1]], "bias_xy": [.05, -.02]}

    @contextmanager
    def fixture(self):
        factory = SimpleNamespace(_make_tasks=lambda: None)
        with self.ledger.instrument(FakeEnv, FakeSimulator, factory), \
             patch.object(execution, "create_task_environment", side_effect=lambda *a: VisibleResetEnv()), \
             patch.object(execution, "create_task_policy", return_value=FixedPolicy()), \
             patch.object(execution.prior, "physics_witness", side_effect=lambda e: {"time": e.data.time, "obs": e.observation.tolist()}):
            yield

    def branch(self, action, fit=None):
        state = {"cache": VerifiedPoint.from_dict(deepcopy(execution.state_view({"cache": self.cache, "cusum": 0.})["cache"])), "cusum": 0.}
        result = {"action": action, "cusum_after_check": 0., "reason": "UNIT_SCRIPTED_LEGAL_CHOICE"}
        with self.fixture(), patch.object(execution, "check_choice", return_value=result), patch.object(execution, "infer_joint", return_value=fit or self.fit) as inference:
            record = execution.execute(self.key, self.fault, state, model(), self.joint, self.emit, self.ledger)
        return record, state, inference.call_count

    def test_saved_legal_choices_change_actual_program_and_controller(self):
        kept, state_kept, count = self.branch("RUN_CACHED")
        refreshed, state_new, new_count = self.branch("REFRESH8")
        self.assertEqual(count, 0); self.assertEqual(new_count, 1)
        self.assertEqual(kept["outcome"]["fixed_probe_steps"], 4)
        self.assertEqual(refreshed["outcome"]["fixed_probe_steps"], 8)
        self.assertEqual(kept["trace"][:4][0]["command"], refreshed["trace"][:4][0]["command"])
        self.assertNotEqual(kept["trace"][4]["command"], refreshed["trace"][4]["command"])
        self.assertNotEqual(kept["trace"][8]["command"], refreshed["trace"][8]["command"])
        self.assertEqual(state_kept["cache"].source_episode, 0)
        self.assertEqual(state_new["cache"].source_episode, 1)
        for record in (kept, refreshed):
            self.assertEqual(record["outcome"]["environment_resets"], 1)
            self.assertEqual(record["outcome"]["noise_rows_consumed"], record["outcome"]["total_steps"])
            self.assertTrue(all(r["intent_saved_ns"] < r["execution_started_ns"] < r["completed_ns"] for r in record["trace"]))
            self.assertGreater(record["cache_event"]["saved_ns"], record["trace"][-1]["completed_ns"])

    def test_failed_new_fit_stops_without_old_cache_substitution(self):
        record, state, _ = self.branch("REFRESH8", {"valid": False, "reason": "UNIT_UNSTABLE_INVERSE"})
        self.assertTrue(record["outcome"]["stopped"])
        self.assertEqual(record["outcome"]["deadline_loss"], 500)
        self.assertEqual(record["outcome"]["total_steps"], 8)
        self.assertIsNone(state["cache"])

    def test_successful_reuse_does_not_renew_source_evidence(self):
        record, state, _ = self.branch("RUN_CACHED")
        self.assertEqual(record["state_before"]["cache"], record["state_after"]["cache"])
        self.assertEqual(state["cache"].evidence_sha256, self.cache.evidence_sha256)

    def test_repeated_or_unknown_probe_choice_aborts_before_more_physical_steps(self):
        for action in ("PROBE8", "UNKNOWN"):
            with self.assertRaises(execution.prior.BranchFailure) as error:
                self.branch(action)
            self.assertEqual(error.exception.record["completed_steps"], 4)
            self.assertEqual(error.exception.record["noise_rows_consumed"], 4)

    def test_record_replay_rejects_saved_controller_and_foreign_cache_tampering(self):
        with self.fixture():
            record = execution.execute(self.key, self.fault, {"cache": self.cache, "cusum": 0.}, model(), self.joint, self.emit, self.ledger)
        record = execution.prior.normal(record)
        business = [e for e in self.events if not e["event"].startswith("LIFECYCLE")]
        state = {"cache": self.cache, "cusum": 0.}
        with patch.object(audit, "create_task_policy", return_value=FixedPolicy()):
            audit.verify_record(record, model(), self.joint, self.fault, state, deque(deepcopy(business)), .01)
            for mode in ("controller", "cache", "future"):
                forged = deepcopy(record); changed = deepcopy(business)
                if mode == "controller":
                    decision = next(d for d in forged["decisions"] if d["controller"] is not None)
                    decision["controller"]["offset"][0] += .1
                    next(e for e in changed if e["sequence"] == decision["sequence"]).update(deepcopy(decision))
                elif mode == "cache": forged["state_before"]["cache"]["source_episode"] = 7
                else:
                    decision = next(d for d in changed if d["event"] == "DECISION")
                    decision["noise_hash"] = "future"; forged["decisions"][0]["noise_hash"] = "future"
                with self.assertRaises(ValueError):
                    audit.verify_record(forged, model(), self.joint, self.fault, {"cache": self.cache, "cusum": 0.}, deque(changed), .01)


if __name__ == "__main__": unittest.main()
