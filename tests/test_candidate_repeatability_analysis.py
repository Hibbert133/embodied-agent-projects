from __future__ import annotations

import unittest

from scripts.analyze_candidate_repeatability import _transition


class CandidateRepeatabilityAnalysisTest(unittest.TestCase):
    def test_transition_counts_helpful_and_harmful_decision_changes(self) -> None:
        rows = [
            {"case_id": "a", "repetition_count": "1", "selected_candidate": "x", "selected_recovery_success": "False"},
            {"case_id": "a", "repetition_count": "2", "selected_candidate": "y", "selected_recovery_success": "True"},
            {"case_id": "b", "repetition_count": "1", "selected_candidate": "x", "selected_recovery_success": "True"},
            {"case_id": "b", "repetition_count": "2", "selected_candidate": "y", "selected_recovery_success": "False"},
        ]
        self.assertEqual(
            _transition(rows, 1, 2),
            {"decision_changed": 2, "recovery_improved": 1, "recovery_worsened": 1},
        )


if __name__ == "__main__":
    unittest.main()
