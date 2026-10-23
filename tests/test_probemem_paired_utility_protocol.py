"""Freeze checks for ProbeMem paired intervention-utility development."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.generate_probemem_paired_utility_manifest import IMPLEMENTATION_PATHS


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/probemem_v2/paired_intervention_utility_development_v1.json"


class ProbeMemPairedUtilityProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_development_stream_is_fresh_and_disjoint_from_heldout(self) -> None:
        start, stop = self.config["seed_range"]
        development = set(range(start, stop + 1))
        heldout_start, heldout_stop = self.config["heldout_seed_range"]
        self.assertEqual(len(development), 20)
        self.assertTrue(development.isdisjoint(range(720, 740)))
        self.assertTrue(development.isdisjoint(range(heldout_start, heldout_stop + 1)))

    def test_two_candidates_share_evidence_and_verification_randomness(self) -> None:
        self.assertEqual(
            self.config["candidates"],
            ["BOUNDED_PLANAR_COMPENSATION", "INDEPENDENT_STOCHASTIC_RETRY"],
        )
        paired = self.config["paired_execution"]
        self.assertTrue(paired["same_initial_rollout"])
        self.assertTrue(paired["same_probe_evidence"])
        self.assertTrue(paired["common_verification_random_numbers"])
        self.assertTrue(paired["counterfactual_outcomes_evaluator_only"])

    def test_evaluator_budget_is_separate_from_online_budget(self) -> None:
        budget = self.config["budget"]
        self.assertEqual(
            budget["online_single_candidate_max_steps"],
            budget["initial_rollout_max_steps"]
            + budget["registered_probe_max_steps"]
            + budget["fresh_verification_max_steps_per_candidate"],
        )
        self.assertEqual(
            budget["evaluator_paired_collection_max_steps"],
            budget["initial_rollout_max_steps"]
            + budget["registered_probe_max_steps"]
            + 2 * budget["fresh_verification_max_steps_per_candidate"],
        )

    def test_protocol_cannot_generate_principles_or_write_memory(self) -> None:
        scope = self.config["scope"]
        self.assertEqual(scope["api_calls"], 0)
        self.assertFalse(scope["rendering"])
        self.assertFalse(scope["principle_generation"])
        self.assertFalse(scope["actionable_memory_write"])
        self.assertFalse(scope["heldout_claim"])

    def test_manifest_tracks_every_registered_implementation(self) -> None:
        self.assertTrue(all((ROOT / path).is_file() for path in IMPLEMENTATION_PATHS))


if __name__ == "__main__":
    unittest.main()
