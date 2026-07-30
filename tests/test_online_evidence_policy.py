from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from src.reasoning import EvidencePacket, EvidenceSource
from src.uncertainty import AnthropicEvidencePolicy, EvidenceAction


class FakeMessages:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.request: dict[str, object] | None = None

    def create(self, **kwargs: object) -> object:
        self.request = kwargs
        return SimpleNamespace(
            id="response_1",
            model="glm-5.2",
            content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
            usage=SimpleNamespace(input_tokens=100, output_tokens=40),
        )


class FakeClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.messages = FakeMessages(payload)


def valid_payload() -> dict[str, object]:
    return {
        "action": "request_probe",
        "probe_kind": "symmetric_xy",
        "target_uncertainty": "planar drift estimate has high residual",
        "hypothesis_mechanism": "insufficient_evidence",
        "hypothesis_axis": "x",
        "hypothesis_direction": "positive",
        "rationale": "paired actions can distinguish drift from task motion",
        "confidence": 0.72,
    }


class OnlineEvidencePolicyTest(unittest.TestCase):
    def test_sends_only_agent_visible_evidence_and_parses_decision(self) -> None:
        client = FakeClient(valid_payload())
        policy = AnthropicEvidencePolicy(client=client)
        evidence = EvidencePacket(
            "failure_148", EvidenceSource.FAILED_ROLLOUT, 1, 500,
            {"uncertainty": 0.84, "passive_axis": "x"},
        )
        decision, audit = policy.decide(evidence, available_probe_steps=32)
        self.assertIs(decision.action, EvidenceAction.REQUEST_PROBE)
        request = client.messages.request
        self.assertIsNotNone(request)
        body = json.loads(request["messages"][0]["content"])  # type: ignore[index]
        serialized = json.dumps(body)
        self.assertNotIn("perturbation", serialized)
        self.assertNotIn("injected_bias", serialized)
        self.assertEqual(audit["model"], "glm-5.2")
        self.assertNotIn("response_text", audit)

    def test_rejects_probe_for_non_probe_action(self) -> None:
        payload = valid_payload()
        payload["action"] = "update_hypothesis"
        client = FakeClient(payload)
        policy = AnthropicEvidencePolicy(client=client)
        evidence = EvidencePacket(
            "failure_1", EvidenceSource.FAILED_ROLLOUT, 1, 20, {"uncertainty": 0.2}
        )
        with self.assertRaisesRegex(RuntimeError, "only request_probe"):
            policy.decide(evidence, available_probe_steps=32)

    def test_evidence_packet_rejects_oracle_truth_before_request(self) -> None:
        client = FakeClient(valid_payload())
        with self.assertRaisesRegex(ValueError, "Oracle-only"):
            EvidencePacket(
                "failure_1", EvidenceSource.FAILED_ROLLOUT, 1, 20,
                {"injected_bias_axis": "x"},
            )
        self.assertIsNone(client.messages.request)


if __name__ == "__main__":
    unittest.main()
