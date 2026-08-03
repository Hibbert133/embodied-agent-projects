"""Freeze checks for the ProbeMem-Online chronological development stream."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/probemem_online/sequential_development_v1.json"


class ProbeMemOnlineSequentialProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_stream_is_frozen_development_only_and_targets_sixty_cases(self) -> None:
        self.assertEqual(self.config["status"], "DEVELOPMENT_FROZEN_BEFORE_EXECUTION")
        self.assertEqual(self.config["seed_range"], [4300, 4499])
        self.assertEqual(self.config["target_operational_cases"], 60)
        self.assertTrue(self.config["prohibitions"]["validation"])
        self.assertTrue(self.config["prohibitions"]["heldout"])

    def test_distribution_shift_order_is_complete_and_nonoverlapping(self) -> None:
        seeds: list[int] = []
        for segment in self.config["segments"]:
            start, stop = segment["seed_range"]
            seeds.extend(range(start, stop + 1))
            self.assertGreaterEqual(len(segment["regime_cycle"]), 2)
        self.assertEqual(seeds, list(range(4300, 4500)))
        self.assertEqual(len(seeds), len(set(seeds)))

    def test_bootstrap_snapshot_hash_is_frozen(self) -> None:
        memory = self.config["memory"]
        snapshot = ROOT / memory["bootstrap_snapshot"]
        self.assertTrue(snapshot.is_file())
        self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(), memory["bootstrap_sha256"])

    def test_random_namespaces_and_budget_are_independent(self) -> None:
        namespaces = list(self.config["random_namespaces"].values())
        self.assertEqual(len(namespaces), len(set(namespaces)))
        budget = self.config["budget"]
        self.assertEqual(
            budget["total_case_max_steps"],
            budget["initial_max_steps"] + budget["probe_max_steps"] + budget["verification_max_steps"],
        )


if __name__ == "__main__":
    unittest.main()
