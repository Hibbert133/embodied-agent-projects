"""Tests for the chronological ProbeMem-Online decision boundary."""

from __future__ import annotations

import unittest

from src.probemem.memory_tools import retrieve_action_memory_payload
from src.probemem.models import InterventionSkill
from src.probemem.online_memory_policy import OnlineMemoryDecision, OnlineMemoryGlmPolicy, build_online_memory_payload
from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionExperience, RegimeActionMemory


def _signature(episode: int) -> ProbeRegimeSignature:
    return ProbeRegimeSignature(1, f"e{episode}", episode, (0.1, 0.0, 0.1, 0.02, 0.9, 0.1, 0.3, 0.12))


def _memory() -> RegimeActionMemory:
    return RegimeActionMemory((RegimeActionExperience(
        1, "r1", 1, 2, _signature(1), InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
        "ACCEPTED", 0.8, "ACCEPTED", 0.2, 0.04, 200, "run", "manifest", "ONLINE_SELECTED_ACTION",
    ),))


def _decision() -> dict:
    prediction = {"predicted_status": "ACCEPTED", "accept_probability": 0.8, "confidence": 0.7}
    return {
        "evidence_interpretation": {"persistent_directional_drift": True, "high_response_variance": False, "evidence_sufficient": True},
        "action_predictions": {
            "BOUNDED_PLANAR_COMPENSATION": prediction,
            "INDEPENDENT_STOCHASTIC_RETRY": {**prediction, "accept_probability": 0.3},
        },
        "memory_used": True,
        "supporting_memory_ids": ["r1"],
        "contradicting_memory_ids": [],
        "memory_applicable": True,
        "memory_conflict_detected": False,
        "selected_skill": "BOUNDED_PLANAR_COMPENSATION",
        "abstain": False,
        "reason": "Earlier compensation evidence supports this bounded skill.",
    }


class ProbeMemOnlinePolicyTest(unittest.TestCase):
    def test_payload_uses_only_prior_action_specific_memory(self) -> None:
        memory = _memory()
        query = _signature(2)
        summaries = retrieve_action_memory_payload(memory, query, created_before_episode_id=2)
        payload = build_online_memory_payload(
            compact_evidence={"episode_id": 2, "evidence_id": "e2"},
            memory_payload=summaries, memory=memory, episode_id=2,
        )
        self.assertTrue(payload["host_constraints"]["memory_write_allowed_only_after_verification"])
        self.assertNotIn("condition_id", str(payload).lower())

    def test_unknown_or_future_memory_id_fails_closed(self) -> None:
        value = _decision()
        value["supporting_memory_ids"] = ["future"]
        with self.assertRaisesRegex(ValueError, "future memory"):
            OnlineMemoryDecision.from_mapping(value, allowed_memory_ids={"r1"})

    def test_both_actions_must_be_predicted_and_no_continuous_action_exists(self) -> None:
        decision = OnlineMemoryDecision.from_mapping(_decision(), allowed_memory_ids={"r1"})
        self.assertEqual(decision.selected_skill, "BOUNDED_PLANAR_COMPENSATION")
        self.assertNotIn("action", decision.to_dict())
        broken = _decision()
        broken["action_predictions"].pop("INDEPENDENT_STOCHASTIC_RETRY")
        with self.assertRaisesRegex(ValueError, "both and only"):
            OnlineMemoryDecision.from_mapping(broken, allowed_memory_ids={"r1"})

    def test_abstain_never_selects_or_executes_a_skill(self) -> None:
        value = _decision()
        value.update({"selected_skill": None, "abstain": True, "memory_used": False,
                      "supporting_memory_ids": [], "memory_applicable": False})
        value["evidence_interpretation"]["evidence_sufficient"] = False
        decision = OnlineMemoryDecision.from_mapping(value, allowed_memory_ids={"r1"})
        self.assertTrue(decision.abstain)
        self.assertIsNone(decision.selected_skill)

    def test_oracle_field_in_payload_is_rejected(self) -> None:
        memory = _memory()
        summaries = retrieve_action_memory_payload(memory, _signature(2), created_before_episode_id=2)
        with self.assertRaises((TypeError, ValueError)):
            build_online_memory_payload(
                compact_evidence={"episode_id": 2, "condition_id": "noise"},
                memory_payload=summaries, memory=memory, episode_id=2,
            )

    def test_invalid_model_output_fails_closed_without_skill_execution(self) -> None:
        class Messages:
            def create(self, **kwargs):
                return type("Response", (), {"content": [type("Block", (), {"type": "text", "text": "not json"})()], "usage": None})()
        client = type("Client", (), {"messages": Messages()})()
        decision, audit = OnlineMemoryGlmPolicy(client=client).request_once(
            {"schema_version": 1, "episode_id": 2}, allowed_memory_ids=set(),
        )
        self.assertIsNone(decision)
        self.assertFalse(audit["valid"])


if __name__ == "__main__":
    unittest.main()
