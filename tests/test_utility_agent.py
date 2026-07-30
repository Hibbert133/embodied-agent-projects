import json
from types import SimpleNamespace
import unittest

from src.utility_agent import AnthropicUtilityAgent


class Messages:
    def create(self, **kwargs):
        self.kwargs = kwargs
        value = {
            "candidate_id": "compensation",
            "hypothesis": "the compensation probe made more progress",
            "expected_effect": "lower final object-goal distance",
            "verification_condition": "success or lower final distance",
            "confidence": 0.8,
        }
        return SimpleNamespace(
            id="mock",
            model="mock",
            content=[SimpleNamespace(type="text", text=json.dumps(value))],
            usage=SimpleNamespace(input_tokens=1, output_tokens=2),
        )


class UtilityAgentTest(unittest.TestCase):
    def test_selects_exact_candidate_without_oracle_payload(self):
        messages = Messages()
        agent = AnthropicUtilityAgent(client=SimpleNamespace(messages=messages))
        candidates = [
            {"candidate_id": "compensation", "strategy": "bounded repair"},
            {"candidate_id": "retry", "strategy": "fresh retry"},
        ]
        probes = [
            {"candidate_id": "compensation", "final_object_goal_distance": 0.1},
            {"candidate_id": "retry", "final_object_goal_distance": 0.2},
        ]
        decision, audit = agent.decide(
            episode_evidence={"case_id": "c1"},
            structured_diagnosis={"estimated_action_bias": [0.1, 0.0]},
            candidates=candidates,
            candidate_probe_evidence=probes,
        )
        self.assertEqual(decision.candidate_id, "compensation")
        self.assertEqual(audit["usage"]["output_tokens"], 2)
        payload = json.loads(messages.kwargs["messages"][0]["content"])
        self.assertNotIn("perturbation_type", str(payload))

    def test_unknown_candidate_fails_closed(self):
        messages = Messages()
        messages.create = lambda **kwargs: SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text=(
                        '{"candidate_id":"invented","hypothesis":"h",'
                        '"expected_effect":"e","verification_condition":"v",'
                        '"confidence":0.5}'
                    ),
                )
            ]
        )
        agent = AnthropicUtilityAgent(client=SimpleNamespace(messages=messages))
        with self.assertRaisesRegex(RuntimeError, "candidate_id"):
            agent.decide(
                episode_evidence={"case_id": "c"},
                structured_diagnosis={},
                candidates=[{"candidate_id": "a"}, {"candidate_id": "b"}],
                candidate_probe_evidence=[
                    {"candidate_id": "a"},
                    {"candidate_id": "b"},
                ],
            )

    def test_oracle_field_is_rejected_before_request(self):
        messages = Messages()
        agent = AnthropicUtilityAgent(client=SimpleNamespace(messages=messages))
        with self.assertRaisesRegex(ValueError, "forbidden"):
            agent.decide(
                episode_evidence={"case_id": "c", "perturbation_type": "bias"},
                structured_diagnosis={},
                candidates=[{"candidate_id": "a"}, {"candidate_id": "b"}],
                candidate_probe_evidence=[
                    {"candidate_id": "a"},
                    {"candidate_id": "b"},
                ],
            )


if __name__ == "__main__":
    unittest.main()
