import json
import unittest
from types import SimpleNamespace

from src.probemem_sciagent.agent_orchestrator import SciAgentCallBudget, SciAgentGlmClient
from src.probemem_sciagent.decision_validator import validate_decision_mapping
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.schemas import SciAgentDecision


COMP = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


def mapping():
    return {
        "evidence_summary": "summary", "candidate_hypotheses": [f"A {COMP}", f"B {RETRY}"],
        "retrieved_principle_ids": [], "retrieved_experience_ids": [],
        "decision_mode": "ACT_DIRECTLY", "selected_probe_type": None, "selected_skill": RETRY,
        "expected_effect": "independent realization", "uncertainty_reason": "", "predicted_success_probability": 0.7,
        "stop_reason": None, "retrieved_hypothesis_ids": [], "tested_hypothesis_ids": [], "probe_justification_codes": [],
    }


class FakeMessages:
    def __init__(self, texts): self.texts = iter(texts)
    def create(self, **kwargs):
        text = next(self.texts)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], usage=SimpleNamespace(input_tokens=10, output_tokens=5))


class SciAgentDecisionTest(unittest.TestCase):
    def setUp(self): self.snapshot = ScientificMemorySnapshot(1, (), (), (), ())

    def test_unknown_principle_id_is_rejected(self):
        value = mapping(); value["retrieved_principle_ids"] = ["future"]
        with self.assertRaises(ValueError): validate_decision_mapping(value, snapshot=self.snapshot, stage="PRE_PROBE")

    def test_continuous_action_field_is_rejected(self):
        value = mapping(); value["continuous_action"] = [1, 0, 0, 0]
        with self.assertRaises(ValueError): validate_decision_mapping(value, snapshot=self.snapshot, stage="PRE_PROBE")

    def test_invalid_json_fails_closed_after_one_repair(self):
        fake = SimpleNamespace(messages=FakeMessages(["not json", "still not json"]))
        client = SciAgentGlmClient(client=fake, call_budget=SciAgentCallBudget(1, 1, 2))
        result = client.decide({}, snapshot=self.snapshot, stage="PRE_PROBE")
        self.assertEqual(result.decision_mode, "ABSTAIN")
        self.assertEqual(client.call_budget.total_calls, 2)

    def test_valid_structured_output_is_accepted(self):
        fake = SimpleNamespace(messages=FakeMessages([json.dumps(mapping())]))
        client = SciAgentGlmClient(client=fake)
        result = client.decide({}, snapshot=self.snapshot, stage="PRE_PROBE")
        self.assertEqual(result.selected_skill, RETRY)

    def test_primary_budget_exhaustion_does_not_spend_repair(self):
        fake = SimpleNamespace(messages=FakeMessages([json.dumps(mapping())]))
        budget = SciAgentCallBudget(0, 1, 1)
        client = SciAgentGlmClient(client=fake, call_budget=budget)
        result = client.decide({}, snapshot=self.snapshot, stage="PRE_PROBE")
        self.assertEqual(result.decision_mode, "ABSTAIN")
        self.assertEqual(budget.repair_calls, 0)

    def test_post_probe_cannot_request_another_probe(self):
        value = mapping(); value.update({
            "decision_mode": "RUN_MICRO_PROBE", "selected_probe_type": "RETRY_REPEATABILITY_PROBE",
            "probe_justification_codes": ["MISSING_ACTION_CONDITIONED_EVIDENCE"], "uncertainty_reason": "missing",
        })
        with self.assertRaises(ValueError): validate_decision_mapping(value, snapshot=self.snapshot, stage="POST_PROBE")


if __name__ == "__main__": unittest.main()
