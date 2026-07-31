from __future__ import annotations

import unittest

from scripts.analyze_candidate_micro_evidence import summarize_horizon


class CandidateMicroEvidenceAnalysisTest(unittest.TestCase):
    def test_summary_uses_paired_outcomes_and_cost(self) -> None:
        rows = [
            {
                "case_id": "a",
                "horizon": "16",
                "selected_recovery_success": "True",
                "utility_agreement": "True",
                "prefix_environment_steps": "32",
                "selected_verification_steps": "10",
            },
            {
                "case_id": "b",
                "horizon": "16",
                "selected_recovery_success": "False",
                "utility_agreement": "False",
                "prefix_environment_steps": "24",
                "selected_verification_steps": "20",
            },
        ]
        outcomes = {
            ("a", "probe_grounded_compensation"): False,
            ("a", "stochastic_retry"): True,
            ("b", "probe_grounded_compensation"): False,
            ("b", "stochastic_retry"): True,
        }
        summary = summarize_horizon(rows, outcomes)
        self.assertEqual(summary["versus_fixed_compensation"], {"win": 1, "tie": 1, "loss": 0})
        self.assertEqual(summary["versus_fixed_retry"], {"win": 0, "tie": 1, "loss": 1})
        self.assertEqual(summary["mean_prefix_environment_steps"], 28)
        self.assertEqual(summary["mean_total_additional_steps"], 43)


if __name__ == "__main__":
    unittest.main()
