import copy
import json
from types import SimpleNamespace
import unittest

from src.probemem_sciagent.agent_orchestrator import SciAgentCallBudget
from src.probemem_sciagent.api_envelope import EnvelopeTolerantApiReliabilityClient
from src.probemem_sciagent.capability_contract import (
    TOKEN_FIELDS,
    attach_capability_contract,
    build_capability_contract,
    expand_capability_response,
)
from src.probemem_sciagent.certified_decision import DECISION_BASES, GROUNDING_CLAIMS
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.schemas import PROBE_JUSTIFICATION_CODES
from tests.test_sciagent_api_reliability import FakeMessages, certified


class SciAgentCapabilityContractTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = ScientificMemorySnapshot(1, (), (), (), ())
        self.contract = build_capability_contract(
            snapshot=self.snapshot, current_evidence_id="evidence-current",
        )

    def test_contract_enumerates_every_registered_static_value(self):
        namespaces = self.contract.namespaces
        self.assertEqual(set(namespaces["probe_justification_codes"].values()), set(PROBE_JUSTIFICATION_CODES))
        self.assertEqual(set(namespaces["decision_bases"].values()), set(DECISION_BASES))
        self.assertEqual(set(namespaces["grounding_claims"].values()), set(GROUNDING_CLAIMS))
        self.assertEqual(namespaces["evidence_ids"], {"EVIDENCE_0": "evidence-current"})

    def test_tokenized_response_expands_to_existing_schema(self):
        canonical = certified("evidence-current")
        tokenized = _tokenize(canonical, self.contract.namespaces)
        self.assertEqual(expand_capability_response(tokenized, self.contract.to_payload()), canonical)

    def test_unknown_or_canonical_value_in_token_field_fails_closed(self):
        tokenized = _tokenize(certified("evidence-current"), self.contract.namespaces)
        tokenized["decision"]["selected_skill"] = "BOUNDED_PLANAR_COMPENSATION"
        with self.assertRaisesRegex(ValueError, "unknown capability token"):
            expand_capability_response(tokenized, self.contract.to_payload())

    def test_token_from_another_request_cannot_cite_evidence(self):
        tokenized = _tokenize(certified("evidence-current"), self.contract.namespaces)
        tokenized["certificate"]["current_evidence_id"] = "EVIDENCE_1"
        with self.assertRaisesRegex(ValueError, "unknown capability token"):
            expand_capability_response(tokenized, self.contract.to_payload())

    def test_attachment_is_agent_visible_and_contains_no_oracle_fields(self):
        payload = attach_capability_contract(
            {"stage": "PRE_PROBE"}, snapshot=self.snapshot,
            current_evidence_id="evidence-current",
        )
        self.assertEqual(payload["capability_contract"]["unknown_token_policy"], "FAIL_CLOSED")
        self.assertIn("probe_justification_codes", payload["capability_contract"]["namespaces"])

    def test_client_expands_tokens_before_existing_certificate_validation(self):
        tokenized = _tokenize(certified("evidence-current"), self.contract.namespaces)
        messages = FakeMessages(["```json\n" + json.dumps(tokenized) + "\n```"])
        client = EnvelopeTolerantApiReliabilityClient(
            client=SimpleNamespace(messages=messages),
            call_budget=SciAgentCallBudget(9, 1, 10),
        )
        request = attach_capability_contract(
            {}, snapshot=self.snapshot, current_evidence_id="evidence-current",
        )
        result = client.certified_decide(
            request, snapshot=self.snapshot, current_evidence_id="evidence-current",
        )
        self.assertTrue(result.valid)
        self.assertTrue(client.audit[0]["valid_capability_contract"])


def _tokenize(value, namespaces):
    result = copy.deepcopy(value)
    for section, fields in TOKEN_FIELDS.items():
        for field, namespace in fields.items():
            inverse = {canonical: token for token, canonical in namespaces[namespace].items()}
            item = result[section][field]
            if item is None:
                continue
            if isinstance(item, list):
                result[section][field] = [inverse[element] for element in item]
            else:
                result[section][field] = inverse[item]
    return result


if __name__ == "__main__":
    unittest.main()
