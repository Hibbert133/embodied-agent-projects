from __future__ import annotations

import unittest

import numpy as np

from src.perturbations import (
    ActionBiasPerturbation,
    ActionScalePerturbation,
    GaussianNoisePerturbation,
    IdentityPerturbation,
)


class PerturbationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.action = np.array([0.5, -0.25, 1.0, -1.0], dtype=np.float32)

    def test_identity_does_not_modify_action(self) -> None:
        perturbation = IdentityPerturbation()
        perturbation.reset(42)
        result = perturbation.apply(self.action)
        np.testing.assert_array_equal(result, self.action)
        self.assertIsNot(result, self.action)

    def test_action_scale_is_correct(self) -> None:
        perturbation = ActionScalePerturbation(0.4)
        perturbation.reset(42)
        np.testing.assert_allclose(
            perturbation.apply(self.action), self.action * 0.4
        )

    def test_noise_is_identical_for_the_same_episode_seed(self) -> None:
        first = GaussianNoisePerturbation(0.1)
        second = GaussianNoisePerturbation(0.1)
        first.reset(123)
        second.reset(123)
        for _ in range(3):
            np.testing.assert_array_equal(
                first.apply(self.action), second.apply(self.action)
            )

    def test_action_bias_is_correct(self) -> None:
        perturbation = ActionBiasPerturbation([0.1, 0.0, -0.1, 0.2])
        perturbation.reset(42)
        np.testing.assert_allclose(
            perturbation.apply(self.action),
            self.action + np.array([0.1, 0.0, -0.1, 0.2]),
        )


if __name__ == "__main__":
    unittest.main()

