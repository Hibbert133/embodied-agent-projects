import unittest

from scripts.collect_temporal_evidence_development import temporal_feature_row
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


if __name__ == "__main__":
    unittest.main()
