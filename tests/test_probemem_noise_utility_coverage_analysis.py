"""Tests for ProbeMem label-blind noise utility coverage analysis."""

from __future__ import annotations

import unittest

from scripts.analyze_probemem_noise_utility_coverage import (
    COMPENSATION,
    RETRY,
    build_outcome_partitions,
    exploratory_feature_auc,
)


def _candidate(episode: int, candidate: str, status: str) -> dict[str, str]:
    return {
        "episode_id": str(episode),
        "candidate_id": candidate,
        "verification_status": status,
    }


class ProbeMemNoiseUtilityCoverageAnalysisTest(unittest.TestCase):
    def test_outcome_partitions_distinguish_exclusive_recoveries(self) -> None:
        rows = [
            _candidate(1, COMPENSATION, "ACCEPTED"),
            _candidate(1, RETRY, "REJECTED"),
            _candidate(2, COMPENSATION, "REJECTED"),
            _candidate(2, RETRY, "ACCEPTED"),
            _candidate(3, COMPENSATION, "ACCEPTED"),
            _candidate(3, RETRY, "ACCEPTED"),
            _candidate(4, COMPENSATION, "REJECTED"),
            _candidate(4, RETRY, "INCONCLUSIVE"),
        ]
        partitions, _ = build_outcome_partitions(rows)
        self.assertEqual(partitions[1], "COMPENSATION_ONLY_RECOVERY")
        self.assertEqual(partitions[2], "RETRY_ONLY_RECOVERY")
        self.assertEqual(partitions[3], "BOTH_RECOVER")
        self.assertEqual(partitions[4], "NEITHER_RECOVERS")

    def test_auc_is_exploratory_and_never_fits_threshold(self) -> None:
        rows = [
            {
                "experiment_run_id": "run",
                "manifest_id": "manifest",
                "episode_id": 1,
                "seed": 1,
                "feature_a": 0.1,
                "outcome_partition_evaluator_only": "COMPENSATION_ONLY_RECOVERY",
                "compensation_status_evaluator_only": "ACCEPTED",
                "retry_status_evaluator_only": "REJECTED",
            },
            {
                "experiment_run_id": "run",
                "manifest_id": "manifest",
                "episode_id": 2,
                "seed": 2,
                "feature_a": 0.9,
                "outcome_partition_evaluator_only": "RETRY_ONLY_RECOVERY",
                "compensation_status_evaluator_only": "REJECTED",
                "retry_status_evaluator_only": "ACCEPTED",
            },
        ]
        result = exploratory_feature_auc(rows)
        self.assertEqual(result[0]["exploratory_roc_auc"], 1.0)
        self.assertFalse(result[0]["threshold_fitted"])
        self.assertFalse(result[0]["heldout_claim_eligible"])


if __name__ == "__main__":
    unittest.main()
