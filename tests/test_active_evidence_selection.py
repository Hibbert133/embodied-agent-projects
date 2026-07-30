from __future__ import annotations

import unittest

from scripts.validate_active_evidence_selection import select_rank_stratified


class ActiveEvidenceSelectionTest(unittest.TestCase):
    def test_selects_even_failure_ranks_without_success_rows(self) -> None:
        rows = [
            {"seed": str(seed), "success": "False", "final_object_goal_distance": str(seed / 10)}
            for seed in range(1, 10)
        ]
        rows.append({"seed": "99", "success": "True", "final_object_goal_distance": "0"})
        self.assertEqual(select_rank_stratified(rows, 5), [1, 3, 5, 7, 9])

    def test_ties_are_seed_deterministic(self) -> None:
        rows = [
            {"seed": str(seed), "success": "False", "final_object_goal_distance": "0.2"}
            for seed in (4, 2, 3, 1)
        ]
        self.assertEqual(select_rank_stratified(rows, 2), [1, 4])

    def test_excludes_development_seeds_before_stratification(self) -> None:
        rows = [
            {"seed": str(seed), "success": "False", "final_object_goal_distance": str(seed)}
            for seed in range(1, 7)
        ]
        self.assertEqual(
            select_rank_stratified(rows, 2, exclude_seeds=(1, 6)), [2, 5]
        )


if __name__ == "__main__":
    unittest.main()
