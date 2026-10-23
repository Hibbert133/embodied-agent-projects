"""Tests for frozen deterministic ACR prediction and resonance."""

from __future__ import annotations

import unittest

from src.probemem.action_evidence import build_action_conditional_evidence_pack
from src.probemem.action_memory import ActionOutcomeMemory
from src.probemem.action_prediction import DeterministicActionConditionalEstimator
from src.probemem.models import InterventionSkill
from src.probemem.resonance import ResonanceClass, ResonanceRecord, classify_resonance
from tests.test_probemem_acr_memory import COMPENSATION, RETRY, record, signature


class ProbeMemAcrPredictionTest(unittest.TestCase):
    def test_cold_start_abstains_and_prior_tie_predicts_inconclusive(self) -> None:
        decision = DeterministicActionConditionalEstimator().predict(
            build_action_conditional_evidence_pack(ActionOutcomeMemory(), signature(1))
        )
        self.assertIsNone(decision.selected_skill)
        self.assertEqual(decision.decision_reason, "ABSTAIN_COLD_START")
        self.assertTrue(all(
            item.predicted_status == "INCONCLUSIVE"
            for item in decision.predictions.values()
        ))

    def test_weighted_dirichlet_selects_higher_action_utility(self) -> None:
        memory = ActionOutcomeMemory()
        statuses = ["ACCEPTED", "ACCEPTED", "ACCEPTED"]
        for episode, status in enumerate(statuses, 1):
            memory.record(record(episode, COMPENSATION, status, first=0.1 * episode))
            memory.record(record(episode, RETRY, "REJECTED", first=0.1 * episode))
        decision = DeterministicActionConditionalEstimator().predict(
            build_action_conditional_evidence_pack(memory, signature(4, first=0.4))
        )
        self.assertIs(decision.selected_skill, COMPENSATION)
        self.assertEqual(decision.decision_reason, "SELECT_HIGHER_UTILITY")
        prediction = decision.predictions[COMPENSATION]
        self.assertGreater(prediction.probabilities["ACCEPTED"], prediction.probabilities["REJECTED"])
        self.assertIsNotNone(prediction.predicted_progress)

    def test_estimator_constants_cannot_be_retuned(self) -> None:
        with self.assertRaises(ValueError):
            DeterministicActionConditionalEstimator(inconclusive_utility=0.4)
        with self.assertRaises(ValueError):
            DeterministicActionConditionalEstimator(minimum_history_per_action=2)

    def test_frozen_resonance_matrix(self) -> None:
        expected = {
            ("ACCEPTED", "ACCEPTED"): ResonanceClass.SUPPORTED,
            ("ACCEPTED", "INCONCLUSIVE"): ResonanceClass.UNRESOLVED,
            ("ACCEPTED", "REJECTED"): ResonanceClass.CONTRADICTED,
            ("INCONCLUSIVE", "ACCEPTED"): ResonanceClass.UNRESOLVED,
            ("INCONCLUSIVE", "INCONCLUSIVE"): ResonanceClass.SUPPORTED,
            ("INCONCLUSIVE", "REJECTED"): ResonanceClass.UNRESOLVED,
            ("REJECTED", "ACCEPTED"): ResonanceClass.CONTRADICTED,
            ("REJECTED", "INCONCLUSIVE"): ResonanceClass.UNRESOLVED,
            ("REJECTED", "REJECTED"): ResonanceClass.SUPPORTED,
        }
        for pair, value in expected.items():
            self.assertIs(classify_resonance(*pair), value)

    def test_resonance_records_observed_probability_and_progress_error(self) -> None:
        item = ResonanceRecord.create(
            prediction_id="prediction",
            episode_id=4,
            selected_skill=InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
            predicted_status="ACCEPTED",
            probabilities={"ACCEPTED": 0.6, "INCONCLUSIVE": 0.3, "REJECTED": 0.1},
            observed_status="REJECTED",
            predicted_progress=0.2,
            observed_progress=-0.1,
        )
        self.assertIs(item.resonance_class, ResonanceClass.CONTRADICTED)
        self.assertAlmostEqual(item.observed_class_probability, 0.1)
        self.assertAlmostEqual(item.progress_error, 0.3)


if __name__ == "__main__":
    unittest.main()
