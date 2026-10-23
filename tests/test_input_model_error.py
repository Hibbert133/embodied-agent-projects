import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from scripts import analyze_input_model_error as analysis
from src.operator_perturbations_v1 import AffineNoisePerturbation
from src.probe.forward_prediction import ForwardQuery, Predictors
from src.probe.operator_identification import affine_controller
from tests.test_operator_identification import model


class InputModelErrorTest(unittest.TestCase):
    def record(self):
        operator = {"matrix_xy": [[.75, .25], [-.15, 1.2]], "bias_xy": [.14, -.14]}
        seed = int(np.random.SeedSequence([10600, 0, 1, 0xF091]).generate_state(1)[0])
        rng = np.random.default_rng(seed)
        fault = AffineNoisePerturbation(operator["matrix_xy"], operator["bias_xy"])
        fault.reset(seed)
        before = {"observation": [0.] * 39, "success": False, "terminated": False, "truncated": False}
        initial = copy.deepcopy(before)
        trace, actual = [], []
        commands = [[1., -1., 1., .7], [.2, 0., 0., -.3], [0., -.2, 0., .5], [-.2, .1, -1., -.5]]
        for index, command in enumerate(commands, 1):
            rng_before = analysis.rng_hash(rng)
            acted = np.clip(fault.apply(np.array(command, dtype=np.float32)), -1, 1)
            actual.append(acted)
            rng.normal(0, .05, 3)
            after = copy.deepcopy(before)
            after["observation"][:3] = (np.array(before["observation"][:3]) + .01 * acted[:3]).tolist()
            trace.append({"before": before, "after": after, "command": command, "host_calls": index,
                          "rng_before": rng_before, "rng_after": analysis.rng_hash(rng), "phase": "POLICY"})
            before = after
        record = {"task": "push-v3", "seed": 10600, "operator_oracle": "GAIN_COUPLED", "initial": initial,
                  "trace": trace}
        return json.loads(json.dumps(record)), operator, np.array(actual)

    def test_exact_replayed_injection_matches_executed_float32_clip_noise(self):
        record, operator, executed = self.record()
        mean, actual = analysis.reconstruct_inputs(record, operator, .05)
        np.testing.assert_array_equal(actual, executed)
        np.testing.assert_array_equal(actual[:, 3], np.array([r["command"][3] for r in record["trace"]], dtype=np.float32))
        self.assertFalse(np.array_equal(mean[:, :3], actual[:, :3]))
        changed = copy.deepcopy(record)
        changed["trace"][2]["rng_after"] = "reseeded"
        with self.assertRaisesRegex(ValueError, "noise sequence"):
            analysis.reconstruct_inputs(changed, operator, .05)
        changed = copy.deepcopy(record)
        changed["trace"][2]["before"]["observation"][0] += .1
        with self.assertRaisesRegex(ValueError, "prefix"):
            analysis.reconstruct_inputs(changed, operator, .05)

    def test_independent_features_match_saved_predictor_after_real_history(self):
        rng = np.random.default_rng(12)
        n = 9
        observations = rng.normal(0, .1, (n, 39))
        deltas = rng.normal(0, .01, (n, 3))
        commands = rng.uniform(-1, 1, (n, 4))
        models = {name: model(name) for name in analysis.MODELS}
        for kind, value in models.items():
            size = 10 if kind == "LINEAR_ARX" else 20
            value["mean"] = rng.normal(0, .1, size).tolist()
            value["scale"] = rng.uniform(.1, 2., size).tolist()
            value["coefficients"] = rng.normal(0, .001, (value["feature_count"], 2)).tolist()
        # The production predictor also expects a nearest model; its value is unused.
        nearest = {"method": "NEAREST_STATE", "mean": [0.] * 20, "scale": [1.] * 20,
                   "training_samples": 16, "neighbors": 16, "inputs": [[0.] * 20] * 16,
                   "targets": [[0., 0.]] * 16}
        from types import SimpleNamespace
        legacy = SimpleNamespace(inertia=np.eye(2), response=np.eye(2), intercept=np.zeros(2))
        predictor = Predictors({**models, "NEAREST_STATE": nearest}, legacy)
        for kind in analysis.MODELS:
            actual = analysis.predict_batch(models[kind], observations, deltas, commands)
            expected = []
            for i in range(2, n):
                q = ForwardQuery(observations[i], deltas[i-1], deltas[i-2], commands[i])
                expected.append(predictor.predict(q)[kind])
            np.testing.assert_allclose(actual, expected, atol=1e-14, rtol=1e-13)
        poisoned = {**models["LINEAR_ARX"], "physical_response_qualified": True}
        with self.assertRaisesRegex(ValueError, "unqualified"):
            analysis.predict_batch(poisoned, observations, deltas, commands)

    def test_squared_decomposition_requires_nonzero_cross_term(self):
        mean = np.array([[2., -1.], [.5, .2]])
        actual = np.array([[1., -.2], [.1, -.1]])
        target = np.zeros((2, 2))
        r = analysis.residual_metrics(mean, actual, target)
        self.assertNotEqual(r["cross_sum"], 0.)
        self.assertAlmostEqual(r["total_squared_sum"], r["model_squared_sum"] + r["input_squared_sum"] + r["cross_sum"])
        empty = analysis.residual_metrics(np.empty((0, 2)), np.empty((0, 2)), np.empty((0, 2)))
        self.assertIsNone(empty["model_rmse_m"])
        json.dumps(empty, allow_nan=False)

    def test_rejected_fit_never_becomes_a_controller_change_pair(self):
        def declaration(index, matrix, valid=True):
            fit = {"valid": valid, "matrix_xy": matrix, "bias_xy": [0., 0.]}
            return {"sequence": index, "at_host_calls": index * 16,
                    "choice": {"fit": fit, "status": "READY_POINT_ESTIMATE" if valid else "UPDATE_REJECTED_RETAIN_PRIOR",
                               "controller": affine_controller(matrix, [0., 0.])}}
        record = {"method": "PASSIVE_LINEAR", "decisions": [declaration(1, [[1., 0.], [0., 1.]]),
                  declaration(2, [[2., 0.], [0., 2.]], False), declaration(3, [[.9, 0.], [0., 1.]])]}
        pairs = analysis.passive_fit_changes(record)
        self.assertEqual(len(pairs), 1)
        self.assertEqual((pairs[0]["from_sequence"], pairs[0]["to_sequence"]), (1, 3))
        self.assertAlmostEqual(pairs[0]["max_parameter_change"], .1)
        self.assertEqual(pairs[0]["true_operator_change_oracle"], 0.)
        record["decisions"][-1]["choice"]["controller"]["matrix_xy"][0][0] += .2
        with self.assertRaisesRegex(ValueError, "executed saved"):
            analysis.passive_fit_changes(record)

    def test_step_weighting_and_trajectory_weighting_are_distinct(self):
        small = analysis.residual_metrics(np.ones((1, 2)), np.ones((1, 2)), np.zeros((1, 2)))
        large = analysis.residual_metrics(np.ones((9, 2)) * 2, np.ones((9, 2)) * 2, np.zeros((9, 2)))
        result = analysis.aggregate([small, large])
        self.assertEqual(result["samples"], 10)
        self.assertAlmostEqual(result["model_step_weighted_rmse_m"], np.sqrt(3.7))
        self.assertEqual(result["model_mean_episode_max_m"], 1.5)

    def test_changed_audited_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.json"
            path.write_bytes(b'{"source": 1}')
            expected = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}
            analysis.verify_files(Path(directory), expected)
            path.write_bytes(b'{"source": 2}')
            with self.assertRaisesRegex(ValueError, "source bytes"):
                analysis.verify_files(Path(directory), expected)

    def test_actuator_and_composed_dynamics_worlds_are_observationally_equal(self):
        # Independent adaptive-policy witness for the conditional factorization
        # ambiguity in the design note. This does not qualify robot dynamics.
        matrix = np.array([[.75, .25], [-.15, 1.2]])
        bias = np.array([.14, -.14])
        response = np.array([[.01, .002], [-.001, .02]])
        a = b = np.array([.3, -.2])
        for t in range(40):
            command_a = np.clip(np.array([np.sin(t) - a[0], np.cos(t) - a[1]]), -.5, .5)
            command_b = np.clip(np.array([np.sin(t) - b[0], np.cos(t) - b[1]]), -.5, .5)
            injected = np.clip(matrix @ command_a + bias, -1, 1)
            a = .8 * a + response @ injected
            # Nominal actuator, but a dynamics map composed with the same input map.
            b = .8 * b + response @ np.clip(matrix @ command_b + bias, -1, 1)
            np.testing.assert_array_equal(a, b)


if __name__ == "__main__":
    unittest.main()
