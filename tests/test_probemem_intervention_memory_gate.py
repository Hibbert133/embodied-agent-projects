"""Tests for frozen coverage-aware intervention memory semantics."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_probemem_paired_utility import validate_stopping_rule
from src.probemem.intervention_memory import VerifiedInterventionEpisode
from src.probemem.intervention_memory_gate import (
    CoverageAwareInterventionMemory,
    MemoryApplicabilityAction,
)
from src.probemem.intervention_utility import InterventionApplicabilitySignature
from src.probemem.models import InterventionSkill


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/probemem_v2/coverage_aware_memory_development_v1.json"


def record(index: int, skill: InterventionSkill, offset: float) -> VerifiedInterventionEpisode:
    return VerifiedInterventionEpisode(
        schema_version=1,
        record_id=f"record_{index}",
        source_episode_id=index,
        source_run_id="run",
        source_manifest_id="manifest",
        source_git_commit="commit",
        selection_policy_id="selector",
        applicability_signature=InterventionApplicabilitySignature(
            schema_version=1,
            evidence_id=f"evidence_{index}",
            episode_id=index,
            values=(offset,) * 13,
        ),
        selected_skill=skill,
        fresh_verification_status="ACCEPTED",
        final_object_goal_distance=0.04,
        verification_steps=100,
        total_interaction_steps=664,
    )


class ProbeMemInterventionMemoryGateTest(unittest.TestCase):
    def test_protocol_is_fresh_bounded_and_keeps_heldout_untouched(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(config["seed_range"], [980, 1059])
        self.assertEqual(config["heldout_seed_range"], [900, 979])
        self.assertEqual(validate_stopping_rule(config), 20)
        self.assertEqual(config["scope"]["api_calls"], 0)
        self.assertFalse(config["scope"]["phase_d_promotion"])

    def test_gate_requires_protocol_authorization(self) -> None:
        records = [record(i, InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY, i / 10) for i in range(1, 5)]
        with self.assertRaisesRegex(ValueError, "frozen protocol"):
            CoverageAwareInterventionMemory(records, neighbor_count=3)

    def test_budget_and_conflict_fail_closed(self) -> None:
        records = [
            record(1, InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY, 0.0),
            record(2, InterventionSkill.BOUNDED_PLANAR_COMPENSATION, 0.1),
            record(3, InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY, 0.2),
            record(4, InterventionSkill.BOUNDED_PLANAR_COMPENSATION, 0.3),
        ]
        memory = CoverageAwareInterventionMemory(
            records, neighbor_count=3, development_protocol_authorized=True
        )
        query = InterventionApplicabilitySignature(1, "query", 10, (0.15,) * 13)
        self.assertEqual(
            memory.decide(query, remaining_budget_steps=499).reason,
            "INSUFFICIENT_VERIFICATION_BUDGET",
        )
        self.assertEqual(
            memory.decide(query, remaining_budget_steps=500).reason,
            "CONFLICTING_VERIFIED_EPISODES",
        )

    def test_unanimous_in_coverage_support_can_use_memory(self) -> None:
        records = [
            record(i, InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY, i / 100)
            for i in range(1, 5)
        ]
        memory = CoverageAwareInterventionMemory(
            records, neighbor_count=3, development_protocol_authorized=True
        )
        query = InterventionApplicabilitySignature(1, "query", 10, (0.025,) * 13)
        decision = memory.decide(query, remaining_budget_steps=500)
        self.assertEqual(decision.action, MemoryApplicabilityAction.USE_VERIFIED_EPISODE)
        self.assertEqual(decision.selected_skill, InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY)


if __name__ == "__main__":
    unittest.main()
