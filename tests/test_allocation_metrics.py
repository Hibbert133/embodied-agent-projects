from __future__ import annotations

import unittest

from src.evaluation.allocation_metrics import (
    average_precision,
    balanced_accuracy,
    paired_win_tie_loss,
    roc_auc,
    stratified_paired_bootstrap_difference,
    wilson_interval,
)


class AllocationMetricsTest(unittest.TestCase):
    def test_auc_and_average_precision_detect_ordering(self) -> None:
        labels = [False, True, False, True]
        self.assertEqual(roc_auc(labels, [0.1, 0.8, 0.2, 0.9]), 1.0)
        self.assertEqual(average_precision(labels, [0.1, 0.8, 0.2, 0.9]), 1.0)

    def test_auc_is_none_for_single_class(self) -> None:
        self.assertIsNone(roc_auc([False, False], [0.1, 0.2]))
        self.assertIsNone(average_precision([True, True], [0.1, 0.2]))

    def test_balanced_accuracy_and_wilson(self) -> None:
        self.assertEqual(
            balanced_accuracy(["bias", "bias", "noise", "noise"], ["bias", "noise", "noise", "noise"]),
            0.75,
        )
        lower, upper = wilson_interval(5, 10) or (0.0, 0.0)
        self.assertLess(lower, 0.5)
        self.assertGreater(upper, 0.5)

    def test_paired_statistics_are_reproducible(self) -> None:
        self.assertEqual(
            paired_win_tie_loss([True, True, False], [False, True, True]),
            {"win": 1, "tie": 1, "loss": 1},
        )
        arguments = ([1.0, 1.0, 0.0, 1.0], [0.0, 1.0, 0.0, 0.0], ["a", "a", "b", "b"])
        first = stratified_paired_bootstrap_difference(
            *arguments, repetitions=100, seed=7
        )
        second = stratified_paired_bootstrap_difference(
            *arguments, repetitions=100, seed=7
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
