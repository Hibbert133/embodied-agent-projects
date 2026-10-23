from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from src.probemem.models import (
    InterventionSkill,
    MemorySnapshot,
    ProbeMemDecision,
    ProbeMemTool,
)
from src.probemem.online_policy import AnthropicProbeMemPolicy, ApiCallBudget
from src.probemem.runtime import CaseBudget, ProbeMemState, ProbeMemStateMachine
from src.probemem.tools import build_default_tool_registry


def valid_decision(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "decision_id": "decision_1",
        "evidence_id": "evidence_1",
        "memory_snapshot_id": "empty_memory_before_episode_0001",
        "memory_used": False,
        "retrieved_principle_ids": [],
        "retrieved_episode_ids": [],
        "principle_applicable": False,
        "evidence_sufficient": True,
        "requested_tool": "select_intervention_skill",
        "mechanism_hypothesis": "stochastic_or_unstable_response",
        "selected_skill": "INDEPENDENT_STOCHASTIC_RETRY",
        "predicted_outcome": {
            "verification_status": "ACCEPTED",
            "expected_progress": 0.2,
            "expected_additional_steps": 300,
        },
        "reason": "response variance makes an independent retry appropriate",
        "confidence": "medium",
    }
    value.update(changes)
    return value


def valid_model_body(**changes: object) -> dict[str, object]:
    value = valid_decision()
    for field in ("schema_version", "decision_id", "evidence_id", "memory_snapshot_id"):
        value.pop(field)
    value.update(changes)
    return value


class FakeMessages:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.requests.append(kwargs)
        text = self.responses.pop(0)
        return SimpleNamespace(
            id="response_1",
            model="glm-5.2",
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=100, output_tokens=40),
        )


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.messages = FakeMessages(responses)


class ProbeMemContractsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = MemorySnapshot.empty_for_episode(1)
        self.registry = build_default_tool_registry()

    def test_exact_schema_and_empty_memory_provenance(self) -> None:
        decision = ProbeMemDecision.from_mapping(valid_decision())
        decision.validate_context(
            evidence_id="evidence_1",
            snapshot=self.snapshot,
            allowed_tools=self.registry.decision_tools(probe_available=False),
            allowed_skills=self.registry.available_skills(probe_collected=False),
        )
        extra = valid_decision(extra_oracle_label="fault_01")
        with self.assertRaisesRegex(ValueError, "exactly"):
            ProbeMemDecision.from_mapping(extra)

    def test_rejects_nested_oracle_evidence_before_api_call(self) -> None:
        client = FakeClient([json.dumps(valid_model_body())])
        policy = AnthropicProbeMemPolicy(client=client)
        with self.assertRaisesRegex(ValueError, "Oracle-only"):
            policy.decide(
                decision_id="decision_1",
                evidence={"evidence_id": "evidence_1", "nested": {"condition_id": "fault_01"}},
                memory_snapshot=self.snapshot,
                allowed_tools=self.registry.decision_tools(probe_available=True),
                allowed_skills=self.registry.available_skills(probe_collected=False),
                remaining_environment_steps=564,
                call_budget=ApiCallBudget(2),
            )
        self.assertEqual(client.messages.requests, [])

    def test_memory_ids_must_come_from_snapshot(self) -> None:
        payload = valid_decision(
            memory_used=True,
            retrieved_principle_ids=["future_principle"],
        )
        decision = ProbeMemDecision.from_mapping(payload)
        with self.assertRaisesRegex(ValueError, "outside"):
            decision.validate_context(
                evidence_id="evidence_1",
                snapshot=self.snapshot,
                allowed_tools=self.registry.decision_tools(probe_available=True),
                allowed_skills=self.registry.available_skills(probe_collected=False),
            )

    def test_budget_reserves_fresh_verification_and_limits_probe(self) -> None:
        budget = CaseBudget().with_initial(500)
        self.assertTrue(budget.can_request_probe())
        budget = budget.with_probe(64)
        self.assertFalse(budget.can_request_probe())
        budget = budget.with_verification(500)
        self.assertEqual(budget.remaining_steps, 0)
        with self.assertRaisesRegex(ValueError, "at most one"):
            budget.with_verification(1)

    def test_probe_skill_only_available_after_probe(self) -> None:
        before = self.registry.available_skills(probe_collected=False)
        after = self.registry.available_skills(probe_collected=True)
        self.assertNotIn(InterventionSkill.BOUNDED_PLANAR_COMPENSATION, before)
        self.assertIn(InterventionSkill.BOUNDED_PLANAR_COMPENSATION, after)

    def test_invalid_output_repairs_once_then_fails_closed(self) -> None:
        client = FakeClient(["not json", "still not json"])
        policy = AnthropicProbeMemPolicy(client=client)
        budget = ApiCallBudget(2)
        decision, audit = policy.decide(
            decision_id="decision_1",
            evidence={"evidence_id": "evidence_1", "response_variance": 0.3},
            memory_snapshot=self.snapshot,
            allowed_tools=self.registry.decision_tools(probe_available=True),
            allowed_skills=self.registry.available_skills(probe_collected=False),
            remaining_environment_steps=564,
            call_budget=budget,
        )
        self.assertIs(decision.requested_tool, ProbeMemTool.ABSTAIN)
        self.assertEqual(audit["status"], "fail_closed")
        self.assertEqual(budget.calls_used, 2)
        self.assertEqual(audit["attempts"][0]["raw_response"], "not json")
        self.assertIn("conditional_rules", audit["request_payload"])

    def test_valid_online_decision_contains_no_oracle_payload(self) -> None:
        client = FakeClient([json.dumps(valid_model_body())])
        policy = AnthropicProbeMemPolicy(client=client)
        decision, audit = policy.decide(
            decision_id="decision_1",
            evidence={"evidence_id": "evidence_1", "response_variance": 0.3},
            memory_snapshot=self.snapshot,
            allowed_tools=self.registry.decision_tools(probe_available=True),
            allowed_skills=self.registry.available_skills(probe_collected=False),
            remaining_environment_steps=564,
            call_budget=ApiCallBudget(2),
        )
        self.assertIs(decision.selected_skill, InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY)
        request = client.messages.requests[0]
        serialized = json.dumps(request["messages"])
        self.assertNotIn("condition_id", serialized)
        self.assertNotIn("perturbation", serialized)
        self.assertEqual(audit["status"], "valid")
        self.assertNotIn("api_key", json.dumps(audit))

    def test_host_adds_provenance_envelope_to_model_body(self) -> None:
        client = FakeClient([json.dumps(valid_model_body())])
        policy = AnthropicProbeMemPolicy(client=client)
        decision, audit = policy.decide(
            decision_id="decision_1",
            evidence={"evidence_id": "evidence_1", "response_variance": 0.3},
            memory_snapshot=self.snapshot,
            allowed_tools=self.registry.decision_tools(probe_available=False),
            allowed_skills=self.registry.available_skills(probe_collected=False),
            remaining_environment_steps=564,
            call_budget=ApiCallBudget(1),
        )
        self.assertEqual(decision.schema_version, 1)
        self.assertEqual(decision.decision_id, "decision_1")
        self.assertEqual(decision.evidence_id, "evidence_1")
        body = json.loads(client.messages.requests[0]["messages"][0]["content"])
        self.assertIn("host_owned_envelope", body)
        self.assertNotIn("schema_version", body["response_schema"])
        self.assertEqual(
            body["valid_response_example"]["predicted_outcome"]["verification_status"],
            "ACCEPTED",
        )
        self.assertEqual(audit["status"], "valid")

    def test_state_machine_rejects_skipped_evidence(self) -> None:
        machine = ProbeMemStateMachine()
        with self.assertRaisesRegex(ValueError, "invalid ProbeMem transition"):
            machine.advance(ProbeMemState.LLM_DECISION)

    def test_online_policy_rejects_memory_records_outside_snapshot(self) -> None:
        client = FakeClient([json.dumps(valid_model_body())])
        policy = AnthropicProbeMemPolicy(client=client)
        with self.assertRaisesRegex(ValueError, "differ from the memory snapshot"):
            policy.decide(
                decision_id="decision_1",
                evidence={"evidence_id": "evidence_1"},
                memory_snapshot=self.snapshot,
                allowed_tools=self.registry.decision_tools(probe_available=False),
                allowed_skills=self.registry.available_skills(probe_collected=False),
                remaining_environment_steps=500,
                call_budget=ApiCallBudget(1),
                retrieved_episode_records=[{"record_id": "future_record"}],
            )
        self.assertEqual(client.messages.requests, [])


if __name__ == "__main__":
    unittest.main()
