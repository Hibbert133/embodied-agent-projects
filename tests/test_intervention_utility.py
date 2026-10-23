from __future__ import annotations

import unittest

from src.evaluation.intervention_utility import (
    CandidateUtilityOutcome,
    UtilityComparison,
    best_candidate_ids,
    compare_candidate_utility,
)


def outcome(candidate: str, status: str, steps: int, distance: float):
    return CandidateUtilityOutcome(candidate, status, steps, distance)


class InterventionUtilityTest(unittest.TestCase):
    def test_verification_status_has_primary_priority(self) -> None:
        accepted = outcome("compensation", "ACCEPTED", 500, 0.2)
        rejected = outcome("retry", "REJECTED", 10, 0.01)
        self.assertIs(
            compare_candidate_utility(accepted, rejected), UtilityComparison.LEFT
        )

    def test_accepted_candidate_uses_steps_before_distance(self) -> None:
        fast = outcome("compensation", "ACCEPTED", 100, 0.06)
        close = outcome("retry", "ACCEPTED", 120, 0.04)
        self.assertEqual(best_candidate_ids([fast, close]), ("compensation",))

    def test_failed_candidate_uses_distance_before_steps(self) -> None:
        far = outcome("compensation", "REJECTED", 100, 0.2)
        close = outcome("retry", "REJECTED", 500, 0.1)
        self.assertEqual(best_candidate_ids([far, close]), ("retry",))

    def test_exact_match_is_preserved_as_tie(self) -> None:
        left = outcome("compensation", "INCONCLUSIVE", 500, 0.1)
        right = outcome("retry", "INCONCLUSIVE", 500, 0.1)
        self.assertEqual(best_candidate_ids([left, right]), ("compensation", "retry"))

    def test_invalid_candidate_count_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly two"):
            best_candidate_ids([outcome("only", "ACCEPTED", 1, 0.0)])


if __name__ == "__main__":
    unittest.main()
