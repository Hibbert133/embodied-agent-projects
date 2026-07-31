"""Tests for paired ProbeMem utility-result interpretation."""

from __future__ import annotations

import unittest

from scripts.analyze_probemem_paired_utility import (
    COMPENSATION,
    RETRY,
    summarize_candidate_pairs,
)


def _case(episode: int, winner: str, condition: str = "fault_01") -> dict[str, str]:
    return {
        "episode_id": str(episode),
        "decision_required": "True",
        "paired_comparable": "True",
        "winner_candidate_ids_oracle": winner,
        "condition_id_oracle": condition,
    }


def _candidate(
    episode: int, candidate: str, status: str, distance_change: float
) -> dict[str, str]:
    return {
        "episode_id": str(episode),
        "candidate_id": candidate,
        "verification_status": status,
        "goal_distance_change": str(distance_change),
    }


class ProbeMemPairedUtilityAnalysisTest(unittest.TestCase):
    def test_retry_winner_without_recovery_does_not_enable_selector(self) -> None:
        cases = [_case(1, RETRY)]
        candidates = [
            _candidate(1, COMPENSATION, "REJECTED", -0.1),
            _candidate(1, RETRY, "REJECTED", 0.0),
        ]
        summary = summarize_candidate_pairs(cases, candidates)
        self.assertEqual(summary["winner_counts_oracle"][RETRY], 1)
        self.assertEqual(summary["exclusive_recovery_cases"][RETRY], 0)
        self.assertFalse(summary["recovery_selector_improvement_available"])
        self.assertEqual(
            summary["experiment_interpretation_status"],
            "INSUFFICIENT_ACTION_UTILITY_DIVERSITY",
        )

    def test_retry_only_recovery_with_noise_can_support_next_selector_test(self) -> None:
        cases = [_case(1, RETRY, condition="fault_05")]
        candidates = [
            _candidate(1, COMPENSATION, "REJECTED", -0.1),
            _candidate(1, RETRY, "ACCEPTED", 0.2),
        ]
        summary = summarize_candidate_pairs(cases, candidates)
        self.assertEqual(summary["exclusive_recovery_cases"][RETRY], 1)
        self.assertEqual(
            summary["experiment_interpretation_status"],
            "READY_FOR_DEVELOPMENT_SELECTOR_TEST",
        )

    def test_missing_candidate_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "incomplete"):
            summarize_candidate_pairs(
                [_case(1, COMPENSATION)],
                [_candidate(1, COMPENSATION, "ACCEPTED", 0.2)],
            )


if __name__ == "__main__":
    unittest.main()
