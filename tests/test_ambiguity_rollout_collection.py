import unittest

from scripts.collect_ambiguity_rollouts import compare_reference_baselines


class AmbiguityRolloutCollectionTest(unittest.TestCase):
    def test_reference_comparison_accepts_matching_execution(self) -> None:
        actual = [
            {
                "condition_id": "fault_01",
                "seed": 310,
                "success": False,
                "steps": 500,
                "final_object_goal_distance": 0.2,
            }
        ]
        expected = [
            {
                "condition_id": "fault_01",
                "seed": "310",
                "success": "False",
                "steps": "500",
                "final_object_goal_distance": "0.2",
            }
        ]
        compare_reference_baselines(actual, expected)

    def test_reference_comparison_rejects_execution_regression(self) -> None:
        actual = [
            {
                "condition_id": "fault_01",
                "seed": 310,
                "success": True,
                "steps": 10,
                "final_object_goal_distance": 0.05,
            }
        ]
        expected = [
            {
                "condition_id": "fault_01",
                "seed": 310,
                "success": False,
                "steps": 500,
                "final_object_goal_distance": 0.2,
            }
        ]
        with self.assertRaisesRegex(ValueError, "success regression"):
            compare_reference_baselines(actual, expected)


if __name__ == "__main__":
    unittest.main()
