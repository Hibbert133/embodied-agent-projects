from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.check_probemem_acr_feedback_sufficiency_seeds import development_seeds


ROOT = Path(__file__).resolve().parents[1]


class FeedbackSufficiencyProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads((ROOT / "configs/probemem_acr/verification_feedback_sufficiency_development_v1.json").read_text(encoding="utf-8"))

    def test_fresh_development_range_and_reservation(self) -> None:
        self.assertEqual(development_seeds(self.config), list(range(3300, 3500)))
        self.assertEqual(self.config["seed_partitions"]["reserved_not_executed"], [3500, 3599])
        self.assertFalse(set(development_seeds(self.config)) & set(range(3100, 3200)))

    def test_label_blind_stop_and_four_realizations(self) -> None:
        self.assertFalse(self.config["stopping_rule"]["reads_verification_outcomes"])
        self.assertEqual(self.config["first_retry_realizations"], 4)

    def test_prohibitions_block_scope_expansion(self) -> None:
        prohibited = self.config["prohibitions"]
        for key in ("fit_selector", "call_llm", "write_online_memory", "run_validation", "run_heldout"):
            self.assertTrue(prohibited[key])


if __name__ == "__main__":
    unittest.main()
