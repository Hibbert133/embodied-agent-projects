import unittest

from src.utility_controls import choose_oracle_candidate, choose_probe_greedy


class UtilityControlsTest(unittest.TestCase):
    def test_probe_greedy_prefers_success_then_steps(self):
        evidence = [
            {
                "candidate_id": "a",
                "success_within_probe_budget": True,
                "steps": 50,
                "final_object_goal_distance": 0.04,
            },
            {
                "candidate_id": "b",
                "success_within_probe_budget": True,
                "steps": 40,
                "final_object_goal_distance": 0.05,
            },
        ]
        self.assertEqual(choose_probe_greedy(evidence), "b")

    def test_probe_greedy_uses_distance_when_both_fail(self):
        evidence = [
            {
                "candidate_id": "a",
                "success_within_probe_budget": False,
                "steps": 80,
                "final_object_goal_distance": 0.20,
            },
            {
                "candidate_id": "b",
                "success_within_probe_budget": False,
                "steps": 80,
                "final_object_goal_distance": 0.10,
            },
        ]
        self.assertEqual(choose_probe_greedy(evidence), "b")

    def test_oracle_prefers_full_success(self):
        outcomes = [
            {"candidate_id": "a", "success": False, "steps": 20,
             "final_object_goal_distance": 0.01},
            {"candidate_id": "b", "success": True, "steps": 70,
             "final_object_goal_distance": 0.05},
        ]
        self.assertEqual(choose_oracle_candidate(outcomes), "b")


if __name__ == "__main__":
    unittest.main()
