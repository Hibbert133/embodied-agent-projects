from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_intervention_identifiability_development import (
    COMPENSATION,
    RETRY,
    _candidate_from_mechanism,
    validate_development_config,
)


CONFIG = Path("configs/autoresearch/intervention_identifiability_development_v2.json")


class InterventionIdentifiabilityProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_development_split_does_not_overlap_heldout(self) -> None:
        validate_development_config(self.config)
        seeds = set(
            range(
                self.config["seed_start"],
                self.config["seed_start"] + self.config["num_seeds"],
            )
        )
        self.assertFalse(seeds & set(range(330, 340)))

    def test_protocol_has_no_rendering_or_api_calls(self) -> None:
        self.assertFalse(self.config["rendering"])
        self.assertEqual(self.config["api_calls"], 0)
        self.assertFalse(
            self.config["unavailable_candidate_handling"]["abstain_is_executable"]
        )

    def test_mechanism_mapping_is_explicit(self) -> None:
        self.assertEqual(_candidate_from_mechanism("stable_bias"), COMPENSATION)
        self.assertEqual(_candidate_from_mechanism("stochastic_noise"), RETRY)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            _candidate_from_mechanism("oracle_parameter")


if __name__ == "__main__":
    unittest.main()
