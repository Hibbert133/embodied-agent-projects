from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_candidate_micro_evidence_development import validate_config


class CandidateMicroEvidenceProtocolTest(unittest.TestCase):
    def test_protocol_is_threshold_free_and_bounded(self) -> None:
        config = json.loads(Path("configs/autoresearch/candidate_micro_evidence_development_v1.json").read_text(encoding="utf-8"))
        validate_config(config)
        self.assertEqual(config["prefix_horizons"], [16, 32, 64, 128])
        self.assertFalse(config["analysis"]["fit_threshold"])
        self.assertEqual(config["api_calls"], 0)

    def test_protocol_rejects_candidate_changes(self) -> None:
        config = json.loads(Path("configs/autoresearch/candidate_micro_evidence_development_v1.json").read_text(encoding="utf-8"))
        config["candidates"] = ["stochastic_retry"]
        with self.assertRaisesRegex(ValueError, "registered intervention candidates"):
            validate_config(config)


if __name__ == "__main__":
    unittest.main()
