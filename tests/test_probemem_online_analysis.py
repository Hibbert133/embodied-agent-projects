"""Tests for ProbeMem-Online post-hoc analysis."""

from __future__ import annotations

import unittest

from scripts.analyze_online_memory import _changes, _latency, _relative_reduction
from scripts.write_online_memory_report import build_report


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

    def test_incomplete_report_forbids_memory_benefit_claim(self) -> None:
        summary = {
            "run_status": "RUNNING", "operational_cases": 2, "target_operational_cases": 60,
            "methods": {}, "full_vs_stateless_changes": {"changed": 1, "helpful": 1, "harmful": 0, "tie": 0},
            "api": {"calls": 8, "valid": 8, "repairs": 0, "latency_ms": {"median": 1, "p90": 2, "max": 3}},
            "integrity": {}, "promotion_gate": {"evaluated": False, "passed": False},
        }
        report = build_report(summary)
        self.assertIn("support no memory-benefit", report)
        self.assertIn("2/60", report)


if __name__ == "__main__":
    unittest.main()
