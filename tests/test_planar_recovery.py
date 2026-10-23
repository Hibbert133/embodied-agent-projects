from __future__ import annotations

import unittest

import numpy as np

from src.planar_recovery import estimate_planar_correction


class PlanarRecoveryTest(unittest.TestCase):
    def test_estimate_uses_both_visible_drift_components(self) -> None:
        context = {
            "inference": {
                "estimated_drift_per_step": (0.03, -0.02),
                "axis_response_gain": (0.5, 0.5),
                "residual": 0.001,
            }
        }
        estimate = estimate_planar_correction(
            context, allowed_magnitudes=(0.0, 0.04, 0.06, 0.10)
        )
        np.testing.assert_allclose(estimate.estimated_action_bias, (0.06, -0.04))
        np.testing.assert_allclose(
            estimate.simultaneous_correction, (-0.06, 0.04, 0.0, 0.0)
        )
        self.assertEqual(estimate.dominant_axis, "x")
        np.testing.assert_allclose(
            estimate.dominant_axis_correction, (-0.06, 0.0, 0.0, 0.0)
        )

    def test_estimate_rejects_missing_or_invalid_inference(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires probe inference"):
            estimate_planar_correction({}, allowed_magnitudes=(0.0, 0.1))
        with self.assertRaisesRegex(ValueError, "two-dimensional"):
            estimate_planar_correction(
                {"inference": {"estimated_drift_per_step": (0.1,), "axis_response_gain": (1.0,)}},
                allowed_magnitudes=(0.0, 0.1),
            )


if __name__ == "__main__":
    unittest.main()
