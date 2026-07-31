from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_candidate_repeatability_evidence import validate_config
from scripts.run_intervention_identifiability_development import validate_development_config


class CandidateRepeatabilityProtocolTest(unittest.TestCase):
    def test_selector_and_fresh_source_are_frozen_before_collection(self) -> None:
        selector = json.loads(
            Path("configs/autoresearch/candidate_repeatability_evidence_v1.json").read_text(
                encoding="utf-8"
            )
        )
        source = json.loads(
            Path("configs/autoresearch/noise_repeatability_confirmatory_source_v1.json").read_text(
                encoding="utf-8"
            )
        )
        validate_config(selector)
        validate_development_config(source)
        self.assertEqual(selector["required_source_seed_range"], [600, 699])
        self.assertEqual(source["seed_start"], 600)
        self.assertTrue(source["analysis"]["selector_frozen_before_collection"])
        self.assertFalse(selector["selector"]["fit_threshold"])


if __name__ == "__main__":
    unittest.main()
