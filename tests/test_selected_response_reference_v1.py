"""Independent algebraic observations only: no new robot, task seed or API."""
from copy import deepcopy
from dataclasses import asdict
import json
import unittest
from unittest.mock import patch

import numpy as np

from src.probe import selected_response_reference_v1 as selected
from src.probe.cold_start_response import ColdPrefix, clipped_normal_mean
from src.probe.local_reprobe_v1 import SelectedAnchorWindow
from src.probe.physical_reprobe_v1 import PROGRAM, WarmWindow


def entry(rng, *, pose=None, constant=False):
    anchor = np.array([0., .7, .33]) if constant else np.array([
        rng.uniform(-.25, .25), rng.uniform(.53, .86), rng.uniform(.27, .43)])
    current = anchor+rng.uniform(-.008, .008, 3)
    if pose is not None:current = np.array(pose);anchor = current-rng.uniform(-.008, .008, 3)
    if constant:current = anchor.copy()
    positions = [current]
    for _ in range(3):positions.insert(0, positions[0]-rng.uniform(-.001, .001, 3))
    rows = []
    for position in positions:
        obs = np.zeros(39);obs[:3] = position;obs[4:7] = [current[0], current[1]+.3, .02]
        rows.append(tuple(float(x) for x in obs))
    return tuple(float(x) for x in anchor), tuple(rows)


def truth():
    h = np.zeros((4, 16, 16));h[0] = .008*np.eye(16)
    h[1] = .003*np.eye(16);h[2] = -.002*np.eye(16);h[3] = .0025*np.eye(16)
    for t in range(8):
        h[0, 2*t, 2*t+1] = .0004;h[0, 2*t+1, 2*t] = -.0003
        if t:h[0, 2*t:2*t+2, 2*t-2:2*t] = .002*np.eye(2)
    state = np.zeros((16, 15))
    state[::2, 0] = .0012;state[1::2, 1] = -.001
    state[::2, 3] = .0007;state[1::2, 4] = .0006
    state[::2, 12] = .0003;state[1::2, 13] = -.0004
    return h, state


def observations(anchor, history, commands, parameters=None, noise=None):
    h, state = truth();features = selected.entry_features(history, anchor)
    impulse = h[0]+np.einsum("k,kij->ij", features[12:], h[1:])
    inputs = np.array(commands)[:, :2]
    if parameters is not None:inputs = np.c_[inputs, np.ones(8)]@np.array(parameters).reshape(2, 3).T
    delta = (state@features+impulse@clipped_normal_mean(inputs)[0].ravel()).reshape(8, 2)
    if noise is not None:delta += noise
    current = np.array(history[-1]);rows = []
    for change in delta:
        current = current.copy();current[:2] += change;rows.append(tuple(float(x) for x in current))
    return tuple(rows)


def training(count=320, *, fixed=False, constant_pose=False):
    rng = np.random.default_rng(602);rows = []
    for _ in range(count):
        anchor, history = entry(rng, constant=constant_pose)
        commands = np.array(PROGRAM) if fixed else np.c_[rng.uniform(-.8, .8, (8, 2)), np.zeros((8, 2))]
        commands = tuple(tuple(float(x) for x in row) for row in commands)
        obs = observations(anchor, history, commands, noise=rng.normal(0, 1e-7, (8, 2)))
        rows.append(selected.NominalSelectedTrajectory("push-v3", 40, anchor, history, commands, obs))
    return rows


def window(parameters, *, pose=(.20, .57, .41)):
    anchor, history = entry(np.random.default_rng(908), pose=pose)
    return SelectedAnchorWindow("push-v3", 50, anchor, history, PROGRAM,
        observations(anchor, history, PROGRAM, parameters))


class SelectedResponseReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = training()
        cls.models = {method:selected.fit_response(cls.samples, "push-v3", method=method) for method in selected.METHODS}
        cls.model = cls.models[selected.METHODS[2]]
        cls.parameters = np.array([[1.15, .12, .13], [-.08, .91, -.09]])
        cls.window = window(cls.parameters)

    def test_fresh_pose_and_history_recover_known_parameters(self):
        for pose in ((.20, .57, .41), (-.20, .81, .29), (.01, .69, .35)):
            with self.subTest(pose=pose):
                fitted = selected.infer_operator(self.model, window(self.parameters, pose=pose))
                self.assertTrue(fitted["valid"]);self.assertEqual(fitted["response_design_rank"], 6)
                np.testing.assert_allclose(fitted["matrix_xy"], self.parameters[:, :2], atol=2e-3, rtol=0)
                np.testing.assert_allclose(fitted["bias_xy"], self.parameters[:, 2], atol=2e-3, rtol=0)
                self.assertFalse(fitted["physical_response_qualified"]);self.assertFalse(fitted["probability_guarantee"])

    def test_same_data_ablations_and_pose_effect_are_real(self):
        errors = []
        for method in selected.METHODS:
            saved = self.models[method]
            self.assertEqual(saved["training_trajectories"], 320)
            fit = selected.infer_operator(saved, self.window);self.assertTrue(fit["valid"])
            errors.append(np.linalg.norm(np.array(fit["matrix_xy"])-self.parameters[:, :2])+
                np.linalg.norm(np.array(fit["bias_xy"])-self.parameters[:, 2]))
        self.assertLess(errors[2], .002);self.assertGreater(errors[0], errors[2]*20);self.assertGreater(errors[1], errors[2]*20)
        np.testing.assert_array_equal(self.models[selected.METHODS[0]]["state_response"], np.zeros((16, 15)))
        for method in selected.METHODS[:2]:
            np.testing.assert_array_equal(np.array(self.models[method]["impulse_basis"])[1:], np.zeros((3, 16, 16)))

    def test_visible_history_changes_result_without_fabricated_zero_state(self):
        data = asdict(self.window);data["entry_history"] = [data["entry_history"][-1]]*4
        altered = selected.infer_operator(self.model, SelectedAnchorWindow(**data))
        self.assertGreater(np.linalg.norm(np.array(altered["bias_xy"])-self.parameters[:, 2]), .005)

    def test_absolute_pose_changes_response_without_relabeling_relative_coordinates(self):
        a = selected.SelectedResponseProblem(self.model, self.window)
        other = window(self.parameters, pose=(-.20, .81, .29))
        b = selected.SelectedResponseProblem(self.model, other)
        self.assertGreater(np.linalg.norm(a.impulse-b.impulse), .005)
        self.assertEqual(selected.entry_features(self.window.entry_history, self.window.anchor).shape, (15,))

    def test_analytic_jacobian_including_clipping_matches_finite_difference(self):
        problem = selected.SelectedResponseProblem(self.model, self.window)
        p = np.array([1.85, 1.2, .29, -1.6, 1.7, -.27]);eps = 1e-6
        _, derivative = problem.predict(p, jacobian=True)
        numeric = np.column_stack([(problem.predict(p+eps*np.eye(6)[j])-problem.predict(p-eps*np.eye(6)[j]))/(2*eps) for j in range(6)])
        np.testing.assert_allclose(derivative, numeric, atol=1e-8, rtol=1e-5)

    def test_all_four_response_matrices_reject_future_inputs(self):
        for basis in range(4):
            bad = deepcopy(self.model);bad["impulse_basis"][basis][0][4] = 1e-10
            with self.assertRaisesRegex(ValueError, "future"):selected.validate_model(bad)

    def test_repeated_fixed_probes_cannot_train_any_method(self):
        samples = training(160, fixed=True)
        for method in selected.METHODS:
            with self.assertRaisesRegex(ValueError, "input support"):selected.fit_response(samples, "push-v3", method=method)

    def test_constant_pose_cannot_identify_pose_interactions(self):
        samples = training(160, constant_pose=True)
        selected.fit_response(samples, "push-v3", method=selected.METHODS[1])
        with self.assertRaisesRegex(ValueError, "input support"):
            selected.fit_response(samples, "push-v3", method=selected.METHODS[2])

    def test_conditional_support_rejects_exact_and_uniformly_near_confounded_inputs(self):
        rng = np.random.default_rng(334);inputs = rng.normal(size=(160, 16))
        for amount in (0., 1e-12):
            nuisance = np.c_[np.ones(160), inputs+amount*rng.normal(size=inputs.shape)]
            with self.assertRaisesRegex(ValueError, "conditioning"):selected._support(inputs, nuisance)
        result = selected._support(inputs, np.ones((160, 1)))
        self.assertEqual(result[2], 16)

    def test_outside_training_pose_rejected_before_optimizer(self):
        outside = window(self.parameters, pose=(.42, .7, .35))
        with patch.object(selected, "least_squares", side_effect=AssertionError("optimizer called")):
            fit = selected.infer_operator(self.model, outside)
        self.assertFalse(fit["valid"]);self.assertEqual(fit["nfev"], 0)
        self.assertEqual(fit["reason"], "OUTSIDE_OBSERVED_TRAINING_POSE_BOX")

    def test_missing_learned_response_stops_before_optimization(self):
        bad = deepcopy(self.model);bad["impulse_basis"] = np.zeros((4, 16, 16)).tolist()
        with patch.object(selected, "least_squares", side_effect=AssertionError("optimizer called")):
            fit = selected.infer_operator(bad, self.window)
        self.assertFalse(fit["valid"]);self.assertEqual(fit["nfev"], 0)
        self.assertEqual(fit["reason"], "INSUFFICIENT_LEARNED_RESPONSE_SUPPORT")

    def test_unstable_inverse_not_accepted(self):
        fit = selected.infer_operator(self.model, window([[.01, 0, 0], [0, 1, 0]]))
        self.assertFalse(fit["valid"]);self.assertEqual(fit["reason"], "OPTIMIZER_OR_INVERSE_DOMAIN_FAILURE")

    def test_training_old_warm_and_cold_windows_cannot_substitute(self):
        with self.assertRaises(ValueError):selected.infer_operator(self.model, self.samples[0])
        with self.assertRaises(ValueError):selected.fit_response([self.window]*160, "push-v3", method=selected.METHODS[0])
        cold = ColdPrefix("push-v3", self.window.entry_history[-1], PROGRAM, self.window.observations, True)
        with self.assertRaises(ValueError):selected.infer_operator(self.model, cold)
        anchor, history = entry(np.random.default_rng(1), pose=(0., .6, .25))
        # Construct a valid historical fixed-anchor input; type separation still rejects it.
        history = tuple(tuple((0., .6, .25)[i] if i < 3 else v for i,v in enumerate(obs)) for obs in history)
        old = WarmWindow("push-v3", 30, history, PROGRAM, observations((0., .6, .25), history, PROGRAM))
        with self.assertRaises(ValueError):selected.infer_operator(self.model, old)

    def test_old_estimator_rejects_new_model_and_new_window(self):
        from src.probe import warm_response_reference_v1 as old
        with self.assertRaises(ValueError):old.validate_model(self.model)
        with self.assertRaises(ValueError):old.WarmResponseProblem(self.model, self.window)

    def test_private_fields_and_wrong_split_rejected(self):
        for key in ("seed", "fault_oracle", "executed_actions", "rng", "future_result", "nominal_verified"):
            bad = asdict(self.samples[0]);bad[key] = {}
            with self.assertRaises(ValueError):selected.NominalSelectedTrajectory.from_mapping(bad)
            saved = deepcopy(self.model);saved[key] = {}
            with self.assertRaises(ValueError):selected.validate_model(saved)
        bad = asdict(self.samples[0]);bad["split"] = "QUALIFY"
        with self.assertRaises(ValueError):selected.NominalSelectedTrajectory.from_mapping(bad)

    def test_incomplete_nonfinite_and_unregistered_training_rejected(self):
        for change in ({"commands": PROGRAM[:7]}, {"probe_start_step": True}, {"anchor": (0., .6, float("nan"))}):
            bad = {**asdict(self.samples[0]), **change}
            with self.assertRaises(ValueError):selected.NominalSelectedTrajectory.from_mapping(bad)
        for samples, task, method in ((self.samples[:159], "push-v3", selected.METHODS[0]),
                (self.samples, "reach-v3", selected.METHODS[0]), (self.samples, "push-v3", "ORACLE")):
            with self.assertRaises(ValueError):selected.fit_response(samples, task, method=method)

    def test_saved_model_flags_ablations_and_covariance_are_checked(self):
        for key, value in (("physical_response_qualified", True), ("training_input_rank", True),
                ("training_conditional_minimum_singular", 0.), ("training_joint_rmse_m", float("nan")),
                ("pose_scale", [1, 1, 1]), ("sigma", True), ("training_hand_min", [.45, .95, .45])):
            bad = deepcopy(self.model);bad[key] = value
            with self.assertRaises(ValueError):selected.validate_model(bad)
        bad = deepcopy(self.model);bad["covariance"][0][0] = -1
        with self.assertRaises(ValueError):selected.validate_model(bad)
        bad = deepcopy(self.models[selected.METHODS[0]]);bad["state_response"][0][0] = .01
        with self.assertRaises(ValueError):selected.validate_model(bad)
        bad = deepcopy(self.models[selected.METHODS[1]]);bad["impulse_basis"][1][0][0] = .01
        with self.assertRaises(ValueError):selected.validate_model(bad)

    def test_read_only_json_roundtrip_and_all_eight_observations_used(self):
        before_model, before_window = deepcopy(self.model), deepcopy(self.window)
        fit = selected.infer_operator(json.loads(json.dumps(self.model, allow_nan=False)), self.window)
        self.assertEqual(fit["observed_rows_used"], 8);json.dumps(fit, allow_nan=False)
        self.assertEqual(self.model, before_model);self.assertEqual(self.window, before_window)
        bad = asdict(self.window);bad["observations"] = [list(row) for row in bad["observations"]]
        bad["observations"][0][0] += .001
        changed = selected.infer_operator(self.model, SelectedAnchorWindow(**bad))
        self.assertGreater(np.linalg.norm(np.array(changed["matrix_xy"])-np.array(fit["matrix_xy"])), .001)


if __name__ == "__main__":unittest.main()
