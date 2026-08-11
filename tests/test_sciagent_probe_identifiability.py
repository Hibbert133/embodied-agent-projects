import unittest

from src.probemem_sciagent.probe_identifiability import (
    build_distributional_target, build_probe_contrast, candidate_winner_reversal_count,
    roc_auc, spearman_rank_correlation, stratified_auc_bootstrap,
)
from src.probemem_sciagent.schemas import CompensationProbeEvidence, RetryProbeEvidence


class ProbeIdentifiabilityTest(unittest.TestCase):
    def test_probe_contrast_has_frozen_physical_semantics(self):
        contrast = build_probe_contrast(
            CompensationProbeEvidence(0.8, 0.1, 0.5, True, 0.01),
            RetryProbeEvidence(3, 2 / 3, 0.01, 0.001, 1 / 3),
        )
        self.assertAlmostEqual(contrast.compensation_support, 0.4)
        self.assertAlmostEqual(contrast.retry_support, 4 / 9)
        self.assertAlmostEqual(contrast.probe_contrast, 0.4 - 4 / 9)

    def test_lost_contact_zeroes_compensation_support(self):
        contrast = build_probe_contrast(
            CompensationProbeEvidence(1.0, 0.1, 1.0, False, 0.1),
            RetryProbeEvidence(3, 0.0, 0.0, 0.0, 0.0),
        )
        self.assertEqual(contrast.compensation_support, 0.0)

    def test_distributional_target_requires_half_rate_margin(self):
        target = build_distributional_target(
            ["ACCEPTED"] * 3 + ["REJECTED"],
            ["ACCEPTED"] + ["REJECTED"] * 3,
            decisive_margin=0.5,
        )
        self.assertEqual(target.decisive_label, "COMPENSATION_SUPERIOR")
        self.assertEqual(target.utility_margin, 0.5)
        tied = build_distributional_target(
            ["ACCEPTED", "ACCEPTED", "REJECTED", "REJECTED"],
            ["ACCEPTED", "REJECTED", "REJECTED", "REJECTED"],
            decisive_margin=0.5,
        )
        self.assertEqual(tied.decisive_label, "NON_DECISIVE")

    def test_auc_is_tie_aware(self):
        self.assertEqual(roc_auc([1, 1, 0, 0], [0.9, 0.5, 0.5, 0.1]), 0.875)
        with self.assertRaises(ValueError):
            roc_auc([1, 1], [0.2, 0.3])

    def test_rank_correlation_handles_ties(self):
        self.assertAlmostEqual(spearman_rank_correlation([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertEqual(spearman_rank_correlation([1, 1, 1], [1, 2, 3]), 0.0)

    def test_bootstrap_is_deterministic_and_stratified(self):
        first = stratified_auc_bootstrap([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1], samples=100, seed=7)
        second = stratified_auc_bootstrap([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1], samples=100, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(first, (1.0, 1.0))

    def test_winner_reversal_detects_opposite_realizations(self):
        self.assertEqual(candidate_winner_reversal_count(
            ["ACCEPTED", "REJECTED"], ["REJECTED", "ACCEPTED"],
        ), 1)
        self.assertEqual(candidate_winner_reversal_count(
            ["ACCEPTED", "ACCEPTED"], ["REJECTED", "ACCEPTED"],
        ), 0)


if __name__ == "__main__":
    unittest.main()
