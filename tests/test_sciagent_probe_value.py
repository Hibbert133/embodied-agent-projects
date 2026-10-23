import json
from types import SimpleNamespace
import unittest

from src.probemem_sciagent.agent_orchestrator import SciAgentCallBudget
from src.probemem_sciagent.api_envelope import EnvelopeTolerantApiReliabilityClient
from src.probemem_sciagent.capability_contract import build_capability_contract
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.probe_value import (
    attach_probe_value_contract,
    validate_probe_value_certificate,
)
from tests.test_sciagent_api_reliability import FakeMessages, certified
from tests.test_sciagent_capability_contract import _tokenize


class SciAgentProbeValueTest(unittest.TestCase):
    def setUp(self):
        self.capability = build_capability_contract(
            snapshot=ScientificMemorySnapshot(1, (), (), (), ()),
            current_evidence_id="current",
        ).to_payload()
        self.contract = attach_probe_value_contract(
            {"capability_contract": self.capability}
        )["probe_value_contract"]

    def test_compensation_probe_is_admitted_when_value_exceeds_cost(self):
        assessment = validate_probe_value_certificate(
            self._certificate("COMPENSATION_RESPONSE_PROBE", gain=0.25),
            decision=self._decision("COMPENSATION_RESPONSE_PROBE"),
            capability_contract=self.capability, probe_value_contract=self.contract,
        )
        self.assertTrue(assessment.admitted)
        self.assertAlmostEqual(assessment.expected_value_gain, 0.25)
        self.assertAlmostEqual(assessment.decision_change_probability, 0.5)

    def test_retry_probe_is_rejected_when_value_is_below_larger_cost(self):
        assessment = validate_probe_value_certificate(
            self._certificate("RETRY_REPEATABILITY_PROBE", gain=0.10),
            decision=self._decision("RETRY_REPEATABILITY_PROBE"),
            capability_contract=self.capability, probe_value_contract=self.contract,
        )
        self.assertFalse(assessment.admitted)
        self.assertIn("EXPECTED_VALUE_NOT_ABOVE_NORMALIZED_COST", assessment.rejection_reasons)

    def test_no_decision_change_is_rejected(self):
        value = self._certificate("COMPENSATION_RESPONSE_PROBE", gain=0.05)
        for branch in value["outcome_branches"]:
            branch["final_skill_token"] = "SKILL_0"
            branch["candidates"] = self._candidates(0.60, 0.40)
        value["claimed_expected_value_gain"] = 0.05
        assessment = validate_probe_value_certificate(
            value, decision=self._decision("COMPENSATION_RESPONSE_PROBE"),
            capability_contract=self.capability, probe_value_contract=self.contract,
        )
        self.assertFalse(assessment.admitted)
        self.assertIn("NO_COUNTERFACTUAL_DECISION_CHANGE", assessment.rejection_reasons)

    def test_branch_probabilities_must_sum_to_one(self):
        value = self._certificate("COMPENSATION_RESPONSE_PROBE", gain=0.25)
        value["outcome_branches"][1]["branch_probability"] = 0.4
        with self.assertRaisesRegex(ValueError, "sum to one"):
            self._validate(value, "COMPENSATION_RESPONSE_PROBE")

    def test_claimed_gain_is_recomputed(self):
        value = self._certificate("COMPENSATION_RESPONSE_PROBE", gain=0.25)
        value["claimed_expected_value_gain"] = 0.4
        with self.assertRaisesRegex(ValueError, "does not match"):
            self._validate(value, "COMPENSATION_RESPONSE_PROBE")

    def test_final_skill_must_be_branch_argmax(self):
        value = self._certificate("COMPENSATION_RESPONSE_PROBE", gain=0.25)
        value["outcome_branches"][0]["final_skill_token"] = "SKILL_1"
        with self.assertRaisesRegex(ValueError, "not candidate argmax"):
            self._validate(value, "COMPENSATION_RESPONSE_PROBE")

    def test_outcomes_must_match_selected_probe(self):
        value = self._certificate("COMPENSATION_RESPONSE_PROBE", gain=0.25)
        value["outcome_branches"][0]["outcome_token"] = "OUTCOME_RETRY_REPEATABLE"
        with self.assertRaisesRegex(ValueError, "registered outcomes"):
            self._validate(value, "COMPENSATION_RESPONSE_PROBE")

    def test_envelope_validates_evsi_before_existing_semantics(self):
        canonical = certified("current")
        canonical["decision"].update({
            "decision_mode": "RUN_MICRO_PROBE",
            "selected_probe_type": "COMPENSATION_RESPONSE_PROBE",
            "selected_skill": "BOUNDED_PLANAR_COMPENSATION",
            "uncertainty_reason": "Action-conditioned evidence is missing.",
            "predicted_success_probability": 0.55,
            "probe_justification_codes": ["MISSING_ACTION_CONDITIONED_EVIDENCE"],
        })
        canonical["certificate"].update({
            "bound_decision_mode": "RUN_MICRO_PROBE",
            "bound_selected_skill": "BOUNDED_PLANAR_COMPENSATION",
            "grounding_claim": "ACTION_UTILITY_UNCERTAIN",
        })
        tokenized = _tokenize(canonical, self.capability["namespaces"])
        tokenized["probe_value_certificate"] = self._certificate(
            "COMPENSATION_RESPONSE_PROBE", gain=0.25,
        )
        messages = FakeMessages([json.dumps(tokenized)])
        client = EnvelopeTolerantApiReliabilityClient(
            client=SimpleNamespace(messages=messages),
            call_budget=SciAgentCallBudget(9, 1, 10),
        )
        request = attach_probe_value_contract({"capability_contract": self.capability})
        result = client.certified_decide(
            request, snapshot=ScientificMemorySnapshot(1, (), (), (), ()),
            current_evidence_id="current",
        )
        self.assertTrue(result.valid)
        self.assertTrue(client.audit[0]["valid_probe_value_certificate"])
        self.assertTrue(client.audit[0]["probe_value_assessment"]["admitted"])

    def _validate(self, value, probe):
        return validate_probe_value_certificate(
            value, decision=self._decision(probe),
            capability_contract=self.capability, probe_value_contract=self.contract,
        )

    @staticmethod
    def _decision(probe):
        return {
            "decision_mode": "RUN_MICRO_PROBE",
            "selected_probe_type": probe,
            "selected_skill": "BOUNDED_PLANAR_COMPENSATION",
        }

    def _certificate(self, probe, *, gain):
        outcome_tokens = (
            ("OUTCOME_COMP_ALIGNED", "OUTCOME_COMP_NOT_ALIGNED")
            if probe == "COMPENSATION_RESPONSE_PROBE"
            else ("OUTCOME_RETRY_REPEATABLE", "OUTCOME_RETRY_NOT_REPEATABLE")
        )
        high = 0.55 + gain
        return {
            "selected_probe_token": "PROBE_0" if probe == "COMPENSATION_RESPONSE_PROBE" else "PROBE_1",
            "current_candidates": self._candidates(0.55, 0.45),
            "outcome_branches": [
                {"outcome_token": outcome_tokens[0], "branch_probability": 0.5,
                 "final_skill_token": "SKILL_0", "candidates": self._candidates(high, 1.0 - high)},
                {"outcome_token": outcome_tokens[1], "branch_probability": 0.5,
                 "final_skill_token": "SKILL_1", "candidates": self._candidates(1.0 - high, high)},
            ],
            "claimed_expected_value_gain": gain,
        }

    @staticmethod
    def _candidates(compensation, retry):
        return [
            {"skill_token": "SKILL_0", "success_probability": compensation},
            {"skill_token": "SKILL_1", "success_probability": retry},
        ]


if __name__ == "__main__":
    unittest.main()
