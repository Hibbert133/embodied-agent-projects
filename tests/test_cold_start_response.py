from copy import deepcopy
from dataclasses import asdict
import unittest
import numpy as np

from src.probe.cold_start_response import (ColdPrefix, NominalTrajectory, clipped_normal_mean,
                                         fit_response, infer_operator, validate_model)
from src.probe.continuous import symmetric_program, ContinuousTransition
from src.probe.forward_prediction import ForwardHistory


def impulse():
    g = np.zeros((16, 16))
    for t in range(8):
        for k in range(t+1): g[2*t:2*t+2, 2*k:2*k+2] = .01*.4**(t-k)*np.eye(2)
    return g


def prefix(commands, matrix=None, bias=None):
    u = np.asarray(commands, float); matrix = np.eye(2) if matrix is None else np.asarray(matrix)
    bias = np.zeros(2) if bias is None else np.asarray(bias)
    mean = clipped_normal_mean(u[:, :2] @ matrix.T+bias)[0]
    delta = (impulse() @ mean.ravel()).reshape(8, 2)
    initial = np.zeros(39); initial[:3] = [0, .6, .2]; initial[4:7] = [.1, .7, .02]
    states = []; now = initial.copy()
    for row in delta:
        now = now.copy(); now[:2] += row; states.append(now.tolist())
    return ColdPrefix("push-v3", initial, u, states, True)


def trained():
    rng = np.random.default_rng(872)
    samples = []
    for _ in range(128):
        u = np.c_[rng.uniform(-.9, .9, (8, 2)), np.zeros((8, 2))]
        samples.append(NominalTrajectory(prefix(u)))
    return fit_response(samples, "push-v3"), samples


class ColdStartResponseTests(unittest.TestCase):
    def test_identical_ridge_design_cannot_create_new_contrast_estimator(self):
        rng = np.random.default_rng(12); z = np.c_[np.ones(24), rng.normal(size=(24, 8))]
        w = rng.uniform(.1, 1, 24); a, b = rng.normal(size=(2, 24))
        h = z.T @ (w[:, None]*z)+np.diag([0]+[1]*8)
        solve = lambda y: np.linalg.solve(h, z.T @ (w*y))
        np.testing.assert_allclose(solve(a-b), solve(a)-solve(b), atol=1e-14)

    def test_two_real_motion_observations_are_needed_before_old_queries(self):
        u = symmetric_program(.4, steps_per_direction=2); p = prefix(u)
        history = ForwardHistory(p.initial_observation); available = []
        for i, sent in enumerate(u):
            query = history.request(sent)
            if query is not None: available.append(i+1)
            history.observe(ContinuousTransition(tuple(sent), history.current, p.observations[i]))
        self.assertEqual(available, [3, 4, 5, 6, 7, 8])
        x = np.c_[np.asarray(u)[:, :2], np.ones(8)]
        full = np.linalg.inv(x.T @ x); used = np.linalg.inv(x[2:].T @ x[2:])
        self.assertAlmostEqual(used[0, 0]/full[0, 0], 3)
        self.assertAlmostEqual(used[1, 1]/full[1, 1], 1)
        self.assertAlmostEqual(np.linalg.det(x.T @ x)/np.linalg.det(x[2:].T @ x[2:]), 4)

    def test_clipped_mean_has_analytic_limits_and_correct_derivative(self):
        mu = np.array([-2., -.9, 0., .9, 2.]); mean, derivative = clipped_normal_mean(mu)
        np.testing.assert_allclose(mean, -mean[::-1], atol=1e-15)
        self.assertAlmostEqual(mean[2], 0); self.assertLess(abs(mean[0]+1), 1e-12)
        eps = 1e-6
        numerical = (clipped_normal_mean(mu+eps)[0]-clipped_normal_mean(mu-eps)[0])/(2*eps)
        np.testing.assert_allclose(derivative, numerical, atol=1e-9)

    def test_schema_excludes_oracle_future_seed_and_virtual_history(self):
        p = prefix(symmetric_program(.4, steps_per_direction=2)); data = asdict(p)
        for field in ("seed", "matrix_xy", "future_outcome", "executed_action_oracle"):
            with self.assertRaises(ValueError): ColdPrefix.from_dict({**data, field: 1})
        with self.assertRaises(ValueError): ColdPrefix.from_dict({**data, "controlled_reset_completed": False})
        with self.assertRaises(ValueError): NominalTrajectory(p, "QUALIFY")

    def test_independent_nominal_joint_fit_recovers_operator_without_truth_input(self):
        model, _ = trained(); a = [[.8, -.2], [.1, 1.2]]; b = [.07, -.05]
        p = prefix(symmetric_program(.4, steps_per_direction=2), a, b)
        for drop in (False, True):
            result = infer_operator(model, p, drop)
            self.assertTrue(result["valid"]); self.assertFalse(result["probability_guarantee"])
            np.testing.assert_allclose(result["matrix_xy"], a, atol=2e-5)
            np.testing.assert_allclose(result["bias_xy"], b, atol=2e-5)
            self.assertEqual(result["observed_rows_used"], 6 if drop else 8)

    def test_mean_model_never_reads_future_commands(self):
        model, samples = trained(); changed = []
        for sample in samples:
            data = asdict(sample.prefix); u = np.asarray(data["commands"]); u[4:, :2] *= -1
            data["commands"] = u; changed.append(NominalTrajectory(ColdPrefix.from_dict(data)))
        other = fit_response(changed, "push-v3")
        np.testing.assert_array_equal(np.asarray(model["impulse"])[:8], np.asarray(other["impulse"])[:8])
        np.testing.assert_array_equal(np.asarray(model["offset"])[:8], np.asarray(other["offset"])[:8])

    def test_scope_incomplete_prefix_and_future_parameter_leak_fail_closed(self):
        model, _ = trained(); p = prefix(symmetric_program(.4, steps_per_direction=2))
        data = asdict(p); data["commands"] = data["commands"][:4]; data["observations"] = data["observations"][:4]
        self.assertEqual(infer_operator(model, ColdPrefix.from_dict(data))["reason"], "INCOMPLETE_EIGHT_STEP_PREFIX")
        data = asdict(p); data["initial_observation"] = [*data["initial_observation"]]; data["initial_observation"][0] = .2
        self.assertEqual(infer_operator(model, ColdPrefix.from_dict(data))["reason"], "OUTSIDE_CONTROLLED_RESET_SCOPE")
        altered = deepcopy(model); altered["impulse"][0][15] = 1e-15
        with self.assertRaises(ValueError): validate_model(altered)
        altered = deepcopy(model); altered["initial_hand_lower"][0] = float("nan")
        with self.assertRaises(ValueError): validate_model(altered)


if __name__ == "__main__": unittest.main()
