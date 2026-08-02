"""Tests for frozen ProbeMem-ACR evaluator definitions."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts.analyze_probemem_acr import _paired_bootstrap, oracle_winners
from scripts.run_probemem_acr_development import _serialize_coverage_decision
from src.probemem import InterventionSkill, MemoryApplicabilityAction
from src.reasoning import validate_no_oracle_evidence


def candidate(status: str, progress: float, steps: int) -> dict[str, object]:
    return {
        "verification_status": status,
        "observed_progress": progress,
        "verification_steps": steps,
    }


class ProbeMemAcrEvaluationTest(unittest.TestCase):
    def test_oracle_uses_status_then_progress_then_cost(self) -> None:
        self.assertEqual(
            oracle_winners({
                "a": candidate("ACCEPTED", 0.1, 500),
                "b": candidate("INCONCLUSIVE", 0.9, 1),
            }),
            ("a",),
        )
        self.assertEqual(
            oracle_winners({
                "a": candidate("REJECTED", 0.1, 10),
                "b": candidate("REJECTED", 0.2, 500),
            }),
            ("b",),
        )
        self.assertEqual(
            oracle_winners({
                "a": candidate("INCONCLUSIVE", 0.2, 20),
                "b": candidate("INCONCLUSIVE", 0.2, 10),
            }),
            ("b",),
        )

    def test_complete_oracle_tie_is_preserved(self) -> None:
        result = oracle_winners({
            "a": candidate("ACCEPTED", 0.2, 10),
            "b": candidate("ACCEPTED", 0.2, 10),
        })
        self.assertEqual(result, ("a", "b"))

    def test_paired_bootstrap_is_reproducible(self) -> None:
        left = _paired_bootstrap([1.0, 0.0, -1.0], seed=9301, resamples=100)
        right = _paired_bootstrap([1.0, 0.0, -1.0], seed=9301, resamples=100)
        self.assertEqual(left, right)

    def test_coverage_audit_does_not_use_agent_forbidden_action_key(self) -> None:
        serialized = _serialize_coverage_decision(SimpleNamespace(
            action=MemoryApplicabilityAction.USE_VERIFIED_EPISODE,
            reason="within frozen coverage",
            selected_skill=InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
            retrieved_record_ids=("record_1",),
            nearest_distance=0.1,
            coverage_radius=0.2,
        ))
        validate_no_oracle_evidence(serialized)
        self.assertNotIn("action", serialized)


if __name__ == "__main__":
    unittest.main()
