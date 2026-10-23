from __future__ import annotations

import math
import unittest

from src.probemem.retry_value_audit import average_precision, binary_roc_auc, threshold_frontier


class RetryValueAuditTests(unittest.TestCase):
    def test_roc_auc_is_pairwise_and_tie_aware(self) -> None:
        self.assertEqual(binary_roc_auc([True, False], [1.0, 0.0]), 1.0)
        self.assertEqual(binary_roc_auc([True, False], [0.0, 1.0]), 0.0)
        self.assertEqual(binary_roc_auc([True, False], [1.0, 1.0]), 0.5)

    def test_single_class_metrics_are_not_fabricated(self) -> None:
        self.assertIsNone(binary_roc_auc([True, True], [0.0, 1.0]))
        self.assertIsNone(average_precision([False, False], [0.0, 1.0]))

    def test_average_precision_groups_ties(self) -> None:
        self.assertAlmostEqual(average_precision([True, False, True], [1.0, 1.0, 0.0]), 7.0 / 12.0)

    def test_frontier_includes_never_and_always_without_selecting_one(self) -> None:
        rows = threshold_frontier(labels=[True, False], scores=[1.0, 0.0], costs=[100, 200], score_name="x")
        self.assertTrue(math.isinf(rows[0]["threshold"]))
        self.assertEqual(rows[0]["retry_requests"], 0)
        self.assertEqual(rows[-1]["retry_requests"], 2)
        self.assertEqual(rows[-1]["additional_environment_steps"], 300)
        self.assertEqual(rows[-1]["recovered_cases"], 1)


if __name__ == "__main__":
    unittest.main()
