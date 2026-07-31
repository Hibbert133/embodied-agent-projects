"""Freeze checks for label-blind ProbeMem noise utility coverage."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.run_probemem_paired_utility import validate_stopping_rule


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/probemem_v2/noise_intervention_utility_coverage_v1.json"


class ProbeMemNoiseUtilityCoverageProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_coverage_is_noise_only_and_uses_fresh_development_seeds(self) -> None:
        self.assertEqual(self.config["condition_cycle"], ["fault_05"])
        start, stop = self.config["seed_range"]
        seeds = set(range(start, stop + 1))
        heldout_start, heldout_stop = self.config["heldout_seed_range"]
        self.assertEqual(len(seeds), 80)
        self.assertTrue(seeds.isdisjoint(range(720, 760)))
        self.assertTrue(seeds.isdisjoint(range(heldout_start, heldout_stop + 1)))

    def test_stop_rule_is_label_blind_and_bounded(self) -> None:
        self.assertEqual(validate_stopping_rule(self.config), 20)
        stopping = self.config["stopping_rule"]
        self.assertFalse(stopping["may_read_candidate_outcome"])
        self.assertFalse(stopping["may_read_winner_label"])
        self.assertEqual(stopping["maximum_initial_units"], 80)

    def test_outcome_dependent_stop_rule_fails_closed(self) -> None:
        modified = copy.deepcopy(self.config)
        modified["stopping_rule"]["may_read_candidate_outcome"] = True
        with self.assertRaisesRegex(ValueError, "label-blind"):
            validate_stopping_rule(modified)

    def test_coverage_still_forbids_api_memory_and_principles(self) -> None:
        scope = self.config["scope"]
        self.assertEqual(scope["api_calls"], 0)
        self.assertFalse(scope["actionable_memory_write"])
        self.assertFalse(scope["principle_generation"])
        self.assertFalse(scope["heldout_claim"])


if __name__ == "__main__":
    unittest.main()
