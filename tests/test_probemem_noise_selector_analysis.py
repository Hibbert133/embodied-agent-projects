"""Tests for frozen ProbeMem selector comparison."""

from __future__ import annotations

import unittest

from scripts.analyze_probemem_noise_selector_validation import (
    COMPENSATION,
    RETRY,
    evaluate_frozen_selector,
)


def _candidate(status: str) -> dict[str, str]:
    return {
        "verification_status": status,
        "initial_steps": "500",
        "verification_steps": "100",
    }


class ProbeMemNoiseSelectorAnalysisTest(unittest.TestCase):
    def test_frozen_rule_reports_paired_win_tie_loss(self) -> None:
        features = [
            {
                "experiment_run_id": "run",
                "manifest_id": "manifest",
                "episode_id": 1,
                "seed": 1,
                "probe_relative_bias_std": 1.0,
                "outcome_partition_evaluator_only": "RETRY_ONLY_RECOVERY",
            },
            {
                "experiment_run_id": "run",
                "manifest_id": "manifest",
                "episode_id": 2,
                "seed": 2,
                "probe_relative_bias_std": 3.0,
                "outcome_partition_evaluator_only": "COMPENSATION_ONLY_RECOVERY",
            },
        ]
        pairs = {
            1: {COMPENSATION: _candidate("REJECTED"), RETRY: _candidate("ACCEPTED")},
            2: {COMPENSATION: _candidate("ACCEPTED"), RETRY: _candidate("REJECTED")},
        }
        rows, summary = evaluate_frozen_selector(features, pairs, 2.0)
        self.assertEqual(summary["accepted_recoveries"]["frozen_selector"], 2)
        self.assertEqual(summary["selector_vs_always_retry"], {"win": 1, "tie": 1, "loss": 0})
        self.assertEqual({row["selected_skill"] for row in rows}, {COMPENSATION, RETRY})


if __name__ == "__main__":
    unittest.main()
