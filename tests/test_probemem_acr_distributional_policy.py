"""Tests for chronological distributional ACR decisions."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.generate_probemem_acr_distributional_manifest import IMPLEMENTATION_PATHS
from scripts.replay_probemem_acr_distributional_methods import _paired_bootstrap_difference
from src.probemem.distributional_policy import (
    COMPENSATION,
    RETRY,
    ObservedActionOutcome,
    decide_distributional_action,
    posterior_alpha,
)


ROOT = Path(__file__).resolve().parents[1]


class ProbeMemAcrDistributionalPolicyTest(unittest.TestCase):
    def test_posterior_counts_all_outcomes_by_action(self) -> None:
        history = [
            ObservedActionOutcome(1, COMPENSATION, "ACCEPTED"),
            ObservedActionOutcome(2, COMPENSATION, "REJECTED"),
            ObservedActionOutcome(3, RETRY, "INCONCLUSIVE"),
        ]
        self.assertEqual(posterior_alpha(history, COMPENSATION), (2.0, 1.0, 2.0))
        self.assertEqual(posterior_alpha(history, RETRY), (1.0, 2.0, 1.0))

    def test_current_and_future_outcomes_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "current or future"):
            decide_distributional_action(
                method="posterior_greedy", episode_id=2, operational_index=2,
                history=[ObservedActionOutcome(2, RETRY, "ACCEPTED")], sampling_seed=1,
            )

    def test_frozen_exploration_precedes_adaptation(self) -> None:
        decision = decide_distributional_action(
            method="posterior_abstain", episode_id=5, operational_index=5,
            history=[ObservedActionOutcome(index, RETRY, "REJECTED") for index in range(1, 5)],
            sampling_seed=2,
        )
        self.assertIs(decision.selected_skill, COMPENSATION)
        self.assertEqual(decision.reason, "frozen alternating exploration")

    def test_uncertain_posterior_abstains_reproducibly(self) -> None:
        left = decide_distributional_action(
            method="posterior_abstain", episode_id=9, operational_index=9,
            history=[
                ObservedActionOutcome(index, COMPENSATION if index % 2 else RETRY, "ACCEPTED")
                for index in range(1, 9)
            ], sampling_seed=3,
        )
        right = decide_distributional_action(
            method="posterior_abstain", episode_id=9, operational_index=9,
            history=[
                ObservedActionOutcome(index, COMPENSATION if index % 2 else RETRY, "ACCEPTED")
                for index in range(1, 9)
            ], sampling_seed=3,
        )
        self.assertIsNone(left.selected_skill)
        self.assertEqual(left, right)

    def test_protocol_is_fresh_frozen_and_no_api(self) -> None:
        config = json.loads(
            (ROOT / "configs/probemem_acr/distributional_memory_development_v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["seed_partitions"]["development"], [2000, 2099])
        self.assertEqual(config["distributional_policy"]["exploration_episodes"], 8)
        self.assertEqual(config["distributional_policy"]["superiority_probability"], 0.9)
        self.assertTrue(config["prohibitions"]["call_llm"])
        self.assertTrue(config["prohibitions"]["run_heldout"])

    def test_manifest_tracks_policy_collection_and_replay(self) -> None:
        paths = {path.as_posix() for path in IMPLEMENTATION_PATHS}
        self.assertIn("src/probemem/distributional_policy.py", paths)
        self.assertIn("scripts/collect_probemem_acr_distributional_stream.py", paths)
        self.assertIn("scripts/replay_probemem_acr_distributional_methods.py", paths)

    def test_paired_bootstrap_is_reproducible(self) -> None:
        left = _paired_bootstrap_difference([1, 0, 1], [0, 0, 1], seed=9702, resamples=100)
        right = _paired_bootstrap_difference([1, 0, 1], [0, 0, 1], seed=9702, resamples=100)
        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
