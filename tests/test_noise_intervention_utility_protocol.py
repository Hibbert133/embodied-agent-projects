from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_intervention_identifiability_development import (
    validate_development_config,
)


CONFIG = Path("configs/autoresearch/noise_intervention_utility_development_v1.json")


class NoiseInterventionUtilityProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_uses_only_fresh_noise_development_units(self) -> None:
        validate_development_config(self.config)
        self.assertEqual(
            [item["condition_id"] for item in self.config["conditions"]],
            ["fault_05"],
        )
        seeds = set(range(410, 430))
        self.assertEqual(
            seeds,
            set(
                range(
                    self.config["seed_start"],
                    self.config["seed_start"] + self.config["num_seeds"],
                )
            ),
        )
        self.assertFalse(seeds & set(range(330, 410)))

    def test_analysis_cannot_fit_a_threshold(self) -> None:
        self.assertFalse(self.config["analysis"]["fit_threshold"])
        self.assertTrue(self.config["evaluator_label"]["oracle_only"])
        self.assertEqual(self.config["api_calls"], 0)


if __name__ == "__main__":
    unittest.main()
