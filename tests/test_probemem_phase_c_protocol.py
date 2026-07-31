"""Freeze and chronology checks for the ProbeMem Phase-C development run."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_probemem_phase_c_comparison import _api_metrics, _memory_context
from src.probemem import (
    ChronologicalEpisodeMemory,
    EvidenceSignature,
    InterventionSkill,
    RecoveryExperience,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/probemem_v2/verified_episode_development_v2.json"


def _signature(episode_id: int) -> EvidenceSignature:
    return EvidenceSignature(
        schema_version=1,
        evidence_id=f"evidence_{episode_id}",
        episode_id=episode_id,
        values=(0.1, 0.2, 0.3, 0.4, 0.01, -0.01, 0.5),
    )


def _experience(episode_id: int, status: str) -> RecoveryExperience:
    return RecoveryExperience(
        schema_version=1,
        record_id=f"record_{episode_id}",
        source_episode_id=episode_id,
        source_manifest_id="manifest_phase_c_test",
        signature=_signature(episode_id),
        selected_skill=InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY,
        predicted_verification_status="ACCEPTED",
        observed_verification_status=status,
        verification_success=status == "ACCEPTED",
        interaction_cost=500,
    )


class ProbeMemPhaseCProtocolTest(unittest.TestCase):
    def test_api_costs_are_aggregated_without_rollout_time(self) -> None:
        metrics = _api_metrics(
            [
                {
                    "api": {
                        "attempts": [
                            {
                                "latency_ms": 12.5,
                                "usage": {"input_tokens": 10, "output_tokens": 4},
                                "valid": True,
                            },
                            {
                                "latency_ms": 7.5,
                                "usage": {"input_tokens": 8, "output_tokens": 2},
                                "valid": False,
                            },
                        ]
                    }
                }
            ]
        )
        self.assertEqual(metrics["api_latency_ms"], 20.0)
        self.assertEqual(metrics["api_input_tokens"], 18)
        self.assertEqual(metrics["api_output_tokens"], 6)
        self.assertEqual(metrics["invalid_structured_outputs"], 1)

    def test_registered_development_stream_does_not_overlap_heldout(self) -> None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        development = set(range(config["seed_range"][0], config["seed_range"][1] + 1))
        heldout = set(
            range(config["heldout_seed_range"][0], config["heldout_seed_range"][1] + 1)
        )
        self.assertEqual(len(development), 20)
        self.assertTrue(development.isdisjoint(heldout))
        self.assertEqual(len(config["condition_cycle"]), 5)

    def test_budget_and_api_caps_are_explicit(self) -> None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        budget = config["budget"]
        self.assertEqual(
            budget["total_case_max_steps"],
            budget["initial_rollout_max_steps"]
            + budget["registered_probe_max_steps"]
            + budget["fresh_verification_max_steps"],
        )
        self.assertEqual(config["api_budget"]["maximum_calls_per_method_case"], 2)
        self.assertLessEqual(
            config["api_budget"]["maximum_calls"],
            len(config["methods"])
            * len(range(config["seed_range"][0], config["seed_range"][1] + 1))
            * config["api_budget"]["maximum_calls_per_method_case"],
        )

    def test_raw_and_verified_contexts_are_strictly_chronological(self) -> None:
        memory = ChronologicalEpisodeMemory(scales=(1.0,) * 7)
        memory.record(_experience(1, "REJECTED"))
        memory.record(_experience(2, "ACCEPTED"))
        query = _signature(3)

        raw_snapshot, raw_rows = _memory_context(
            "raw_episodic_retrieval_development_only", memory, query, 3, 3
        )
        verified_snapshot, verified_rows = _memory_context(
            "verified_episodic_retrieval", memory, query, 3, 3
        )

        self.assertEqual({row["source_episode_id"] for row in raw_rows}, {1, 2})
        self.assertEqual({row["source_episode_id"] for row in verified_rows}, {2})
        self.assertTrue(
            all(row["source_episode_id"] < 3 for row in raw_rows + verified_rows)
        )
        self.assertEqual(
            set(raw_snapshot.retrievable_episode_ids),
            {row["record_id"] for row in raw_rows},
        )
        self.assertEqual(
            set(verified_snapshot.verified_episode_ids),
            {row["record_id"] for row in verified_rows},
        )


if __name__ == "__main__":
    unittest.main()
