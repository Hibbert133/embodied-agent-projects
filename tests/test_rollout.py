from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.perturbations import ActionBiasPerturbation, IdentityPerturbation
from src.rollout import run_episode


class FakeActionSpace:
    def __init__(self) -> None:
        self.low = np.array([-1.0], dtype=np.float32)
        self.high = np.array([1.0], dtype=np.float32)


class FakeEnvironment:
    def __init__(self, episode_length: int = 3) -> None:
        self.action_space = FakeActionSpace()
        self.episode_length = episode_length
        self.actions: list[np.ndarray] = []

    def reset(self, seed: int) -> tuple[np.ndarray, dict]:
        self.actions = []
        return np.array([float(seed)], dtype=np.float32), {}

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict]:
        self.actions.append(np.asarray(action).copy())
        count = len(self.actions)
        return (
            np.array([float(count)], dtype=np.float32),
            1.0,
            False,
            count >= self.episode_length,
            {"success": count == 2},
        )


class SequencePolicy:
    def __init__(self, actions: list[float]) -> None:
        self.actions = actions
        self.index = 0

    def get_action(self, observation: np.ndarray) -> np.ndarray:
        action = self.actions[self.index % len(self.actions)]
        self.index += 1
        return np.array([action], dtype=np.float32)


class RolloutPerturbationTest(unittest.TestCase):
    def test_executed_actions_are_clipped_and_statistics_are_correct(self) -> None:
        env = FakeEnvironment(episode_length=3)
        policy = SequencePolicy([0.0, 2.0, -2.0])
        with tempfile.TemporaryDirectory() as directory:
            trajectory = Path(directory) / "trajectory.jsonl"
            result = run_episode(
                env,
                policy,
                seed=7,
                max_steps=3,
                trajectory_path=trajectory,
                stop_on_success=False,
            )
        self.assertTrue(all(np.all(action <= 1.0) for action in env.actions))
        self.assertTrue(all(np.all(action >= -1.0) for action in env.actions))
        self.assertEqual(result.clip_count, 2)
        self.assertAlmostEqual(result.clip_fraction, 2 / 3)

    def test_bias_clipping_is_counted(self) -> None:
        env = FakeEnvironment(episode_length=2)
        result = run_episode(
            env,
            SequencePolicy([0.5]),
            seed=7,
            max_steps=2,
            perturbation=ActionBiasPerturbation(1.0),
            stop_on_success=False,
        )
        self.assertEqual(result.clip_count, 2)
        self.assertEqual(result.clip_fraction, 1.0)
        np.testing.assert_array_equal(env.actions[0], np.array([1.0]))

    def test_identity_matches_unperturbed_baseline(self) -> None:
        baseline = run_episode(
            FakeEnvironment(),
            SequencePolicy([0.25]),
            seed=9,
            max_steps=3,
            perturbation=None,
        )
        identity = run_episode(
            FakeEnvironment(),
            SequencePolicy([0.25]),
            seed=9,
            max_steps=3,
            perturbation=IdentityPerturbation(),
        )
        self.assertEqual(baseline.success, identity.success)
        self.assertEqual(baseline.steps, identity.steps)
        self.assertEqual(baseline.episode_return, identity.episode_return)
        self.assertEqual(baseline.clip_count, identity.clip_count)
        self.assertEqual(baseline.clip_fraction, identity.clip_fraction)


if __name__ == "__main__":
    unittest.main()
