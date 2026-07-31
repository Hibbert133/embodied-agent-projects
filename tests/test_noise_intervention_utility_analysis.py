from __future__ import annotations

import unittest

from scripts.analyze_noise_intervention_utility import FEATURES, analyze_feature_rows


def row(label: str, base: float) -> dict[str, object]:
    value: dict[str, object] = {
        "paired_comparable": "True",
        "best_candidate_ids": label,
    }
    value.update({feature: base for feature in FEATURES})
    return value


class NoiseInterventionUtilityAnalysisTest(unittest.TestCase):
    def test_reports_prevalence_and_preregistered_direction(self) -> None:
        result = analyze_feature_rows(
            [
                row("probe_grounded_compensation", 0.1),
                row("stochastic_retry", 0.9),
            ]
        )
        self.assertEqual(result["retry_preferred_units"], 1)
        self.assertEqual(result["retry_prevalence"], 0.5)
        self.assertFalse(result["threshold_fitted"])
        for feature in FEATURES:
            self.assertEqual(result["features"][feature]["roc_auc"], 1.0)

    def test_single_class_is_explicitly_incomplete(self) -> None:
        result = analyze_feature_rows(
            [row("probe_grounded_compensation", 0.1)]
        )
        self.assertEqual(result["status"], "INCOMPLETE_SINGLE_CLASS_LABEL")
        self.assertIsNone(result["features"][FEATURES[0]]["roc_auc"])


if __name__ == "__main__":
    unittest.main()
