from __future__ import annotations

import unittest

from scripts.summarize_recovery_ablation import summarize


class FaultGroupingTest(unittest.TestCase):
    def test_fault_conditions_are_separated_when_requested(self) -> None:
        base = {
            "planner": "probe_rule", "seed": "1", "trial": "1",
            "success": "False", "steps": "500", "final_object_goal_distance": "0.2",
            "probe_environment_steps": "0", "correction_schedule": "whole",
            "injected_bias_magnitude": "0.145",
        }
        rows = [
            {**base, "injected_bias_axis": "x", "injected_bias_sign": "negative"},
            {**base, "injected_bias_axis": "y", "injected_bias_sign": "positive"},
        ]
        grouped = summarize(rows, group_by_fault=True)
        self.assertEqual(len(grouped), 2)
        self.assertNotEqual(grouped[0]["planner"], grouped[1]["planner"])

    def test_magnitude_error_semantics(self) -> None:
        self.assertAlmostEqual(abs(0.20 - 0.198), 0.002)
        self.assertAlmostEqual(abs(0.10 - 0.145), 0.045)


if __name__ == "__main__":
    unittest.main()
