"""Tests for ProbeMem-ACR action-outcome memory and evidence."""

from __future__ import annotations

import unittest

from src.probemem.action_evidence import build_action_conditional_evidence_pack
from src.probemem.action_memory import (
    ActionOutcomeMemory,
    ActionOutcomeRecord,
    ActionRecordOrigin,
    standardized_rms_distance,
    unique_episode_scales,
)
from src.probemem.intervention_utility import InterventionApplicabilitySignature
from src.probemem.models import InterventionSkill


COMPENSATION = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def signature(episode: int, first: float = 0.0) -> InterventionApplicabilitySignature:
    return InterventionApplicabilitySignature(
        schema_version=1,
        evidence_id=f"evidence_{episode}",
        episode_id=episode,
        values=(first,) + (0.0,) * 12,
    )


def record(
    episode: int,
    skill: InterventionSkill,
    status: str,
    *,
    first: float = 0.0,
) -> ActionOutcomeRecord:
    return ActionOutcomeRecord(
        schema_version=1,
        record_id=f"record_{episode}_{skill.value}",
        source_episode_id=episode,
        available_from_episode_id=episode + 1,
        source_run_id="run",
        source_manifest_id="manifest",
        source_git_commit="commit",
        evidence_signature=signature(episode, first),
        intervention_skill=skill,
        predicted_status=None,
        predicted_progress=None,
        observed_status=status,
        observed_progress=first,
        final_object_goal_distance=0.1,
        verification_steps=100,
        interaction_cost=664,
        probe_used=True,
        record_origin=ActionRecordOrigin.DEVELOPMENT_COUNTERFACTUAL,
        operational_retrieval_eligible=False,
    )


class ProbeMemAcrMemoryTest(unittest.TestCase):
    def test_cold_start_status_allows_null_progress_prediction(self) -> None:
        payload = record(1, COMPENSATION, "ACCEPTED").to_dict()
        payload["predicted_status"] = "INCONCLUSIVE"
        payload["predicted_progress"] = None
        restored = ActionOutcomeRecord.from_dict(payload)
        self.assertEqual(restored.predicted_status, "INCONCLUSIVE")
        self.assertIsNone(restored.predicted_progress)

    def test_counterfactual_cannot_enter_operational_memory(self) -> None:
        payload = record(1, COMPENSATION, "ACCEPTED").to_dict()
        payload["operational_retrieval_eligible"] = True
        with self.assertRaises(ValueError):
            ActionOutcomeRecord.from_dict(payload)

    def test_same_episode_actions_are_allowed_but_duplicate_action_is_not(self) -> None:
        memory = ActionOutcomeMemory()
        memory.record(record(1, COMPENSATION, "ACCEPTED"))
        memory.record(record(1, RETRY, "REJECTED"))
        with self.assertRaises(ValueError):
            memory.record(record(1, RETRY, "INCONCLUSIVE"))

    def test_current_and_future_records_are_not_retrieved(self) -> None:
        memory = ActionOutcomeMemory()
        memory.record(record(1, COMPENSATION, "ACCEPTED"))
        memory.record(record(1, RETRY, "ACCEPTED"))
        scales = unique_episode_scales(memory.prior_records(2))
        retrieved = memory.retrieve_action_outcomes(
            signature(2), COMPENSATION, 2,
            outcome_status="ACCEPTED", limit=5, scales=scales,
        )
        self.assertEqual([item.record.source_episode_id for item in retrieved], [1])
        with self.assertRaises(ValueError):
            memory.retrieve_action_outcomes(
                signature(3), COMPENSATION, 2,
                outcome_status="ACCEPTED", limit=5, scales=scales,
            )

    def test_standardization_uses_unique_episode_signatures(self) -> None:
        records = [
            record(1, COMPENSATION, "ACCEPTED", first=1.0),
            record(1, RETRY, "REJECTED", first=1.0),
            record(2, COMPENSATION, "ACCEPTED", first=3.0),
            record(2, RETRY, "REJECTED", first=3.0),
        ]
        scales = unique_episode_scales(records)
        self.assertAlmostEqual(scales[0], 1.0)
        self.assertEqual(scales[1:], (1.0,) * 12)

    def test_distance_is_frozen_standardized_rms(self) -> None:
        distance = standardized_rms_distance(signature(1, 1.0), signature(2), (1.0,) * 13)
        self.assertAlmostEqual(distance, (1.0 / 13.0) ** 0.5)

    def test_evidence_pack_separates_actions_and_classes(self) -> None:
        memory = ActionOutcomeMemory()
        memory.record(record(1, COMPENSATION, "ACCEPTED"))
        memory.record(record(1, RETRY, "REJECTED"))
        pack = build_action_conditional_evidence_pack(memory, signature(2))
        self.assertEqual(
            [item.record.record_id for item in pack.candidate_actions[COMPENSATION].classes["ACCEPTED"].records],
            ["record_1_BOUNDED_PLANAR_COMPENSATION"],
        )
        self.assertEqual(
            [item.record.record_id for item in pack.candidate_actions[RETRY].classes["REJECTED"].records],
            ["record_1_INDEPENDENT_STOCHASTIC_RETRY"],
        )
        self.assertNotIn("observed_status", str(pack.to_dict()))


if __name__ == "__main__":
    unittest.main()
