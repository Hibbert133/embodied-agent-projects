from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

from src.online_planar_agent import (
    AnthropicPlanarRecoveryAgent, PlanarAgentDecision, validate_planar_decision,
)
from src.trajectory_views import FORBIDDEN_AGENT_FIELDS


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(nested_keys(x) for x in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(nested_keys(x) for x in value))
    return set()


class FakeMessages:
    def __init__(self, decision: dict[str, object]) -> None:
        self.decision = decision
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(
            id="msg_planar", model="glm-test", content=[
                SimpleNamespace(type="text", text=json.dumps(self.decision))
            ], usage=SimpleNamespace(input_tokens=30, output_tokens=20),
        )


class OnlinePlanarAgentTest(unittest.TestCase):
    def test_mode_and_grid_validation(self) -> None:
        valid = PlanarAgentDecision(
            "simultaneous", -0.1, 0.18, "whole", "visible drift", "reduce drift", 0.8
        )
        self.assertEqual(validate_planar_decision(valid), valid)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_planar_decision(PlanarAgentDecision(
                "dominant_only", -0.1, 0.18, "whole", "h", "e", 0.5
            ))
        with self.assertRaisesRegex(ValueError, "allowed signed grid"):
            validate_planar_decision(PlanarAgentDecision(
                "simultaneous", -0.101, 0.18, "whole", "h", "e", 0.5
            ))

    def test_adapter_sends_only_supplied_agent_evidence(self) -> None:
        response = {
            "repair_mode": "simultaneous", "correction_x": -0.1,
            "correction_y": 0.18, "correction_schedule": "whole",
            "hypothesis": "Both visible drift components are nonzero.",
            "expected_effect": "Reduce final object-goal distance.",
            "confidence": 0.8, "stop": False,
        }
        messages = FakeMessages(response)
        agent = AnthropicPlanarRecoveryAgent(
            model="glm-test", base_url="https://example.invalid/anthropic",
            client=SimpleNamespace(messages=messages),
        )
        decision, audit = agent.decide(
            episode_evidence={"success": False, "final_object_goal_distance": 0.2},
            diagnostic_context={"inference": {"estimated_drift_per_step": [0.1, -0.1]}},
            remaining_rollouts=1,
        )
        self.assertEqual(decision.repair_mode, "simultaneous")
        payload = json.loads(str(messages.kwargs["messages"][0]["content"]))
        self.assertFalse(FORBIDDEN_AGENT_FIELDS & nested_keys(payload))
        self.assertNotIn("ANTHROPIC_API_KEY", str(payload))
        self.assertEqual(audit["response_id"], "msg_planar")

        with self.assertRaisesRegex(ValueError, "forbidden fields"):
            agent.decide(
                episode_evidence={"success": False, "injected_bias": [0.1, -0.1]},
                diagnostic_context={"inference": {}}, remaining_rollouts=1,
            )


if __name__ == "__main__":
    unittest.main()
