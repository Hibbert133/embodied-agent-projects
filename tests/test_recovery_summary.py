from __future__ import annotations

import unittest

from scripts.summarize_recovery_ablation import summarize


class RecoverySummaryTest(unittest.TestCase):
    def test_probe_steps_are_counted_once_per_episode(self) -> None:
        rows = [
            {"planner": "probe_rule", "seed": "1", "trial": "1", "success": "False", "steps": "500", "probe_environment_steps": "0", "final_object_goal_distance": "0.2"},
            {"planner": "probe_rule", "seed": "1", "trial": "2", "success": "True", "steps": "70", "probe_environment_steps": "32", "final_object_goal_distance": "0.04"},
        ]
        result = summarize(rows)[0]
        self.assertEqual(result["successes"], 1)
        self.assertEqual(result["mean_rollout_steps"], 570)
        self.assertEqual(result["mean_probe_steps"], 32)
        self.assertEqual(result["mean_total_environment_steps"], 602)
        self.assertEqual(result["initial_failures"], 1)
        self.assertEqual(result["recovered_initial_failures"], 1)
        self.assertEqual(result["conditional_recovery_rate"], 1.0)
        self.assertEqual(result["mean_recovery_trial_steps"], 70)


if __name__ == "__main__":
    unittest.main()
