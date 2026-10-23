"""Tests for post-hoc ProbeMem-ACR failure localization definitions."""

from __future__ import annotations

import unittest
import json
from pathlib import Path

from scripts.analyze_probemem_acr_failure_localization import (
    COMPENSATION,
    RETRY,
    outcome_partition,
    rank_probability,
)


class ProbeMemAcrFailureLocalizationTest(unittest.TestCase):
    def test_replication_protocol_reserves_fresh_disjoint_seeds(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = json.loads(
            (root / "configs/probemem_acr/retry_utility_replication_v1.json").read_text(encoding="utf-8")
        )
        partitions = [set(range(bounds[0], bounds[1] + 1)) for bounds in config["seed_partitions"].values()]
        self.assertEqual([len(partition) for partition in partitions], [100, 50, 50])
        self.assertFalse(partitions[0] & partitions[1])
        self.assertFalse(partitions[0] & partitions[2])
        self.assertEqual(config["registered_condition"], "fault_05")
        self.assertTrue(config["prohibitions"]["fit_threshold"])
        self.assertTrue(config["prohibitions"]["call_llm"])

    def test_outcome_partition_requires_both_registered_candidates(self) -> None:
        self.assertEqual(
            outcome_partition({COMPENSATION: "ACCEPTED", RETRY: "REJECTED"}),
            "COMPENSATION_ONLY_RECOVERY",
        )
        self.assertEqual(
            outcome_partition({COMPENSATION: "REJECTED", RETRY: "ACCEPTED"}),
            "RETRY_ONLY_RECOVERY",
        )
        with self.assertRaises(ValueError):
            outcome_partition({COMPENSATION: "ACCEPTED"})

    def test_rank_probability_is_descriptive_and_tie_aware(self) -> None:
        self.assertEqual(rank_probability([2.0], [1.0]), 1.0)
        self.assertEqual(rank_probability([1.0], [2.0]), 0.0)
        self.assertEqual(rank_probability([1.0], [1.0]), 0.5)
        self.assertAlmostEqual(rank_probability([0.0, 2.0], [1.0]), 0.5)


if __name__ == "__main__":
    unittest.main()
