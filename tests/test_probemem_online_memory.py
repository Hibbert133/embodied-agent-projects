"""Integrity tests for ProbeMem-Online action-conditioned memory."""

from __future__ import annotations

import json
import unittest
from collections import Counter

from scripts.generate_online_memory_bootstrap_manifest import build_units

from src.probemem.memory_resonance import ActionResonanceRecord
from src.probemem.memory_tools import retrieve_action_memory_payload, validate_memory_ids
from src.probemem.models import InterventionSkill
from src.probemem.regime_memory import (
    ProbeRegimeSignature,
    RegimeActionExperience,
    RegimeActionMemory,
)


COMPENSATION = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def signature(episode_id: int, offset: float = 0.0) -> ProbeRegimeSignature:
    return ProbeRegimeSignature(1, f"evidence_{episode_id}", episode_id, (
        0.1 + offset, 0.0, 0.1 + offset, 0.02, 0.9, 0.1, 0.3, 0.12,
    ))


def record(episode_id: int, skill: InterventionSkill, status: str, *, offset: float = 0.0) -> RegimeActionExperience:
    return RegimeActionExperience(
        schema_version=1, record_id=f"record_{episode_id}", episode_id=episode_id,
        available_from_episode_id=episode_id + 1, probe_signature=signature(episode_id, offset),
        selected_skill=skill, predicted_status=None, predicted_accept_probability=None,
        observed_status=status, observed_progress=0.2 if status == "ACCEPTED" else -0.1,
        observed_final_distance=0.05 if status == "ACCEPTED" else 0.15,
        interaction_cost=500, source_run_id="bootstrap", source_manifest_id="manifest",
        record_origin="OUTCOME_BLIND_BOOTSTRAP_SELECTED_ACTION",
    )


class ProbeMemOnlineMemoryTest(unittest.TestCase):
    def test_bootstrap_assignment_is_outcome_blind_and_counterbalanced(self) -> None:
        config = {
            "seed_range": [4100, 4199],
            "random_namespaces": {"initial_perturbation": 19201, "registered_probe": 19202, "selected_verification": 19203},
        }
        units = build_units(config)
        cells = Counter((row["condition_id_oracle"], row["selected_skill"]) for row in units)
        self.assertEqual(len(units), 100)
        self.assertEqual(set(cells.values()), {25})
        self.assertTrue(all(len({row["initial_perturbation_seed"], row["diagnostic_probe_seed"], row["selected_verification_seed"]}) == 3 for row in units))
        self.assertTrue(all("outcome" not in key for row in units for key in row))

    def test_action_histories_are_separate_and_keep_all_outcomes(self) -> None:
        memory = RegimeActionMemory((
            record(1, COMPENSATION, "ACCEPTED"),
            record(2, RETRY, "REJECTED", offset=0.1),
            record(3, COMPENSATION, "INCONCLUSIVE", offset=0.2),
        ))
        compensation, _ = memory.retrieve_action_history(signature(4), COMPENSATION, created_before_episode_id=4)
        retry, _ = memory.retrieve_action_history(signature(4), RETRY, created_before_episode_id=4)
        self.assertEqual(compensation.history_count, 2)
        self.assertEqual((compensation.support_count, compensation.unresolved_count, compensation.contradiction_count), (1, 1, 0))
        self.assertEqual((retry.support_count, retry.unresolved_count, retry.contradiction_count), (0, 0, 1))
        self.assertEqual({item.selected_skill for item in memory.verified_examples}, {COMPENSATION})

    def test_current_and_future_records_are_invisible(self) -> None:
        memory = RegimeActionMemory((record(1, COMPENSATION, "ACCEPTED"), record(3, RETRY, "REJECTED")))
        self.assertEqual([item.episode_id for item in memory.prior(3)], [1])
        with self.assertRaisesRegex(ValueError, "provenance"):
            memory.retrieve_action_history(signature(4), RETRY, created_before_episode_id=3)

    def test_one_selected_action_per_episode_and_append_order(self) -> None:
        memory = RegimeActionMemory()
        memory.append_after_verification(record(1, COMPENSATION, "REJECTED"))
        with self.assertRaisesRegex(ValueError, "one selected action"):
            alternative = RegimeActionExperience(**{
                **record(1, RETRY, "ACCEPTED").__dict__, "record_id": "counterfactual_1",
            })
            memory.append_after_verification(alternative)
        later = RegimeActionMemory((record(2, RETRY, "ACCEPTED"),))
        with self.assertRaisesRegex(ValueError, "strict episode order"):
            later.append_after_verification(record(1, COMPENSATION, "ACCEPTED"))

    def test_oracle_and_counterfactual_fields_fail_closed(self) -> None:
        payload = record(1, COMPENSATION, "ACCEPTED").to_dict()
        payload["condition_id"] = "fault_01"
        with self.assertRaises((TypeError, ValueError)):
            RegimeActionExperience.from_dict(payload)
        serialized = json.dumps(record(1, COMPENSATION, "REJECTED").to_dict()).lower()
        for forbidden in ("fault", "condition", "oracle", "alternative_outcome"):
            self.assertNotIn(forbidden, serialized)

    def test_memory_payload_ids_are_chronological(self) -> None:
        memory = RegimeActionMemory((record(1, COMPENSATION, "ACCEPTED"), record(2, RETRY, "REJECTED")))
        payload = retrieve_action_memory_payload(memory, signature(3), created_before_episode_id=3)
        validate_memory_ids(payload, memory, created_before_episode_id=3)
        payload["candidate_actions"][COMPENSATION.value]["global"]["retrieved_record_ids"] += ("future",)
        with self.assertRaisesRegex(ValueError, "future"):
            validate_memory_ids(payload, memory, created_before_episode_id=3)

    def test_resonance_keeps_contradiction_and_brier_score(self) -> None:
        result = ActionResonanceRecord.create(
            episode_id=4, selected_skill=RETRY, predicted_status="ACCEPTED",
            probabilities={"ACCEPTED": 0.7, "INCONCLUSIVE": 0.2, "REJECTED": 0.1},
            observed_status="REJECTED", observed_progress=-0.1,
            supporting_memory_ids=("r1",), contradicting_memory_ids=("r2",),
        )
        self.assertEqual(result.resonance_class, "CONTRADICTED")
        self.assertAlmostEqual(result.observed_class_probability, 0.1)
        self.assertAlmostEqual(result.brier_score, 0.7**2 + 0.2**2 + 0.9**2)


if __name__ == "__main__":
    unittest.main()
