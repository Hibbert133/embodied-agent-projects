"""Tests for leakage-safe chronological contextual ACR decisions."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.generate_probemem_acr_contextual_manifest import IMPLEMENTATION_PATHS
from src.probemem.contextual_policy import ContextualOutcome, decide_contextual_action
from src.probemem.distributional_policy import COMPENSATION, RETRY
from src.probemem.intervention_utility import INTERVENTION_APPLICABILITY_FEATURES


ROOT = Path(__file__).resolve().parents[1]


def _values(value: float) -> tuple[float, ...]:
    return (value,) * len(INTERVENTION_APPLICABILITY_FEATURES)


class ProbeMemAcrContextualPolicyTest(unittest.TestCase):
    def test_current_and_future_outcomes_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "current or future"):
            decide_contextual_action(
                method="contextual_greedy", episode_id=2, operational_index=17,
                query_values=_values(0.0),
                history=[ContextualOutcome(2, RETRY, 1.0, _values(0.0))],
            )

    def test_exploration_is_frozen_and_alternating(self) -> None:
        decision = decide_contextual_action(
            method="contextual_abstain", episode_id=5, operational_index=5,
            query_values=_values(1.0),
            history=[ContextualOutcome(index, RETRY, 0.0, _values(float(index))) for index in range(1, 5)],
        )
        self.assertIs(decision.selected_skill, COMPENSATION)
        self.assertEqual(decision.reason, "frozen alternating contextual exploration")

    def test_context_changes_action_prediction_without_nearest_neighbor_copy(self) -> None:
        history = []
        for index in range(1, 17):
            skill = COMPENSATION if index % 2 else RETRY
            context = -1.0 if index <= 8 else 1.0
            utility = 1.0 if (skill is COMPENSATION) == (context < 0) else 0.0
            history.append(ContextualOutcome(index, skill, utility, _values(context)))
        negative = decide_contextual_action(
            method="contextual_greedy", episode_id=17, operational_index=17,
            query_values=_values(-1.0), history=history,
        )
        positive = decide_contextual_action(
            method="contextual_greedy", episode_id=18, operational_index=17,
            query_values=_values(1.0), history=history,
        )
        self.assertIs(negative.selected_skill, COMPENSATION)
        self.assertIs(positive.selected_skill, RETRY)

    def test_scaler_excludes_current_episode(self) -> None:
        history = [
            ContextualOutcome(index, COMPENSATION if index % 2 else RETRY, 0.5, _values(float(index)))
            for index in range(1, 17)
        ]
        decision = decide_contextual_action(
            method="contextual_greedy", episode_id=20, operational_index=20,
            query_values=_values(1000.0), history=history,
        )
        self.assertEqual(decision.standardization_episode_ids, tuple(range(1, 17)))
        self.assertNotIn(20, decision.standardization_episode_ids)

    def test_protocol_freezes_all_features_and_no_api(self) -> None:
        config = json.loads(
            (ROOT / "configs/probemem_acr/contextual_utility_development_v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["seed_partitions"]["development"], [2500, 2699])
        self.assertEqual(config["stopping_rule"]["target_operational_cases"], 60)
        self.assertFalse(config["contextual_model"]["feature_selection"])
        self.assertTrue(config["prohibitions"]["call_llm"])
        self.assertTrue(config["prohibitions"]["run_heldout"])

    def test_manifest_hashes_policy_collection_and_replay(self) -> None:
        paths = {path.as_posix() for path in IMPLEMENTATION_PATHS}
        self.assertIn("src/probemem/contextual_policy.py", paths)
        self.assertIn("scripts/collect_probemem_acr_distributional_stream.py", paths)
        self.assertIn("scripts/replay_probemem_acr_contextual_methods.py", paths)


if __name__ == "__main__":
    unittest.main()
