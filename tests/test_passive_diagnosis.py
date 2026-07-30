from __future__ import annotations

import unittest

import numpy as np

from src.diagnosis import estimate_passive_planar_drift


def make_agent_transitions() -> list[dict[str, object]]:
    commands = [
        (-0.5, 0.1), (0.5, -0.1), (-0.3, 0.4), (0.3, -0.4),
        (-0.2, -0.5), (0.2, 0.5), (-0.4, 0.3), (0.4, -0.3),
    ]
    observation = np.zeros(39, dtype=float)
    observation[-3:] = (0.1, 0.8, 0.02)
    rows = []
    for step, (command_x, command_y) in enumerate(commands, start=1):
        next_observation = observation.copy()
        next_observation[0] += 0.02 * command_x + 0.003
        next_observation[1] += 0.03 * command_y - 0.002
        rows.append(
            {
                "schema_version": 2,
                "episode_id": 1,
                "seed": 7,
                "step": step,
                "observation": observation.tolist(),
                "next_observation": next_observation.tolist(),
                "commanded_action": [command_x, command_y, 0.0, 1.0],
                "reward": 0.0,
                "success": False,
                "terminated": False,
                "truncated": False,
                "task_progress_metrics": {},
            }
        )
        observation = next_observation
    return rows


class PassiveDiagnosisTest(unittest.TestCase):
    def test_recovers_known_visible_local_model(self) -> None:
        estimate = estimate_passive_planar_drift(make_agent_transitions())
        np.testing.assert_allclose(estimate.axis_response_gain, (0.02, 0.03), atol=1e-10)
        np.testing.assert_allclose(
            estimate.estimated_drift_per_step, (0.003, -0.002), atol=1e-10
        )
        self.assertEqual(estimate.dominant_axis, "x")
        self.assertEqual(estimate.estimated_direction, "positive")
        self.assertLess(estimate.uncertainty, 1e-6)

    def test_rejects_broken_transition_continuity(self) -> None:
        rows = make_agent_transitions()
        rows[1]["observation"] = np.ones(39).tolist()
        with self.assertRaisesRegex(ValueError, "state-continuous"):
            estimate_passive_planar_drift(rows)

    def test_rejects_oracle_trajectory_rows(self) -> None:
        rows = make_agent_transitions()
        del rows[0]["commanded_action"]
        with self.assertRaisesRegex(ValueError, "commanded_action"):
            estimate_passive_planar_drift(rows)


if __name__ == "__main__":
    unittest.main()
