"""Tests for the evaluator-only ProbeMem contradiction audit."""

from __future__ import annotations

import unittest

from scripts.audit_probemem_memory_contradictions import (
    implicit_prediction_resonance,
    standardized_feature_contributions,
)
from src.probemem.intervention_utility import InterventionApplicabilitySignature


def _signature(episode_id: int, values: tuple[float, ...]) -> InterventionApplicabilitySignature:
    return InterventionApplicabilitySignature(
        schema_version=1,
        evidence_id=f"evidence_{episode_id}",
        episode_id=episode_id,
        values=values,
    )


class ProbeMemMemoryContradictionAuditTest(unittest.TestCase):
    def test_resonance_is_derived_from_fresh_status(self) -> None:
        self.assertEqual(implicit_prediction_resonance("ACCEPTED"), "SUPPORTED")
        self.assertEqual(implicit_prediction_resonance("INCONCLUSIVE"), "UNRESOLVED")
        self.assertEqual(implicit_prediction_resonance("REJECTED"), "CONTRADICTED")
        with self.assertRaises(ValueError):
            implicit_prediction_resonance("UNKNOWN")

    def test_feature_contributions_are_normalized_and_ranked(self) -> None:
        left = _signature(1, (2.0, 1.0) + (0.0,) * 11)
        right = _signature(2, (0.0,) * 13)
        contributions = standardized_feature_contributions(
            left, right, (1.0,) * 13
        )
        self.assertEqual(contributions[0][0], "progress_to_goal")
        self.assertAlmostEqual(contributions[0][1], 0.8)
        self.assertEqual(contributions[1][0], "final_object_goal_distance")
        self.assertAlmostEqual(sum(value for _, value in contributions), 1.0)


if __name__ == "__main__":
    unittest.main()
