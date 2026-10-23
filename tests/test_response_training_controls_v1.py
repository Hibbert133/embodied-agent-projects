"""Pure-array causal histories, weighting, loss geometry and strong references."""
from copy import deepcopy
from dataclasses import replace, asdict
import hashlib
import unittest
import numpy as np
import numpy.testing

from src.probe import response_training_controls_v1 as core
from src.probe.observable_history_model_v1 import HistoryTrajectory, targets


def trajectory(n=30, key="SYNTHETIC", split="TRAIN"):
    rng = np.random.default_rng(981704)
    commands = rng.uniform(-.7, .7, (n, 4)); state = np.zeros(39); observations = []
    for command in commands:
        state = state.copy(); state[:2] += .002*command[:2]; state[2] += .0003*command[2]; state[3] = command[3]
        state[4:7] = [.1, .5, .02]; state[-3:] = [.2, .7, .1]; observations.append(state)
    return HistoryTrajectory("push-v3", key, split, np.zeros(39), commands, observations)


def gru(feature, loss, window, t):
    rng = np.random.default_rng(83818)
    return {"schema": "TRAINING_CONTROL_GRU_V1", "task": t.task, "feature": feature, "window": window,
        "stats": core.statistics([t], t.task, feature, loss), "output_weight": rng.normal(0, .1, (2, 32)).tolist(), "output_bias": [0., 0.],
        "gru": {k: rng.normal(0, .1, shape).tolist() for k, shape in (("weight_ih_l0", (96, 43)), ("weight_hh_l0", (96, 32)), ("bias_ih_l0", (96,)), ("bias_hh_l0", (96,)))}}


class TrainingControlsTests(unittest.TestCase):
    def test_all_feature_shapes_and_real_first_displacements(self):
        t = trajectory()
        a, b = core.feature_array(t, "F20"), core.feature_array(t, "F43")
        self.assertEqual(a.shape, (28, 20)); self.assertEqual(b.shape, (28, 43))
        state = np.asarray([t.initial, *t.observations])
        np.testing.assert_array_equal(b[0, :39], state[2])
        np.testing.assert_allclose(a[0, 3:6], state[2, :3]-state[1, :3])
        np.testing.assert_allclose(a[0, 6:9], state[1, :3]-state[0, :3])
        np.testing.assert_array_equal(a[0, 9:13], t.commands[2])

    def test_first_window_is_same_real_t2_for_both_features(self):
        t = trajectory()
        for feature in core.FEATURES:
            stats = core.statistics([t], t.task, feature, "ISO")
            x, y, lengths = core.prepared(t, stats, 16)
            self.assertEqual(lengths.tolist(), list(range(1, 17))+[16]*12)
            np.testing.assert_array_equal(x[0, 1:], 0)
            np.testing.assert_allclose(x[0, 0], core.frames(t, stats)[0], atol=1e-6)
            np.testing.assert_allclose(y[0]*stats["target_scale"]+stats["target_mean"], targets(t)[0], atol=1e-10)

    def test_future_observation_and_commands_cannot_change_early_predictions(self):
        t = trajectory(); observations = np.asarray(t.observations).copy(); observations[15:] += .1
        commands = np.asarray(t.commands).copy(); commands[16:] *= -.5
        future = replace(t, observations=observations, commands=commands)
        for feature in core.FEATURES:
            for loss in core.LOSSES:
                for window in core.WINDOWS:
                    m = gru(feature, loss, window, t)
                    a, b = core.predict(m, t), core.predict(m, future)
                    np.testing.assert_array_equal(a[:14], b[:14])
                    self.assertFalse(np.array_equal(a[15:], b[15:]))

    def test_known_linear_response_in_all_three_references(self):
        ts = [trajectory(35, "A"), trajectory(21, "B")]
        for feature in ("H10", "F20", "F43"):
            model = core.fit_linear(ts, ts[0].task, feature)
            self.assertLess(float(np.sqrt(np.mean((core.predict(model, ts[0])-targets(ts[0]))**2))), 1e-5)
            self.assertFalse(model["probability_guarantee"])

    def test_trajectory_weighting_is_not_timestep_weighting(self):
        a, b = trajectory(9, "A"), trajectory(80, "B")
        altered = np.asarray(b.observations); altered[:, 8] += 7
        b = replace(b, observations=altered)
        stats = core.statistics([a, b], a.task, "F43", "ISO")
        expected = (core.feature_array(a, "F43").mean(axis=0)+core.feature_array(b, "F43").mean(axis=0))/2
        np.testing.assert_allclose(stats["input_mean"], expected, atol=1e-14)
        model = core.fit_linear([a, b], a.task, "F43")
        np.testing.assert_allclose(model["stats"]["input_mean"], expected, atol=1e-14)

    def test_isotropic_scale_and_loss_algebra(self):
        t = trajectory(); iso = core.statistics([t], t.task, "F20", "ISO"); axis = core.statistics([t], t.task, "F20", "AXIS")
        self.assertEqual(iso["target_scale"][0], iso["target_scale"][1])
        self.assertAlmostEqual(iso["target_scale"][0]**2, np.mean(np.asarray(axis["target_scale"])**2))
        error = np.array([[.001, .003], [-.002, .004]])
        self.assertAlmostEqual(np.mean((error/iso["target_scale"])**2)*iso["target_scale"][0]**2, np.mean(error**2))
        np.testing.assert_allclose(iso["input_mean"], axis["input_mean"])
        np.testing.assert_allclose(iso["input_scale"], axis["input_scale"])

    def test_f20_padding_never_adds_state_information(self):
        t = trajectory(); m = core.statistics([t], t.task, "F20", "ISO")
        frame = core.frames(t, m)
        np.testing.assert_array_equal(frame[:, 20:], 0)
        self.assertEqual(frame.shape[1], 43)
        self.assertEqual(7458-23*96, 5250)

    def test_small_and_constant_scale_use_frozen_rule(self):
        t = trajectory(); obs = np.asarray(t.observations); obs[:, 27] = np.arange(len(obs))*1e-10
        t = replace(t, observations=obs)
        s = core.statistics([t], t.task, "F43", "ISO")
        self.assertEqual(s["input_scale"][27], 1.)
        self.assertEqual(s["input_scale"][17], 1.)

    def test_cal_test_duplicate_and_empty_training_rejected(self):
        for split in ("CAL", "TEST"):
            with self.assertRaises(ValueError):
                core.statistics([trajectory(split=split)], "push-v3", "F20", "ISO")
        t = trajectory()
        with self.assertRaises(ValueError): core.statistics([t, t], t.task, "F20", "ISO")
        with self.assertRaises(ValueError): core.statistics([trajectory(2)], t.task, "F20", "ISO")

    def test_private_or_nonfinite_trajectory_fields_rejected(self):
        raw = asdict(trajectory())
        for name in ("oracle", "seed", "actual_noise", "future_results", "executed_action_oracle"):
            with self.assertRaises(ValueError): HistoryTrajectory.from_dict(raw | {name: {"nested": 0}})
        bad = deepcopy(raw); bad["initial"] = [float("nan")]*39
        with self.assertRaises(ValueError): HistoryTrajectory.from_dict(bad)

    def test_batch_sampling_schedule_has_real_indices_and_is_reproducible(self):
        ts = [trajectory(9, "A"), trajectory(26, "B")]
        digests = []
        for feature in core.FEATURES:
            for loss in core.LOSSES:
                for window in core.WINDOWS:
                    rng = np.random.default_rng(8877); digest = hashlib.sha256()
                    cache = [core.prepared(t, core.statistics(ts, "push-v3", feature, loss), window) for t in ts]
                    for _ in range(20):
                        chosen, positions = core.schedule(rng, ts)
                        x, y, lengths = core.minibatch(cache, chosen, positions)
                        self.assertEqual(x.shape, (32, window, 43)); self.assertEqual(y.shape, (32, 2))
                        self.assertTrue(all(0 <= p < len(ts[c].commands)-2 for c, p in zip(chosen, positions)))
                        self.assertTrue(all(1 <= n <= window for n in lengths))
                        digest.update(np.asarray([chosen, positions+2], dtype="<i8").tobytes())
                    digests.append(digest.hexdigest())
        self.assertEqual(len(set(digests)), 1)

    def test_prediction_does_not_mutate_saved_parameters(self):
        t = trajectory(); m = gru("F20", "ISO", 16, t); before = deepcopy(m)
        core.predict(m, t)
        self.assertEqual(m, before)
        with self.assertRaises(ValueError): core.predict(m, replace(t, task="reach-v3"))

    def test_empty_prediction_and_illegal_controls(self):
        t = trajectory(); m = gru("F43", "AXIS", 1, t)
        for n in (0, 1, 2): self.assertEqual(core.predict(m, trajectory(n)).shape, (0, 2))
        for window in (0, 2, 15):
            with self.assertRaises(ValueError): core.prepared(t, m["stats"], window)
        with self.assertRaises(ValueError): core.statistics([t], t.task, "F21", "ISO")
        with self.assertRaises(ValueError): core.statistics([t], t.task, "F20", "MSE_AFTER_TEST_TUNING")


if __name__ == "__main__":
    unittest.main()
