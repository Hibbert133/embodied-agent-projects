import json
from types import SimpleNamespace
import unittest

from src.probemem_sciagent.agent_orchestrator import SciAgentCallBudget
from src.probemem_sciagent.api_reliability import ApiReliabilityClient, build_health_check_payload
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot


COMP = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


class FakeMessages:
    def __init__(self, values): self.values = iter(values); self.calls = 0
    def create(self, **kwargs):
        self.calls += 1
        value = next(self.values)
        if isinstance(value, Exception): raise value
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=value)],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )


def decision(mode="ACT_DIRECTLY", selected=COMP):
    return {
        "evidence_summary": "Agent-visible repeated response evidence.",
        "candidate_hypotheses": [f"Stable response may favor {COMP}", f"Variable response may favor {RETRY}"],
        "retrieved_principle_ids": [], "retrieved_experience_ids": [],
        "decision_mode": mode, "selected_probe_type": None, "selected_skill": selected,
        "expected_effect": "Use a registered bounded recovery.", "uncertainty_reason": "",
        "predicted_success_probability": 0.7, "stop_reason": None,
        "retrieved_hypothesis_ids": [], "tested_hypothesis_ids": [], "probe_justification_codes": [],
    }


def certified(evidence_id="current", mode="ACT_DIRECTLY", selected=COMP):
    action = decision(mode, selected)
    if mode == "ABSTAIN":
        action.update({"selected_skill": None, "predicted_success_probability": 0.0, "stop_reason": "insufficient evidence"})
    alternative = None if mode == "ABSTAIN" else (RETRY if selected == COMP else COMP)
    return {
        "decision": action,
        "certificate": {
            "decision_basis": "ABSTENTION_SAFETY" if mode == "ABSTAIN" else "CURRENT_DIRECT_EVIDENCE",
            "bound_decision_mode": mode, "bound_selected_skill": action["selected_skill"],
            "alternative_skill": alternative, "current_evidence_id": evidence_id,
            "supporting_evidence_ids": [evidence_id], "supporting_principle_ids": [],
            "supporting_experience_ids": [], "supporting_probe_record_ids": [],
            "grounding_claim": "INSUFFICIENT_EVIDENCE" if mode == "ABSTAIN" else "REPEATED_RESPONSE_SUPPORTS_COMPENSATION",
            "counterevidence_summary": "The alternative remains possible.",
        },
    }


class ApiReliabilityTest(unittest.TestCase):
    def setUp(self): self.snapshot = ScientificMemorySnapshot(1, (), (), (), ())

    def client(self, values, failures=2):
        messages = FakeMessages(values)
        return ApiReliabilityClient(
            client=SimpleNamespace(messages=messages),
            call_budget=SciAgentCallBudget(9, 1, 10),
            maximum_consecutive_failures=failures,
        ), messages

    def test_valid_certificate_binds_current_evidence(self):
        client, _ = self.client([json.dumps(certified())])
        result = client.certified_decide({}, snapshot=self.snapshot, current_evidence_id="current")
        self.assertTrue(result.valid)
        self.assertEqual(result.certified_decision.decision.selected_skill, COMP)

    def test_mismatched_decision_binding_fails_closed(self):
        value = certified(); value["certificate"]["bound_selected_skill"] = RETRY
        client, _ = self.client([json.dumps(value), json.dumps(value)])
        result = client.certified_decide({}, snapshot=self.snapshot, current_evidence_id="current")
        self.assertFalse(result.valid)
        self.assertEqual(result.fail_closed_decision.decision_mode, "ABSTAIN")

    def test_validated_identical_request_is_cached(self):
        client, messages = self.client([json.dumps(certified())])
        first = client.certified_decide({"x": 1}, snapshot=self.snapshot, current_evidence_id="current")
        second = client.certified_decide({"x": 1}, snapshot=self.snapshot, current_evidence_id="current")
        self.assertTrue(first.valid and second.cache_hit)
        self.assertEqual(messages.calls, 1)
        self.assertEqual(client.call_budget.total_calls, 1)

    def test_two_logical_failures_open_circuit_without_third_call(self):
        client, messages = self.client(["bad", "bad", "bad", "bad"])
        self.assertFalse(client.certified_decide({"case": 1}, snapshot=self.snapshot, current_evidence_id="current").valid)
        self.assertFalse(client.certified_decide({"case": 2}, snapshot=self.snapshot, current_evidence_id="current").valid)
        calls = messages.calls
        third = client.certified_decide({"case": 3}, snapshot=self.snapshot, current_evidence_id="current")
        self.assertEqual(third.error, "CIRCUIT_OPEN")
        self.assertEqual(messages.calls, calls)

    def test_health_check_requires_grounded_abstention(self):
        client, _ = self.client([json.dumps(certified("api_health_check_evidence", "ABSTAIN", None))])
        result = client.certified_decide(
            build_health_check_payload(), snapshot=self.snapshot,
            current_evidence_id="api_health_check_evidence",
        )
        self.assertTrue(result.valid)
        self.assertEqual(result.certified_decision.decision.decision_mode, "ABSTAIN")


if __name__ == "__main__": unittest.main()
