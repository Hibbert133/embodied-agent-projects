import json
from types import SimpleNamespace
import unittest

from src.probemem_sciagent.agent_orchestrator import SciAgentCallBudget
from src.probemem_sciagent.api_envelope import EnvelopeTolerantApiReliabilityClient
from src.probemem_sciagent.capability_contract import build_capability_contract
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.quantized_probe_value import (
    PROBABILITY_TOKENS,
    attach_quantized_probe_value_contract,
    validate_quantized_probe_value_certificate,
)
from tests.test_sciagent_api_reliability import FakeMessages, certified
from tests.test_sciagent_capability_contract import _tokenize


class SciAgentQuantizedProbeValueTest(unittest.TestCase):
    def setUp(self):
        self.capability = build_capability_contract(
            snapshot=ScientificMemorySnapshot(1, (), (), (), ()),
            current_evidence_id="current",
        ).to_payload()
        self.contract = attach_quantized_probe_value_contract(
            {"capability_contract": self.capability}
        )["probe_value_contract"]

    def test_probability_language_is_complete_five_percent_lattice(self):
        self.assertEqual(len(PROBABILITY_TOKENS), 21)
        self.assertEqual(PROBABILITY_TOKENS["P_00"], 0.0)
        self.assertEqual(PROBABILITY_TOKENS["P_20"], 1.0)

    def test_host_derives_admitted_compensation_probe(self):
        assessment = self._validate(self._certificate("PROBE_0"), self._decision())
        self.assertTrue(assessment.admitted)
        self.assertAlmostEqual(assessment.expected_value_gain, 0.25)
        self.assertAlmostEqual(assessment.decision_change_probability, 0.5)

    def test_non_probe_decision_requires_null_certificate(self):
        direct = self._decision(mode="ACT_DIRECTLY", probe=None)
        assessment = self._validate(None, direct)
        self.assertFalse(assessment.admitted)
        self.assertEqual(assessment.rejection_reasons, ("AGENT_DID_NOT_REQUEST_PROBE",))
        with self.assertRaisesRegex(ValueError, "requires null"):
            self._validate({}, direct)

    def test_current_selected_probability_cannot_trail_alternative(self):
        value = self._certificate("PROBE_0")
        value["current_selected_probability_token"] = "P_08"
        value["current_alternative_probability_token"] = "P_12"
        with self.assertRaisesRegex(ValueError, "below alternative"):
            self._validate(value, self._decision())

    def test_unknown_probability_token_fails_closed(self):
        value = self._certificate("PROBE_0")
        value["current_selected_probability_token"] = "P_11_5"
        with self.assertRaisesRegex(ValueError, "unknown quantized"):
            self._validate(value, self._decision())

    def test_host_rejects_low_value_retry_probe(self):
        value = self._certificate("PROBE_1", selected_high="P_13", alternative_high="P_13")
        assessment = self._validate(
            value, self._decision(probe="RETRY_REPEATABILITY_PROBE"),
        )
        self.assertFalse(assessment.admitted)
        self.assertIn("EXPECTED_VALUE_NOT_ABOVE_NORMALIZED_COST", assessment.rejection_reasons)

    def test_branch_normalization_and_registered_outcomes_are_enforced(self):
        value = self._certificate("PROBE_0")
        value["outcome_branches"][1]["branch_probability_token"] = "P_09"
        with self.assertRaisesRegex(ValueError, "sum to one"):
            self._validate(value, self._decision())

    def test_envelope_accepts_certified_direct_decision_with_null_value(self):
        tokenized = _tokenize(certified("current"), self.capability["namespaces"])
        tokenized["probe_value_certificate"] = None
        client = EnvelopeTolerantApiReliabilityClient(
            client=SimpleNamespace(messages=FakeMessages([json.dumps(tokenized)])),
            call_budget=SciAgentCallBudget(9, 1, 10),
        )
        request = attach_quantized_probe_value_contract(
            {"capability_contract": self.capability}
        )
        result = client.certified_decide(
            request, snapshot=ScientificMemorySnapshot(1, (), (), (), ()),
            current_evidence_id="current",
        )
        self.assertTrue(result.valid)
        assessment = client.audit[0]["probe_value_assessment"]
        self.assertFalse(assessment["admitted"])
        self.assertEqual(assessment["rejection_reasons"], ["AGENT_DID_NOT_REQUEST_PROBE"])
        value = self._certificate("PROBE_0")
        value["outcome_branches"][0]["outcome_token"] = "OUTCOME_RETRY_REPEATABLE"
        with self.assertRaisesRegex(ValueError, "registered outcomes"):
            self._validate(value, self._decision())

    def _validate(self, raw, decision):
        return validate_quantized_probe_value_certificate(
            raw, decision=decision, capability_contract=self.capability,
            probe_value_contract=self.contract,
        )

    @staticmethod
    def _decision(mode="RUN_MICRO_PROBE", probe="COMPENSATION_RESPONSE_PROBE"):
        return {
            "decision_mode": mode, "selected_probe_type": probe,
            "selected_skill": "BOUNDED_PLANAR_COMPENSATION",
        }

    @staticmethod
    def _certificate(probe_token, selected_high="P_16", alternative_high="P_16"):
        outcomes = (
            ("OUTCOME_COMP_ALIGNED", "OUTCOME_COMP_NOT_ALIGNED")
            if probe_token == "PROBE_0"
            else ("OUTCOME_RETRY_REPEATABLE", "OUTCOME_RETRY_NOT_REPEATABLE")
        )
        return {
            "selected_probe_token": probe_token,
            "current_selected_probability_token": "P_11",
            "current_alternative_probability_token": "P_09",
            "outcome_branches": [
                {"outcome_token": outcomes[0], "branch_probability_token": "P_10",
                 "selected_probability_token": selected_high,
                 "alternative_probability_token": "P_04"},
                {"outcome_token": outcomes[1], "branch_probability_token": "P_10",
                 "selected_probability_token": "P_04",
                 "alternative_probability_token": alternative_high},
            ],
        }


if __name__ == "__main__":
    unittest.main()
