from __future__ import annotations

import json
from types import SimpleNamespace
import unittest

import numpy as np

from src.recovery_skills import build_planar_recovery_skills, select_skill
from src.skill_grounded_agent import AnthropicSkillGroundedAgent
from src.trajectory_views import FORBIDDEN_AGENT_FIELDS


def context() -> dict[str, object]:
    return {
        "probe_environment_steps": 32,
        "inference": {
            "estimated_drift_per_step": (0.00056, -0.00099),
            "axis_response_gain": (0.0061, 0.0057),
            "residual": 0.000001,
        },
    }


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(nested_keys(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(nested_keys(item) for item in value))
    return set()


class FakeMessages:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        decision = {
            "skill_id": "simultaneous_xy_repair",
            "correction_schedule": "whole",
            "hypothesis": "Both estimated planar components are material.",
            "expected_effect": "Reduce object-goal distance in one rollout.",
            "verification_condition": "success or final distance below 0.05",
            "confidence": 0.8,
            "stop": False,
        }
        return SimpleNamespace(
            id="msg_skill", model="glm-test",
            content=[SimpleNamespace(type="text", text=json.dumps(decision))],
            usage=SimpleNamespace(input_tokens=20, output_tokens=10),
        )


class RecoverySkillsTest(unittest.TestCase):
    def test_registry_exposes_grounded_dominant_and_simultaneous_repairs(self) -> None:
        diagnosis, skills = build_planar_recovery_skills(context())
        self.assertEqual(len(skills), 2)
        dominant = select_skill(skills, "dominant_axis_repair")
        simultaneous = select_skill(skills, "simultaneous_xy_repair")
        self.assertEqual(np.count_nonzero(dominant.correction[:2]), 1)
        self.assertEqual(np.count_nonzero(simultaneous.correction[:2]), 2)
        np.testing.assert_allclose(simultaneous.correction, (-0.1, 0.18, 0.0, 0.0))
        self.assertNotIn("dominant_axis", diagnosis)

    def test_online_agent_selects_exact_skill_without_oracle_payload(self) -> None:
        diagnosis, skills = build_planar_recovery_skills(context())
        messages = FakeMessages()
        agent = AnthropicSkillGroundedAgent(
            model="glm-test", base_url="https://example.invalid/anthropic",
            client=SimpleNamespace(messages=messages),
        )
        decision, audit = agent.decide(
            episode_evidence={"success": False, "final_object_goal_distance": 0.2},
            structured_diagnosis=diagnosis, skills=skills, remaining_rollouts=1,
        )
        self.assertEqual(decision.skill_id, "simultaneous_xy_repair")
        payload = json.loads(str(messages.kwargs["messages"][0]["content"]))
        self.assertFalse(FORBIDDEN_AGENT_FIELDS & nested_keys(payload))
        self.assertNotIn("injected_bias", str(payload))
        self.assertEqual(audit["response_id"], "msg_skill")


if __name__ == "__main__":
    unittest.main()
