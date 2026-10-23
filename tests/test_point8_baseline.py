from collections import deque
from contextlib import contextmanager
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import run_point8_baseline as run
from scripts import analyze_point8_baseline as audit
from src.analysis.point8_baseline import statistics, LATE_PAIRS
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_acquisition_value import FakeEnv, FakeSimulator, FixedPolicy, model


class PointEightBaselineTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        def emit(kind, payload):
            item = {"event": kind, "sequence": len(self.events)+1, "saved_ns": run.perf_counter_ns(), **run.normal(payload)}
            self.events.append(item); return item
        self.emit = emit; self.ledger = LifecycleLedger(emit, 1000000)
        self.factory = SimpleNamespace(_make_tasks=lambda: None)
        self.key = {"experiment_run_id": "unit", "manifest_id": "unit", "source_git_commit": "unit", "stream": 0,
                    "task": "push-v3", "replicate": 0, "seed": 13400, "operator_id_oracle": "A"}
        self.operator = {"matrix_xy": [[.8, .1], [0, 1.1]], "bias_xy": [.1, -.08]}

    @contextmanager
    def fixtures(self):
        witness = lambda env: {"fixture": True, "time": env.data.time, "observation": env.observation.tolist()}
        with self.ledger.instrument(FakeEnv, FakeSimulator, self.factory), patch.object(run, "create_task_environment", side_effect=lambda *args: FakeEnv()), patch.object(run, "create_task_policy", return_value=FixedPolicy()), patch.object(run, "physics_witness", side_effect=witness):
            yield

    def branch(self, method):
        return run.normal(run.execute({**self.key, "method": method}, self.operator, model(), .0001, self.emit, self.ledger))

    def replay(self, record):
        events = deque(e for e in self.events if not e["event"].startswith("LIFECYCLE"))
        audit.verify_record(record, model(), .0001, self.operator, events, .01)
        self.assertFalse(events)

    def test_all_seven_actual_saved_programs_replay_with_one_reset(self):
        with self.fixtures():
            for method in run.METHODS:
                self.events.clear(); record = self.branch(method); self.replay(record)
                self.assertEqual(record["outcome"]["environment_resets"], 1)
                self.assertEqual(record["outcome"]["noise_rows_consumed"], record["outcome"]["total_steps"])
                expected = 0 if method == "NO_PROBE" else 16 if method in ("KEEP_POINT8_AFTER16", "POINT16_CYCLE", "UPDATE_G16") else 8
                self.assertEqual(record["outcome"]["fixed_probe_steps"], expected)

    def test_point8_and_gaussian8_use_same_data_but_change_actual_commands(self):
        with self.fixtures():
            point = self.branch("DIRECT_POINT8"); gaussian = self.branch("DIRECT_G8")
        self.assertEqual(run.prefix_match(point, gaussian), "MATCHED_ACTIVE_PREFIX_8")
        pd = next(d for d in point["decisions"] if d["action"] == "RUN_POINT")
        gd = next(d for d in gaussian["decisions"] if d["action"] == "BUILD_GAUSSIAN")
        self.assertEqual(pd["fit"], gd["fit"])
        self.assertNotEqual(point["trace"][8]["command"], gaussian["trace"][8]["command"])

    def test_kept_point_consumes_original_fit_and_cannot_be_replaced(self):
        with self.fixtures():
            record = self.branch("KEEP_POINT8_AFTER16"); self.replay(record)
            original = next(d for d in record["decisions"] if d["action"] == "RUN_POINT")
            kept = next(d for d in record["decisions"] if d["action"] == "RUN_KEEP_POINT")
            self.assertEqual(kept["controller"], original["controller"])
            self.assertEqual(kept["source_decision_sequence"], original["sequence"])
            kept["controller"]["offset"][0] += .01
            next(e for e in self.events if e["sequence"] == kept["sequence"])["controller"] = deepcopy(kept["controller"])
            with self.assertRaises(ValueError): self.replay(record)

    def test_both_sixteen_prefix_pairs_match_and_reject_future_substitution(self):
        with self.fixtures():
            for method, base in LATE_PAIRS:
                left, right = self.branch(method), self.branch(base)
                self.assertEqual(run.prefix_match(left, right, 16), "MATCHED_ACTIVE_PREFIX_16")
                left["trace"][15]["noise_after_hash"] = "changed"
                with self.assertRaises(ValueError): run.prefix_match(left, right, 16)

    def test_point_failure_stops_without_extra_probe_or_substitution(self):
        with self.fixtures(), patch.object(run, "infer_operator", return_value={"valid": False, "reason": "UNSTABLE_ESTIMATED_INVERSE"}):
            for method in ("DIRECT_POINT8", "KEEP_POINT8_AFTER16"):
                record = self.branch(method)
                self.assertTrue(record["outcome"]["stopped"])
                self.assertEqual(record["outcome"]["total_steps"], 8)
                self.assertEqual(record["outcome"]["deadline_loss"], 500)
                self.assertEqual(sum(d["action"] == "REQUEST_FIXED_PROBE" for d in record["decisions"]), 1)

    def test_stopped_before_sixteen_retains_shared_prefix_reason(self):
        with self.fixtures():
            other = self.branch("POINT16_CYCLE")
            with patch.object(run, "infer_operator", return_value={"valid": False, "reason": "NO_FIT"}):
                stopped = self.branch("KEEP_POINT8_AFTER16")
        self.assertEqual(run.prefix_match(stopped, other, 16), "ENDED_BEFORE_16_SHARED_8")
        self.assertEqual(run.prefix_match(stopped, other, 8), "MATCHED_ACTIVE_PREFIX_8")

    def test_identity_and_no_probe_never_fit_nominal_model(self):
        with self.fixtures(), patch.object(run, "infer_operator", side_effect=AssertionError("unexpected fit")), patch.object(run.GaussianReference, "from_visible", side_effect=AssertionError("unexpected fit")):
            for method in ("NO_PROBE", "IDENTITY_AFTER8"):
                record = self.branch(method)
                self.assertFalse(record["outcome"]["stopped"])

    def test_new_registration_keeps_old_reserved_ranges_untouched(self):
        c = json.loads(run.CONFIG.read_text(encoding="utf-8")); run.validate(c)
        self.assertEqual(run.task_seed(0, "push-v3"), 13400)
        self.assertEqual(run.task_seed(15, "door-open-v3"), 13447)
        self.assertEqual(c["reserved_seeds"], [13448, 13799]); self.assertEqual(len(run.operators(c)), 16)
        for change in ({"seed_start": 13048}, {"methods": list(run.METHODS)[:-1]}, {"api_calls": 1}):
            with self.assertRaises(ValueError): run.validate({**c, **change})

    def test_complete_statistics_keep_stops_and_all_primary_secondary_contrasts(self):
        c = json.loads(run.CONFIG.read_text(encoding="utf-8")); rows = []; pairs = []; repetitions = []
        for stream in range(16):
            for task in run.TASKS:
                for future in range(2):
                    for method in run.METHODS:
                        rows.append(dict(stream=stream, task=task, replicate=future, method=method, success=True, stopped=False, total_steps=50, deadline_loss=50, fixed_probe_steps=8, policy_measure_steps=0))
                    for method in run.PORTFOLIO:
                        pairs.append(dict(stream=stream, task=task, replicate=future, method=method, reference="DIRECT_G8", boundary=8, reason="MATCHED_ACTIVE_PREFIX_8"))
                    for method, base in LATE_PAIRS:
                        pairs.append(dict(stream=stream, task=task, replicate=future, method=method, reference=base, boundary=16, reason="MATCHED_ACTIVE_PREFIX_16"))
                for method in run.METHODS:
                    repetitions.append(dict(stream=stream, task=task, replicate=1, method=method, reason="MATCHED_ACTIVE_PREFIX_8"))
        stopped = next(r for r in rows if r["method"] == "DIRECT_POINT8")
        stopped.update(success=False, stopped=True, total_steps=8, deadline_loss=500)
        result = statistics({"config": c}, rows, pairs, repetitions, run.METHODS, run.TASKS)
        self.assertEqual(result["methods"]["DIRECT_POINT8"]["cases"], 96)
        self.assertEqual(result["methods"]["DIRECT_POINT8"]["stops"], 1)
        self.assertEqual(result["methods"]["DIRECT_POINT8"]["nominal_offline_steps"], 21010)
        self.assertEqual(result["methods"]["IDENTITY_AFTER8"]["nominal_offline_steps"], 0)
        self.assertEqual([r["role"] for r in result["registered_contrasts"]], ["PRIMARY"]+["SECONDARY_UNADJUSTED"]*4)
        self.assertAlmostEqual(result["registered_contrasts"][0]["statistics"]["deadline_loss"]["difference"], 450/96)
        with self.assertRaises(ValueError): statistics({"config": c}, rows[:-1], pairs, repetitions, run.METHODS, run.TASKS)


if __name__ == "__main__":
    unittest.main()
