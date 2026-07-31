from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_intervention_identifiability_development import validate_development_config


class NoiseRepeatabilitySourceProtocolTest(unittest.TestCase):
    def test_fresh_label_blind_source_is_bounded(self) -> None:
        config = json.loads(
            Path("configs/autoresearch/noise_repeatability_source_v1.json").read_text(
                encoding="utf-8"
            )
        )
        validate_development_config(config)
        seeds = set(range(config["seed_start"], config["seed_start"] + config["num_seeds"]))
        self.assertFalse(seeds & set(range(330, 340)))
        self.assertFalse(seeds & set(range(400, 489)))
        self.assertEqual(config["stopping_rule"]["depends_only_on"], "paired-comparable operational count")
        self.assertFalse(config["stopping_rule"]["may_read_utility_label"])
        self.assertTrue(config["analysis"]["outcomes_hidden_until_repeatability_selection_is_frozen"])


if __name__ == "__main__":
    unittest.main()
