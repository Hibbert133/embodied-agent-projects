from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_intervention_identifiability_development import validate_development_config


CONFIG = Path("configs/autoresearch/noise_intervention_utility_coverage_v1.json")


class NoiseUtilityCoverageProtocolTest(unittest.TestCase):
    def test_stop_rule_is_label_blind_and_bounded(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        validate_development_config(config)
        self.assertEqual(config["seed_start"], 430)
        self.assertEqual(config["target_paired_comparable_operational_units"], 20)
        self.assertEqual(config["num_seeds"], 60)
        self.assertFalse(config["stopping_rule"]["may_read_utility_label"])
        self.assertFalse(config["analysis"]["fit_threshold"])


if __name__ == "__main__":
    unittest.main()
