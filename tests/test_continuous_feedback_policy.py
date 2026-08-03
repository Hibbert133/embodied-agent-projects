from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.probemem.continuous_feedback_policy import PROGRESS_THRESHOLD_METRES, decide_from_progress
from src.probemem.tools import InterventionSkill


ROOT = Path(__file__).resolve().parents[1]


class ContinuousFeedbackPolicyTests(unittest.TestCase):
    def test_threshold_is_exactly_zero_and_not_fitted(self) -> None:
        config = json.loads((ROOT / "configs/probemem_acr/continuous_feedback_development_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(PROGRESS_THRESHOLD_METRES, 0.0)
        self.assertEqual(config["continuous_rule"]["threshold"], 0.0)
        self.assertTrue(config["prohibitions"]["retune_threshold"])

    def test_positive_repeats_nonpositive_switches_and_success_stops(self) -> None:
        self.assertEqual(decide_from_progress(first_status="INCONCLUSIVE", first_observed_progress=0.001).selected_skill, InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY)
        self.assertEqual(decide_from_progress(first_status="REJECTED", first_observed_progress=0.0).selected_skill, InterventionSkill.BOUNDED_PLANAR_COMPENSATION)
        self.assertEqual(decide_from_progress(first_status="REJECTED", first_observed_progress=-0.001).selected_skill, InterventionSkill.BOUNDED_PLANAR_COMPENSATION)
        self.assertIsNone(decide_from_progress(first_status="ACCEPTED", first_observed_progress=-1.0).selected_skill)

    def test_fresh_development_seeds_preserve_heldout(self) -> None:
        config = json.loads((ROOT / "configs/probemem_acr/continuous_feedback_development_v1.json").read_text(encoding="utf-8"))
        seeds = set(range(config["seed_partitions"]["development"][0], config["seed_partitions"]["development"][1] + 1))
        self.assertFalse(seeds & set(range(3100, 3200)))
        self.assertFalse(seeds & set(range(3800, 3900)))


if __name__ == "__main__":
    unittest.main()
