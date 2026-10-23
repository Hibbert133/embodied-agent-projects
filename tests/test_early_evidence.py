import copy
from collections import deque
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from scripts import run_early_evidence as run
from scripts import analyze_early_evidence as audit
from src.probe.gaussian_response_reference import GaussianReference, PRIMITIVES, box_minimum, bounded_command
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_acquisition_value import FakeEnv, FakeSimulator, FixedPolicy, model
from tests.test_operator_identification import generated_samples, model as fit_model


class GaussianReferenceTest(unittest.TestCase):
    def reference(self):
        samples = generated_samples("LINEAR_ARX", np.array([[.8, .2, .1], [-.1, 1.1, -.08]]))
        return GaussianReference.from_visible(fit_model("LINEAR_ARX"), samples, .0002)[0]

    def test_conditional_covariance_update_matches_batch_information(self):
        reference = self.reference(); commands = PRIMITIVES["X4"]
        jac = np.vstack([reference.command_jacobian(c[:2]) for c in commands])
        expected = np.linalg.inv(np.linalg.inv(reference.covariance) + jac.T @ jac / reference.noise_rms_m ** 2)
        actual = reference.after_commands(commands)
        np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-13)
        self.assertGreaterEqual(np.linalg.eigvalsh(np.asarray(reference.covariance) - actual)[0], -1e-12)
        self.assertGreater(reference.ivr(commands, [[.5, 0.]], [1.]), 0.)

    def test_task_measure_changes_legal_probe_and_budget_is_checked(self):
        reference = GaussianReference((1., 0., 0., 0., 1., 0.), tuple(tuple(float(v) for v in row) for row in np.eye(6)), ((1., 0.), (0., 1.)), .1, "past")
        self.assertEqual(reference.choose([[.8, 0.]], [1.], 492, 8)["action"], "X4")
        self.assertEqual(reference.choose([[0., .8]], [1.], 492, 8)["action"], "Y4")
        for remaining, used in ((30, 8), (492, 16)):
            with self.assertRaises(ValueError): reference.choose([[0., 0.]], [1.], remaining, used)
        with self.assertRaises(ValueError): reference.after_commands([(0., 0., .5, 0.)])
        with self.assertRaises(ValueError): reference.ivr(PRIMITIVES["X4"], [[0., 0.]], [.5])

    def test_box_control_satisfies_kkt_at_interior_and_saturated_edges(self):
        h = np.array([[2., .4], [.4, 1.]])
        for g in (np.array([-.1, .2]), np.array([-4., .4]), np.array([-4., 4.])):
            q = box_minimum(h, g); gradient = h @ q + g
            self.assertTrue(np.all(np.abs(q) <= 1))
            for value, derivative in zip(q, gradient):
                if abs(value) < 1 - 1e-10: self.assertAlmostEqual(derivative, 0., places=10)
                elif value == -1: self.assertGreaterEqual(derivative, -1e-10)
                else: self.assertLessEqual(derivative, 1e-10)

    def test_saved_gaussian_controller_has_visible_strict_scope(self):
        saved = self.reference().controller(); raw = (.5, -.3, .7, 1.)
        sent = bounded_command(saved, raw)
        self.assertTrue(np.all(np.abs(sent) <= 1)); np.testing.assert_array_equal(sent[2:], np.asarray(raw, np.float32)[2:])
        other = copy.deepcopy(saved); other["mean"][2] += .1
        self.assertFalse(np.array_equal(sent, bounded_command(other, raw)))
        for name, value in (("future_outcome", True), ("physical_response_qualified", True), ("regularization", .1)):
            altered = {**saved, name: value}
            with self.assertRaises(ValueError): bounded_command(altered, raw)
        with self.assertRaises(TypeError): GaussianReference.from_visible(fit_model("LINEAR_ARX"), (), .0001, true_operator=[])


class EarlyEvidenceExecutionTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        def emit(kind, payload):
            item = {"event": kind, "sequence": len(self.events) + 1, "saved_ns": run.perf_counter_ns(), **run.normal(payload)}
            self.events.append(item); return item
        self.emit = emit; self.ledger = LifecycleLedger(emit, 1000000)
        self.factory = SimpleNamespace(_make_tasks=lambda: None)
        self.key = {"experiment_run_id": "test", "manifest_id": "manifest", "source_git_commit": "source", "stream": 0,
                    "task": "push-v3", "replicate": 0, "seed": 11500, "operator_id_oracle": "A"}
        self.operator = {"matrix_xy": [[.8, .1], [0., 1.1]], "bias_xy": [.1, -.08]}
        self.measures = {"push-v3": {"commands": [[.5, .1]], "weights": [1.]}}

    @contextmanager
    def fixtures(self):
        witness = lambda env: {"fixture": True, "time": env.data.time, "observation": env.observation.tolist()}
        with self.ledger.instrument(FakeEnv, FakeSimulator, self.factory), patch.object(run, "create_task_environment", side_effect=lambda *args: FakeEnv()), \
             patch.object(run, "create_task_policy", return_value=FixedPolicy()), patch.object(run, "physics_witness", side_effect=witness):
            yield

    def branch(self, method):
        return run.normal(run.execute({**self.key, "method": method}, self.operator, model(), .0001, self.measures, self.emit, self.ledger))

    def replay(self, record):
        business = deque(e for e in self.events if not e["event"].startswith("LIFECYCLE"))
        audit.verify_record(record, model(), .0001, self.measures, self.operator, business, .01)
        self.assertFalse(business)

    def test_all_eight_methods_consume_saved_choices_and_replay(self):
        with self.fixtures():
            for method in run.METHODS:
                self.events.clear(); record = self.branch(method); self.replay(record)
                self.assertEqual(record["outcome"]["environment_resets"], 1)
                self.assertLessEqual(record["outcome"]["fixed_probe_steps"] + record["outcome"]["ivr_probe_steps"], 16)
                if method.startswith("IVR_"):
                    self.assertEqual([d["at_host_calls"] for d in record["decisions"] if d["action"] == "REQUEST_IVR_PROBE"], [8, 12])

    def test_true_eight_step_prefix_is_shared_but_original_wide_order_is_not(self):
        with self.fixtures():
            first = self.branch("POINT8"); continued = self.branch("POINT16_CYCLE"); original = self.branch("POINT16_WIDE")
        self.assertEqual(run.pairing(continued, first), "MATCHED_CONTINUATION")
        self.assertNotEqual([r["command"] for r in original["trace"][:8]], [r["command"] for r in first["trace"][:8]])
        continued["trace"][2]["rng_after"] = "changed"
        with self.assertRaises(ValueError): run.pairing(continued, first)

    def test_controller_or_injection_substitution_is_rejected(self):
        with self.fixtures():
            self.events.clear(); record = self.branch("GAUSS8")
            record["trace"][-1]["executed_action_oracle"][0] += .1
            with self.assertRaises(ValueError): self.replay(record)

    def test_primary_statistics_keep_failed_and_stopped_cases(self):
        rows = []; pairs = []
        for stream in range(8):
            for task in run.TASKS:
                for replicate in range(4):
                    pairs.append({"stream": stream, "task": task, "replicate": replicate, "reason": "MATCHED_CONTINUATION"})
                    for method in run.METHODS:
                        success = method == "POINT16_CYCLE"
                        rows.append({"stream": stream, "task": task, "replicate": replicate, "method": method, "success": success,
                                     "stopped": not success, "total_steps": 30 if success else 8, "deadline_loss": 30 if success else 500,
                                     "fixed_probe_steps": 16 if success else 8, "ivr_probe_steps": 0, "point_fit_failures": int(not success)})
        m = {"config": __import__("json").loads(run.CONFIG.read_text(encoding="utf-8"))}
        result = audit.statistics(m, rows, pairs)
        self.assertTrue(result["repeat_gate"]["passed"])
        self.assertEqual((result["methods"]["POINT8"]["cases"], result["methods"]["POINT8"]["successes"], result["methods"]["POINT8"]["mean_deadline_loss"]), (96, 0, 500))
        rows.pop()
        with self.assertRaises(ValueError): audit.statistics(m, rows, pairs)


if __name__ == "__main__": unittest.main()
