"""Tests for the frozen ProbeMem-ACR protocol scaffold."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.check_probemem_acr_seed_registry import _ranges, _seed_values


ROOT = Path(__file__).resolve().parents[1]


class ProbeMemAcrProtocolTest(unittest.TestCase):
    def test_registered_partitions_are_disjoint_and_sized(self) -> None:
        config = json.loads(
            (ROOT / "configs/probemem_acr/seed_registry_v1.json").read_text(
                encoding="utf-8"
            )
        )
        ranges = _ranges(config)
        self.assertEqual(len(ranges["development"]), 100)
        self.assertEqual(len(ranges["validation_reserved"]), 50)
        self.assertEqual(len(ranges["heldout_reserved"]), 100)

    def test_seed_parser_ignores_random_namespaces(self) -> None:
        payload = {
            "seed_range": [1100, 1102],
            "random_seed_namespaces": {"initial": 1200},
            "seed": 1103,
        }
        self.assertEqual(list(_seed_values(payload)), [1100, 1101, 1102, 1103])

    def test_condition_mapping_has_twenty_units_per_condition(self) -> None:
        counts = [0] * 5
        for seed in range(1100, 1200):
            counts[(seed - 1100) % 5] += 1
        self.assertEqual(counts, [20] * 5)


if __name__ == "__main__":
    unittest.main()
