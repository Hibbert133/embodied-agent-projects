"""Tests for post-hoc ProbeMem frozen-selector causal audit."""

from __future__ import annotations

import unittest

from scripts.audit_probemem_noise_selector_failures import (
    classify_decision_effect,
    summarize_audit,
)


class ProbeMemNoiseSelectorCausalAuditTest(unittest.TestCase):
    def test_effect_requires_an_actual_decision_change(self) -> None:
        self.assertEqual(
            classify_decision_effect("RETRY", "RETRY", True, True),
            "NO_DECISION_CHANGE",
        )
        self.assertEqual(
            classify_decision_effect("COMP", "RETRY", True, False),
            "HELPFUL_CHANGE",
        )
        self.assertEqual(
            classify_decision_effect("COMP", "RETRY", False, True),
            "HARMFUL_CHANGE",
        )

    def test_summary_never_claims_refitting_or_promotion(self) -> None:
        rows = [
            {
                "seed": 1,
                "selected_accepted": False,
                "outcome_partition_evaluator_only": "RETRY_ONLY_RECOVERY",
                "effect_vs_always_retry": "HARMFUL_CHANGE",
                "effect_vs_always_compensation": "NO_DECISION_CHANGE",
                "absolute_threshold_margin": 3.0,
            }
        ]
        summary = summarize_audit(rows)
        self.assertEqual(summary["error_seeds"], [1])
        self.assertFalse(summary["selector_or_threshold_refit"])
        self.assertFalse(summary["phase_d_promoted"])
        self.assertEqual(summary["new_environment_rollouts"], 0)


if __name__ == "__main__":
    unittest.main()
