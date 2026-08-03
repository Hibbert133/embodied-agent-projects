"""Tests for ProbeMem-Online post-hoc analysis."""

from __future__ import annotations

import unittest

from scripts.analyze_online_memory import _changes, _latency, _relative_reduction


def row(episode: int, skill: str, status: str) -> dict[str, str]:
    return {"episode_id": str(episode), "selected_skill": skill, "verification_status": status}


class ProbeMemOnlineAnalysisTest(unittest.TestCase):
    def test_action_changes_are_causal_outcome_changes(self) -> None:
        stateless = [row(1, "A", "REJECTED"), row(2, "A", "ACCEPTED"), row(3, "A", "ACCEPTED")]
        full = [row(1, "B", "ACCEPTED"), row(2, "B", "REJECTED"), row(3, "A", "ACCEPTED")]
        self.assertEqual(_changes(stateless, full), {"changed": 2, "helpful": 1, "harmful": 1, "tie": 0})

    def test_latency_uses_nearest_rank_p90(self) -> None:
        result = _latency([1.0, 2.0, 3.0, 4.0, 100.0])
        self.assertEqual(result["median"], 3.0)
        self.assertEqual(result["p90"], 100.0)

    def test_zero_baseline_harm_is_not_fabricated_reduction(self) -> None:
        self.assertIsNone(_relative_reduction(0, 0))
        self.assertAlmostEqual(_relative_reduction(10, 7), 0.3)


if __name__ == "__main__":
    unittest.main()
