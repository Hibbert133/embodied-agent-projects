"""Tests for accepted-only post-probe ProbeMem episodic records."""

from __future__ import annotations

import unittest

from src.probemem.intervention_memory import VerifiedInterventionEpisode
from src.probemem.intervention_utility import InterventionApplicabilitySignature
from src.probemem.models import InterventionSkill


def episode(status: str = "ACCEPTED") -> VerifiedInterventionEpisode:
    return VerifiedInterventionEpisode(
        schema_version=1,
        record_id="record_1",
        source_episode_id=1,
        source_run_id="run",
        source_manifest_id="manifest",
        source_git_commit="commit",
        selection_policy_id="frozen_selector",
        applicability_signature=InterventionApplicabilitySignature(
            schema_version=1,
            evidence_id="evidence_1",
            episode_id=1,
            values=(0.1,) * 13,
        ),
        selected_skill=InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
        fresh_verification_status=status,
        final_object_goal_distance=0.04,
        verification_steps=100,
        total_interaction_steps=664,
    )


class ProbeMemInterventionMemoryTest(unittest.TestCase):
    def test_only_accepted_episode_is_valid(self) -> None:
        self.assertEqual(episode().fresh_verification_status, "ACCEPTED")
        with self.assertRaisesRegex(ValueError, "only fresh ACCEPTED"):
            episode("REJECTED")

    def test_operational_retrieval_fails_closed_until_frozen(self) -> None:
        base = episode()
        with self.assertRaisesRegex(ValueError, "development-only"):
            VerifiedInterventionEpisode(
                **{
                    **base.__dict__,
                    "operational_retrieval_enabled": True,
                }
            )

    def test_record_contains_no_counterfactual_or_oracle_fields(self) -> None:
        payload = episode().to_dict()
        self.assertNotIn("perturbation_type", payload)
        self.assertNotIn("counterfactual", payload)
        self.assertTrue(payload["verified_episode_eligible"])


if __name__ == "__main__":
    unittest.main()
