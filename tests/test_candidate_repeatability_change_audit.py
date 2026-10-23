from __future__ import annotations

import unittest

from scripts.analyze_candidate_repeatability_changes import classify_changed_case


def _packet(candidate: str, comp_score: float, retry_score: float) -> dict[str, object]:
    return {
        "case_id": "case",
        "seed": 1,
        "selected_candidate": candidate,
        "candidate_repeatability_evidence": [
            {"candidate_id": "probe_grounded_compensation", "prefix_success_count": 0, "robust_distance_score": comp_score},
            {"candidate_id": "stochastic_retry", "prefix_success_count": 0, "robust_distance_score": retry_score},
        ],
    }


class CandidateRepeatabilityChangeAuditTest(unittest.TestCase):
    def test_classifies_harmful_robust_distance_flip(self) -> None:
        row = classify_changed_case(
            _packet("stochastic_retry", 0.2, 0.1),
            _packet("probe_grounded_compensation", 0.1, 0.2),
            {"selected_recovery_success": "True"},
            {"selected_recovery_success": "False"},
        )
        self.assertEqual(row["outcome_class"], "HARMFUL")
        self.assertEqual(row["evidence_driver"], "ROBUST_DISTANCE_RANK_FLIP")


if __name__ == "__main__":
    unittest.main()
