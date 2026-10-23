import copy
from collections import deque
from contextlib import contextmanager
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch
import numpy as np

from scripts import run_executable_support as run
from scripts import analyze_executable_support as audit
from src.probe.executable_support import DesiredMeasure, support_map, choose, digest
from src.probe.gaussian_response_reference import GaussianReference, PRIMITIVES
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_acquisition_value import FakeEnv, FakeSimulator, FixedPolicy, model


def rotated_reference(covariance=None, evidence="past-eight"):
    cov = np.diag([.04, .04, 1e-8, .04, .04, 1e-8]) if covariance is None else covariance
    return GaussianReference((0., -1., 0., 1., 0., 0.), cov, np.eye(2), .1, evidence)


class ExecutableSupportMathTest(unittest.TestCase):
    def test_rotated_inverse_changes_probe_axis_and_matches_independent_risk(self):
        reference = rotated_reference(); measure = DesiredMeasure(((.8, 0.),), (1.,))
        mapping = support_map(reference, measure); u = np.asarray(mapping["executable_commands"][0])
        # Independent solution of this isotropic strictly convex objective.
        a = np.array([[0., -1.], [1., 0.]])
        expected = np.linalg.solve(1.09 * np.eye(2), a.T @ np.array([.8, 0.]) + .01 * np.array([.8, 0.]))
        np.testing.assert_allclose(u, expected, rtol=1e-7, atol=1e-8)
        raw = reference.choose(measure.commands, measure.weights, 492, 8)
        selected = choose(reference, measure, 492, 8)
        self.assertEqual((raw["action"], selected["action"]), ("X4", "Y4"))
        def jac(q):
            x = np.array([*q, 1.]); result = np.zeros((2, 6)); result[0, :3] = x; result[1, 3:] = x
            return result
        scores = {}
        cov = np.asarray(reference.covariance)
        for name, commands in PRIMITIVES.items():
            design = np.vstack([jac(command[:2]) for command in commands])
            posterior = np.linalg.inv(np.linalg.inv(cov) + design.T @ design / .01)
            scores[name] = np.trace(jac(u) @ (cov - posterior) @ jac(u).T)
        for name, expected_score in scores.items(): self.assertAlmostEqual(selected["scores"][name], expected_score, places=12)
        self.assertGreater(scores["Y4"], 1000 * scores["X4"])

    def test_mapping_binds_saved_controller_and_preserves_weights_without_grid_rounding(self):
        measure = DesiredMeasure(((.8, 0.), (0., .8), (-.8, 0.)), (.25, .5, .25))
        reference = rotated_reference(); result = choose(reference, measure, 492, 8)
        mapping = result["support_mapping"]
        self.assertEqual(mapping["weights"], [.25, .5, .25])
        self.assertEqual(mapping["controller_sha256"], digest(reference.controller()))
        self.assertEqual(result["support_sha256"], digest(mapping))
        self.assertFalse(mapping["physical_response_qualified"]); self.assertFalse(mapping["probability_guarantee"])
        self.assertTrue(np.all(np.abs(mapping["executable_commands"]) <= 1.))
        self.assertNotEqual(mapping["executable_commands"], mapping["desired_commands"])

    def test_anchor_ablation_freezes_only_query_support(self):
        measure = DesiredMeasure(((.8, 0.),), (1.,)); anchor = rotated_reference()
        current = GaussianReference((1., 0., 0., 0., 1., 0.), np.asarray(anchor.covariance) / 2, np.eye(2), .1, "past-twelve")
        frozen = choose(current, measure, 488, 12, anchor=anchor)
        adaptive = choose(current, measure, 488, 12)
        self.assertEqual(frozen["support_mapping"], support_map(anchor, measure))
        self.assertNotEqual(frozen["support_mapping"], adaptive["support_mapping"])
        self.assertEqual(frozen["evidence_digest"], "past-twelve")
        self.assertEqual(frozen["support_mapping"]["evidence_digest"], "past-eight")

    def test_strict_evidence_budget_and_measure_contracts(self):
        reference = rotated_reference(); measure = DesiredMeasure(((.8, 0.),), (1.,))
        for commands, weights in (((), ()), (((2., 0.),), (1.,)), (((.2, 0.),), (.5,)), (((.2, 0.),), (True,)), (((.2, 0.),), (float("nan"),))):
            with self.assertRaises(ValueError): DesiredMeasure(commands, weights)
        for remaining, used in ((35, 8), (492, 16), (True, 8)):
            with self.assertRaises(ValueError): choose(reference, measure, remaining, used)
        with self.assertRaises(ValueError): choose(reference.controller(), measure, 492, 8)
        with self.assertRaises(ValueError): choose(reference, {"commands": [[.8, 0.]], "weights": [1.]}, 492, 8)
        for forbidden in ("seed", "true_operator", "rng_state", "future_outcome"):
            with self.assertRaises(TypeError): choose(reference, measure, 492, 8, **{forbidden: 1})
            with self.assertRaises(TypeError): DesiredMeasure(commands=((.8, 0.),), weights=(1.,), **{forbidden: 1})


class SupportExecutionTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        def emit(kind, payload):
            item = {"event": kind, "sequence": len(self.events) + 1, "saved_ns": run.perf_counter_ns(), **run.normal(payload)}
            self.events.append(item); return item
        self.emit = emit; self.ledger = LifecycleLedger(emit, 1000000)
        self.factory = SimpleNamespace(_make_tasks=lambda: None)
        self.key = {"experiment_run_id": "test", "manifest_id": "manifest", "source_git_commit": "source", "stream": 0,
                    "task": "push-v3", "replicate": 0, "seed": 11800, "operator_id_oracle": "A"}
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

    def test_all_nine_saved_policies_replay_with_single_reset_and_continuous_noise(self):
        with self.fixtures():
            for method in run.METHODS:
                self.events.clear(); record = self.branch(method); self.replay(record)
                self.assertEqual(record["outcome"]["environment_resets"], 1)
                self.assertLessEqual(record["outcome"]["fixed_probe_steps"] + record["outcome"]["ivr_probe_steps"], 16)
                if method.startswith("IVR_"):
                    self.assertEqual(len(record["outcome"]["selected_ivr_programs"]), 2)

    def test_primary_eight_step_state_is_shared_and_rng_substitution_is_rejected(self):
        with self.fixtures():
            reference = self.branch("IVR_TASK16"); candidate = self.branch("IVR_EXEC16")
        self.assertEqual(run.pairing(candidate, reference), "MATCHED_CONTINUATION")
        candidate["trace"][0]["rng_after"] = "changed"
        with self.assertRaises(ValueError): run.pairing(candidate, reference)

    def test_executor_uses_saved_legal_program_choice(self):
        def force(name):
            def selected(*args, **kwargs):
                return {**choose(*args, **kwargs), "action": name}
            return selected
        with self.fixtures():
            with patch.object(run, "choose_support", side_effect=force("X4")): x = self.branch("IVR_EXEC16")
            with patch.object(run, "choose_support", side_effect=force("Y4")): y = self.branch("IVR_EXEC16")
        self.assertEqual([r["command"] for r in x["trace"][8:12]], np.asarray(PRIMITIVES["X4"], np.float32).tolist())
        self.assertEqual([r["command"] for r in y["trace"][8:12]], np.asarray(PRIMITIVES["Y4"], np.float32).tolist())
        self.assertNotEqual(x["trace"][8]["after"], y["trace"][8]["after"])

    def test_rehashed_support_substitution_is_rejected_by_causal_recomputation(self):
        with self.fixtures():
            record = self.branch("IVR_EXEC16")
        decision = next(d for d in record["decisions"] if d["action"] == "REQUEST_IVR_PROBE")
        decision["validation"]["support_mapping"]["executable_commands"][0][0] += .01
        decision["validation"]["support_sha256"] = digest(decision["validation"]["support_mapping"])
        item = next(e for e in self.events if e["sequence"] == decision["sequence"])
        item["validation"] = copy.deepcopy(decision["validation"])
        with self.assertRaises(ValueError): self.replay(record)


class SupportDesignStatisticsTest(unittest.TestCase):
    def test_new_operator_population_and_seed_separation(self):
        c = json.loads(run.CONFIG.read_text(encoding="utf-8")); run.validate(c)
        operators = run.operators(c)
        self.assertEqual(len(operators), 16)
        self.assertEqual([r["stream"] for r in operators], list(range(16)))
        self.assertEqual(run.task_seed(15, "door-open-v3"), 11847)
        matrices = [json.dumps(r["states_oracle"][0], sort_keys=True) for r in operators]
        self.assertEqual(len(set(matrices)), 16)
        altered = {**c, "seed_start": 11500}
        with self.assertRaises(ValueError): run.validate(altered)
        with self.assertRaises(ValueError): run.validate({**c, "future_outcome": 1})

    def test_complete_denominator_cluster_interval_and_failed_population(self):
        rows = []; pairs = []
        for s in range(16):
            for t in run.TASKS:
                for repeat in range(2):
                    pairs.append({"stream": s, "task": t, "replicate": repeat, "reason": "MATCHED_CONTINUATION"})
                    for method in run.METHODS:
                        length = 150 if method == "IVR_EXEC16" else 200
                        rows.append({"stream": s, "task": t, "replicate": repeat, "method": method,
                                     "success": True, "stopped": False, "total_steps": length, "deadline_loss": length,
                                     "fixed_probe_steps": 8, "ivr_probe_steps": 8, "point_fit_failures": 0,
                                     "selected_ivr_programs": ["X4", "Y4"] if method.startswith("IVR_") else []})
        m = {"config": json.loads(run.CONFIG.read_text(encoding="utf-8"))}
        stats = audit.statistics(m, rows, pairs)
        self.assertTrue(stats["development_signal"]["passed"])
        primary = stats["candidate_contrasts"]["IVR_TASK16"]
        self.assertEqual(primary["operator_streams"], 16)
        self.assertEqual(primary["deadline_loss"]["paired_cluster_percentile_95"], [-50., -50.])
        self.assertEqual(stats["methods"]["IVR_EXEC16"]["cases"], 96)
        damaged = copy.deepcopy(rows)
        for r in damaged:
            if r["method"] == "IVR_EXEC16": r.update(success=False, stopped=True, total_steps=8, deadline_loss=500)
        failed = audit.statistics(m, damaged, pairs)
        self.assertFalse(failed["development_signal"]["passed"])
        self.assertEqual(failed["methods"]["IVR_EXEC16"]["stops"], 96)
        self.assertEqual(failed["methods"]["IVR_EXEC16"]["mean_deadline_loss"], 500)
        with self.assertRaises(ValueError): audit.statistics(m, rows[:-1], pairs)
        with self.assertRaises(ValueError): audit.statistics(m, rows, pairs[:-1] + [pairs[0]])


if __name__ == "__main__": unittest.main()
