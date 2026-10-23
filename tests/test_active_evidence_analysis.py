from __future__ import annotations

import unittest

from scripts.analyze_active_evidence_campaign import (
    evaluate_frozen_threshold,
    select_development_threshold,
)


def outcome(success: bool, steps: int, uncertainty: float) -> dict[str, object]:
    return {
        "success": success,
        "environment_steps": steps,
        "metrics": {"uncertainty": uncertainty},
    }


class ActiveEvidenceAnalysisTest(unittest.TestCase):
    def test_threshold_uses_probe_only_where_it_improves_success(self) -> None:
        passive = {
            "easy": outcome(True, 100, 0.2),
            "medium": outcome(True, 110, 0.5),
            "hard": outcome(False, 200, 0.9),
        }
        probed = {
            "easy": outcome(True, 130, 0.2),
            "medium": outcome(True, 140, 0.5),
            "hard": outcome(True, 150, 0.9),
        }
        selected = select_development_threshold(passive, probed)
        self.assertEqual(selected["development_successes"], 3)
        self.assertEqual(selected["development_probe_requests"], 1)
        self.assertAlmostEqual(selected["threshold"], 0.7)

    def test_requires_paired_cases(self) -> None:
        with self.assertRaisesRegex(ValueError, "paired"):
            select_development_threshold(
                {"one": outcome(False, 10, 0.5)},
                {"two": outcome(True, 10, 0.5)},
            )

    def test_frozen_threshold_does_not_retune(self) -> None:
        passive = {
            "easy": outcome(True, 100, 0.2),
            "hard": outcome(False, 200, 0.9),
        }
        gated = {
            "easy": {**outcome(True, 100, 0.2), "metrics": {"uncertainty": 0.2, "probe_requested": False}},
            "hard": {**outcome(True, 150, 0.9), "metrics": {"uncertainty": 0.9, "probe_requested": True}},
        }
        result = evaluate_frozen_threshold(passive, gated, threshold=0.7)
        self.assertFalse(result["heldout_retuning"])
        self.assertEqual(result["decision_rule_matches"], 2)
        self.assertEqual(result["success_gain_over_passive"], 1)


if __name__ == "__main__":
    unittest.main()
