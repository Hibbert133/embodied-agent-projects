import unittest
import hashlib
import json
from pathlib import Path
from dataclasses import asdict
import numpy as np
from src.probe.cold_start_response import ColdPrefix, RIDGE, SCOPE
from src.probe.cold_cache_prediction import PredictionQuery, SourceBelief, forecast, response, score, source_belief


def fixture():
    initial = np.zeros(39); initial[:3] = (0, 0, .2); initial[4:7] = (.5, .5, .2)
    commands = ((.4, 0, 0, 0), (-.4, 0, 0, 0), (0, .4, 0, 0), (0, -.4, 0, 0))*2
    model = {"schema": "cold_response_v1", "task": "push-v3", "scope": SCOPE, "training_trajectories": 128,
             "sigma": .05, "ridge": RIDGE, "offset": [0.]*16, "impulse": (.01*np.eye(16)).tolist(),
             "covariance": (1e-6*np.eye(16)).tolist(), "initial_hand_lower": [-1.]*3,
             "initial_hand_upper": [1.]*3, "minimum_initial_object_distance": .08,
             "training_joint_rmse_m": .001, "physical_response_qualified": False, "probability_guarantee": False}
    parameters = (1., 0., 0., 0., 1., 0.)
    query = PredictionQuery("push-v3", tuple(initial), commands, True)
    mu = response(model, query, parameters)[0].reshape(8, 2)
    states = []; current = initial.copy()
    for displacement in mu:
        current = current.copy(); current[:2] += displacement; states.append(tuple(current))
    prefix = ColdPrefix(query.task, query.initial_observation, commands, tuple(states), True)
    return model, parameters, query, prefix


class CachePredictionTest(unittest.TestCase):
    def test_registered_source_digests_match_exact_bytes(self):
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root/"configs/cross_task_cache_validity/development_v1.json").read_text(encoding="utf-8"))
        for key in ("bridge_manifest", "bridge_audit", "bridge_costs"):
            expected = config[key+"_sha256"]
            self.assertEqual(len(bytes.fromhex(expected)), 32)
            self.assertEqual(expected, hashlib.sha256((root/config[key]).read_bytes()).hexdigest())

    def test_jacobian_matches_central_difference_including_clipping(self):
        model, _, query, _ = fixture(); parameters = np.array([1.9, .1, .25, .05, 1.7, -.2])
        analytic = response(model, query, parameters)[1]
        numeric = np.column_stack([(response(model, query, parameters+1e-6*d)[0]-response(model, query, parameters-1e-6*d)[0])/2e-6 for d in np.eye(6)])
        np.testing.assert_allclose(analytic, numeric, rtol=1e-7, atol=1e-10)

    def test_local_information_inverse_matches_direct_linear_reference(self):
        model, parameters, query, prefix = fixture(); cached = source_belief(model, prefix, parameters)
        x = np.c_[np.array(query.commands)[:, :2], np.ones(8)]
        expected = np.kron(np.eye(2), .01*np.linalg.inv(x.T @ x))
        np.testing.assert_allclose(cached.covariance, expected, atol=1e-14)

    def test_prediction_covariance_addition_and_zero_residual(self):
        model, parameters, query, prefix = fixture(); cached = source_belief(model, prefix, parameters)
        plug = forecast(model, query, cached, "PLUGIN"); propagated = forecast(model, query, cached, "SOURCE_UNCERTAINTY")
        jacobian = response(model, query, parameters)[1]
        np.testing.assert_allclose(np.array(propagated["covariance"])-plug["covariance"], jacobian @ cached.covariance @ jacobian.T, atol=1e-18)
        self.assertLess(score(plug, prefix)["statistic"], 1e-20)
        self.assertGreater(score(plug, prefix)["nominal_three_look_threshold"], score(plug, prefix)["nominal_threshold_95"])

    def test_hidden_or_future_fields_are_rejected(self):
        _, _, query, _ = fixture()
        for key in ("observations", "future_outcome", "operator_id_oracle", "seed", "rng"):
            with self.assertRaises(ValueError): PredictionQuery.from_dict({**asdict(query), key: 0})

    def test_bad_covariance_and_cache_labels_are_rejected(self):
        model, parameters, _, prefix = fixture(); cached = source_belief(model, prefix, parameters)
        with self.assertRaises(ValueError): SourceBelief.from_dict({**asdict(cached), "bias_oracle": [0, 0]})
        with self.assertRaises((ValueError, np.linalg.LinAlgError)): SourceBelief.from_dict({**asdict(cached), "covariance": np.zeros((6, 6))})

    def test_unrequested_responses_and_mismatched_commands_are_rejected(self):
        model, parameters, query, prefix = fixture(); cached = source_belief(model, prefix, parameters)
        small = PredictionQuery(query.task, query.initial_observation, query.commands[:2], True)
        prediction = forecast(model, small, cached, "SOURCE_UNCERTAINTY")
        with self.assertRaises(ValueError): score(prediction, prefix)
        altered = ColdPrefix(prefix.task, prefix.initial_observation, ((.2, 0, 0, 0), *prefix.commands[1:2]), prefix.observations[:2], True)
        with self.assertRaises(ValueError): score(prediction, altered)

    def test_scope_and_mode_are_not_silently_relaxed(self):
        model, parameters, query, prefix = fixture(); cached = source_belief(model, prefix, parameters)
        with self.assertRaises(ValueError): forecast(model, query, cached, "REPAIR")
        with self.assertRaises(ValueError): PredictionQuery(query.task, query.initial_observation, query.commands[:3], True)
        invalid = list(query.initial_observation); invalid[4:7] = invalid[:3]
        with self.assertRaises(ValueError): forecast(model, PredictionQuery(query.task, tuple(invalid), query.commands, True), cached, "PLUGIN")

    def test_source_response_changes_do_not_change_fixed_point_forecast(self):
        model, parameters, query, prefix = fixture()
        altered_states = tuple(tuple(v+.0001 if i < 2 else v for i, v in enumerate(row)) for row in prefix.observations)
        altered = ColdPrefix(prefix.task, prefix.initial_observation, prefix.commands, altered_states, True)
        left = source_belief(model, prefix, parameters); right = source_belief(model, altered, parameters)
        self.assertNotEqual(left.evidence_sha256, right.evidence_sha256)
        np.testing.assert_array_equal(forecast(model, query, left, "SOURCE_UNCERTAINTY")["mean"], forecast(model, query, right, "SOURCE_UNCERTAINTY")["mean"])

    def test_changed_cached_parameters_change_prediction(self):
        model, parameters, query, prefix = fixture(); cached = source_belief(model, prefix, parameters)
        altered = SourceBelief.from_dict({**asdict(cached), "parameters": (1., 0., .1, 0., 1., -.1)})
        left = forecast(model, query, cached, "SOURCE_UNCERTAINTY")
        right = forecast(model, query, altered, "SOURCE_UNCERTAINTY")
        self.assertFalse(np.allclose(left["mean"], right["mean"]))
        self.assertGreater(score(right, prefix)["statistic"], score(left, prefix)["statistic"])

    def test_source_uncertainty_lowers_quadratic_score_without_changing_mean(self):
        model, parameters, query, prefix = fixture(); cached = source_belief(model, prefix, parameters)
        wrong = SourceBelief.from_dict({**asdict(cached), "parameters": (1., 0., .1, 0., 1., -.1)})
        plug = forecast(model, query, wrong, "PLUGIN")
        propagated = forecast(model, query, wrong, "SOURCE_UNCERTAINTY")
        np.testing.assert_array_equal(plug["mean"], propagated["mean"])
        self.assertGreater(score(plug, prefix)["statistic"], score(propagated, prefix)["statistic"])


if __name__ == "__main__":
    unittest.main()
