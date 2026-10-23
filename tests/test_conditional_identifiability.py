from __future__ import annotations

import unittest

from src.probemem.conditional_identifiability import conditional_pairwise_auc, within_group_permutation_test


class ConditionalIdentifiabilityTests(unittest.TestCase):
    def test_auc_uses_only_within_group_pairs(self) -> None:
        auc, groups, pairs = conditional_pairwise_auc(
            [1, 1, 2, 2], [True, False, True, False], [2.0, 1.0, 0.0, 1.0],
        )
        self.assertEqual(auc, 0.5)
        self.assertEqual(groups, 2)
        self.assertEqual(pairs, 2)

    def test_uninformative_groups_do_not_create_synthetic_auc(self) -> None:
        auc, groups, pairs = conditional_pairwise_auc([1, 1, 2], [True, True, False], [1.0, 2.0, 0.0])
        self.assertIsNone(auc)
        self.assertEqual((groups, pairs), (0, 0))

    def test_permutation_is_reproducible_and_group_preserving(self) -> None:
        args = ([1, 1, 2, 2], [True, False, True, False], [2.0, 1.0, 2.0, 1.0])
        first = within_group_permutation_test(*args, seed=7, resamples=100)
        second = within_group_permutation_test(*args, seed=7, resamples=100)
        self.assertEqual(first, second)
        self.assertEqual(first["observed_auc"], 1.0)


if __name__ == "__main__":
    unittest.main()
