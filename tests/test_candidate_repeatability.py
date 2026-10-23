from __future__ import annotations

import unittest

from src.candidate_repeatability import (
    aggregate_candidate_repetitions,
    select_repeatability_candidate,
)


def _repeat(candidate: str, distance: float, *, success: bool = False) -> dict[str, object]:
    return {
        "candidate_id": candidate,
        "final_object_goal_distance": distance,
        "success_within_probe_budget": success,
        "observed_steps": 64,
    }


class CandidateRepeatabilityTest(unittest.TestCase):
    def test_aggregate_uses_mean_plus_population_std(self) -> None:
        result = aggregate_candidate_repetitions(
            [_repeat("a", 0.1), _repeat("a", 0.3)], candidate_id="a"
        )
        self.assertAlmostEqual(result["mean_final_object_goal_distance"], 0.2)
        self.assertAlmostEqual(result["final_object_goal_distance_std"], 0.1)
        self.assertAlmostEqual(result["robust_distance_score"], 0.3)
        self.assertEqual(result["total_environment_steps"], 128)

    def test_selector_prefers_success_then_robust_distance(self) -> None:
        stable = aggregate_candidate_repetitions(
            [_repeat("stable", 0.2), _repeat("stable", 0.2)], candidate_id="stable"
        )
        variable = aggregate_candidate_repetitions(
            [_repeat("variable", 0.05), _repeat("variable", 0.35)], candidate_id="variable"
        )
        self.assertEqual(select_repeatability_candidate([variable, stable]), "stable")
        successful = dict(variable)
        successful["prefix_success_count"] = 1
        self.assertEqual(select_repeatability_candidate([stable, successful]), "variable")

    def test_oracle_field_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Oracle-only"):
            aggregate_candidate_repetitions(
                [{**_repeat("a", 0.1), "condition_id": "fault_05"}], candidate_id="a"
            )


if __name__ == "__main__":
    unittest.main()
