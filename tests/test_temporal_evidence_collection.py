import unittest

from scripts.collect_temporal_evidence_development import phase_feature_row, temporal_feature_row
from src.diagnosis.phase_conditioned import PhaseConditionedEstimate, PhaseResponseEstimate
from src.diagnosis.passive_planar import PassivePlanarEstimate


class TemporalEvidenceCollectionTest(unittest.TestCase):
    def test_flattened_features_preserve_agent_visible_estimate(self) -> None:
        estimate = PassivePlanarEstimate(
            estimated_drift_per_step=(0.1, -0.2),
            axis_response_gain=(0.01, 0.02),
            normalized_residual=(0.3, 0.4),
            action_excitation=(0.5, 0.6),
            axis_confidence=(0.7, 0.8),
            overall_confidence=0.75,
            uncertainty=0.25,
            dominant_axis="y",
            estimated_direction="negative",
            sample_count=20,
        )
        result = temporal_feature_row(
            condition_id="fault",
            seed=320,
            case_id="case",
            estimate=estimate,
        )
        self.assertEqual(result["temporal_uncertainty"], 0.25)
        self.assertAlmostEqual(result["normalized_residual_norm"], 0.5)
        self.assertEqual(result["sample_count"], 20)

    def test_phase_features_preserve_registered_score(self) -> None:
        phase = PhaseResponseEstimate(
            phase="approach", sample_count=8, axis_response_gain=(0.01, 0.01),
            estimated_drift_per_step=(0.0, 0.0), normalized_residual=(0.2, 0.4),
            normalized_residual_norm=0.316, action_excitation=(0.2, 0.2),
        )
        estimate = PhaseConditionedEstimate(
            phase_estimates=(phase,),
            phase_sample_counts={"approach": 8, "push": 2, "near_goal": 0},
            phase_inconsistency=0.316, eligible_sample_fraction=0.8, sample_count=10,
        )
        result = phase_feature_row(
            condition_id="fault", seed=320, case_id="case", estimate=estimate
        )
        self.assertEqual(result["phase_inconsistency"], 0.316)
        self.assertTrue(result["approach_eligible"])
        self.assertFalse(result["push_eligible"])


if __name__ == "__main__":
    unittest.main()
