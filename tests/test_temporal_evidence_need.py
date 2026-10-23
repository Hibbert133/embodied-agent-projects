import unittest

from scripts.analyze_temporal_evidence_need import (
    roc_auc_for_probe_need,
    select_temporal_threshold,
)


def row(uncertainty: float, passive: str, probe: str, truth: str) -> dict[str, object]:
    return {
        "temporal_uncertainty": uncertainty,
        "passive_prediction": passive,
        "probe_prediction": probe,
        "mechanism_class_oracle": truth,
        "probe_needed_oracle": passive != truth and probe == truth,
    }


class TemporalEvidenceNeedTest(unittest.TestCase):
    def test_threshold_uses_high_uncertainty_direction_only(self) -> None:
        rows = [
            row(0.1, "stable_bias", "stable_bias", "stable_bias"),
            row(0.8, "stable_bias", "stochastic_noise", "stochastic_noise"),
        ]
        result = select_temporal_threshold(rows)
        self.assertEqual(result["development_correct"], 2)
        self.assertEqual(result["development_probe_requests"], 1)
        self.assertGreater(result["threshold"], 0.1)
        self.assertLess(result["threshold"], 0.8)

    def test_auc_scores_probe_need_without_changing_direction(self) -> None:
        rows = [
            row(0.2, "stable_bias", "stable_bias", "stable_bias"),
            row(0.9, "stable_bias", "stochastic_noise", "stochastic_noise"),
        ]
        self.assertEqual(roc_auc_for_probe_need(rows), 1.0)


if __name__ == "__main__":
    unittest.main()
