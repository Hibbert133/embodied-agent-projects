from __future__ import annotations

import unittest

import numpy as np

from src.diagnosis import estimate_phase_conditioned_response


def make_rows(noisy_push: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    observation = np.zeros(39, dtype=float)
    observation[0:3] = (0.0, 0.60, 0.20)
    observation[4:7] = (0.0, 0.70, 0.02)
    observation[-3:] = (0.0, 0.85, 0.02)
    commands = [(-0.5, 0.2), (0.5, -0.2), (-0.3, 0.4), (0.3, -0.4)] * 4
    for step, (command_x, command_y) in enumerate(commands, start=1):
        next_observation = observation.copy()
        noise = 0.004 * (-1.0 if step % 2 else 1.0) if noisy_push and step > 8 else 0.0
        next_observation[0] += 0.01 * command_x + 0.001 + noise
        next_observation[1] += 0.01 * command_y - 0.001 - noise
        if step == 8:
            next_observation[4:7] = next_observation[0:3] + np.array([0.0, 0.02, 0.0])
        rows.append(
            {
                "schema_version": 2,
                "episode_id": 1,
                "seed": 1,
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


class PhaseConditionedDiagnosisTest(unittest.TestCase):
    def test_separates_approach_and_push_without_oracle_fields(self) -> None:
        estimate = estimate_phase_conditioned_response(make_rows())
        self.assertEqual(estimate.phase_sample_counts["approach"], 8)
        self.assertEqual(estimate.phase_sample_counts["push"], 8)
        self.assertEqual(
            [phase.phase for phase in estimate.phase_estimates], ["approach", "push"]
        )
        self.assertLess(estimate.phase_inconsistency, 1e-6)

    def test_within_push_variation_increases_inconsistency(self) -> None:
        stable = estimate_phase_conditioned_response(make_rows(False))
        noisy = estimate_phase_conditioned_response(make_rows(True))
        self.assertGreater(noisy.phase_inconsistency, stable.phase_inconsistency)

    def test_rejects_broken_causal_continuity(self) -> None:
        rows = make_rows()
        rows[1]["observation"] = np.ones(39).tolist()
        with self.assertRaisesRegex(ValueError, "state-continuous"):
            estimate_phase_conditioned_response(rows)


if __name__ == "__main__":
    unittest.main()
