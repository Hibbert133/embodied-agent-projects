"""Tests for falsifiable development intervention-utility records."""

from __future__ import annotations

import unittest
from dataclasses import replace

from src.probemem import (
    EvidenceSignature,
    FreshVerificationObservation,
    InterventionSkill,
    InterventionUtilityRecord,
    PredictedOutcome,
    PredictionRelation,
    UtilityVerdict,
)
from src.reasoning import validate_no_oracle_evidence


def _record(status: str = "ACCEPTED") -> InterventionUtilityRecord:
    return InterventionUtilityRecord.create(
        record_id="utility_001",
        source_episode_id=1,
        source_run_id="run_development",
        source_manifest_id="manifest_development",
        source_method="verified_episodic_retrieval",
        applicability_signature=EvidenceSignature(
            schema_version=1,
            evidence_id="post_probe_evidence_001",
            episode_id=1,
            values=(0.1, 0.2, 0.3, 0.4, 0.01, -0.01, 0.5),
        ),
        selected_skill=InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
        predicted_outcome=PredictedOutcome("ACCEPTED", 0.1, 500),
        observed_outcome=FreshVerificationObservation(
            evidence_id="fresh_verification_001",
            verification_status=status,
            verification_success=status == "ACCEPTED",
            environment_steps=500,
            final_object_goal_distance=0.05,
            goal_distance_change=0.1,
        ),
    )


class ProbeMemInterventionUtilityTest(unittest.TestCase):
    def test_host_derives_support_and_matched_prediction(self) -> None:
        record = _record("ACCEPTED")
        self.assertIs(record.utility_verdict, UtilityVerdict.SUPPORTED)
        self.assertIs(record.prediction_relation, PredictionRelation.MATCHED)
        self.assertFalse(record.actionable_memory)
        self.assertFalse(record.principle_promotion_eligible)
        validate_no_oracle_evidence(record.to_dict())

    def test_rejected_verification_is_explicit_contradiction(self) -> None:
        record = _record("REJECTED")
        self.assertIs(record.utility_verdict, UtilityVerdict.CONTRADICTED)
        self.assertIs(record.prediction_relation, PredictionRelation.NEGATIVE_SURPRISE)

    def test_inconclusive_verification_is_not_promoted_or_rejected(self) -> None:
        record = _record("INCONCLUSIVE")
        self.assertIs(record.utility_verdict, UtilityVerdict.UNRESOLVED)
        self.assertIs(record.prediction_relation, PredictionRelation.NEGATIVE_SURPRISE)

    def test_caller_cannot_override_host_derived_verdict(self) -> None:
        with self.assertRaisesRegex(ValueError, "host-derived"):
            replace(_record("REJECTED"), utility_verdict=UtilityVerdict.SUPPORTED)

    def test_development_record_cannot_become_actionable_memory(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot enter actionable memory"):
            replace(_record(), actionable_memory=True)

    def test_abstention_is_not_an_executed_intervention(self) -> None:
        with self.assertRaisesRegex(ValueError, "executed intervention"):
            replace(_record(), selected_skill=InterventionSkill.ABSTAIN)


if __name__ == "__main__":
    unittest.main()
