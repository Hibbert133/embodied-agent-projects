"""Tests for the replacement distributional development population."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.generate_probemem_acr_distributional_manifest_v2 import IMPLEMENTATION_PATHS


ROOT = Path(__file__).resolve().parents[1]


class ProbeMemAcrDistributionalProtocolV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.v1 = json.loads(
            (ROOT / "configs/probemem_acr/distributional_memory_development_v1.json").read_text(encoding="utf-8")
        )
        cls.v2 = json.loads(
            (ROOT / "configs/probemem_acr/distributional_memory_development_v2.json").read_text(encoding="utf-8")
        )

    def test_uses_fresh_larger_development_population(self) -> None:
        self.assertEqual(self.v2["seed_partitions"]["development"], [2200, 2349])
        self.assertEqual(self.v2["seed_partitions"]["validation_reserved"], [2350, 2399])
        self.assertEqual(self.v2["seed_partitions"]["heldout_reserved"], [2400, 2499])
        self.assertEqual(self.v2["stopping_rule"]["maximum_initial_units"], 150)
        self.assertEqual(self.v2["stopping_rule"]["target_operational_cases"], 40)
        self.assertFalse(self.v2["stopping_rule"]["reads_candidate_outcomes"])

    def test_policy_and_gate_are_not_retuned_after_incomplete_v1(self) -> None:
        self.assertEqual(self.v2["distributional_policy"], self.v1["distributional_policy"])
        self.assertEqual(self.v2["promotion_gate"], self.v1["promotion_gate"])
        self.assertEqual(self.v2["methods"], self.v1["methods"])

    def test_later_phases_and_api_remain_prohibited(self) -> None:
        prohibitions = self.v2["prohibitions"]
        self.assertTrue(prohibitions["call_llm"])
        self.assertTrue(prohibitions["promote_principle"])
        self.assertTrue(prohibitions["run_validation"])
        self.assertTrue(prohibitions["run_heldout"])

    def test_manifest_hashes_shared_frozen_execution(self) -> None:
        paths = {path.as_posix() for path in IMPLEMENTATION_PATHS}
        self.assertIn("scripts/collect_probemem_acr_distributional_stream.py", paths)
        self.assertIn("scripts/replay_probemem_acr_distributional_methods.py", paths)
        self.assertIn("src/probemem/distributional_policy.py", paths)


if __name__ == "__main__":
    unittest.main()
