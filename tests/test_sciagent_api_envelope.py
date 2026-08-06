import json
from types import SimpleNamespace
import unittest

from src.probemem_sciagent.agent_orchestrator import SciAgentCallBudget
from src.probemem_sciagent.api_envelope import (
    EnvelopeTolerantApiReliabilityClient,
    extract_unique_certified_object,
)
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from tests.test_sciagent_api_reliability import FakeMessages, certified


class SciAgentApiEnvelopeTest(unittest.TestCase):
    def test_bare_certified_object_is_preferred(self):
        value = certified()
        parsed, mode = extract_unique_certified_object(json.dumps(value))
        self.assertEqual(parsed, value)
        self.assertEqual(mode, "BARE_JSON")

    def test_reasoning_wrapped_unique_object_is_accepted(self):
        value = certified()
        text = "<think>compare bounded alternatives</think>\n```json\n" + json.dumps(value) + "\n```"
        parsed, mode = extract_unique_certified_object(text)
        self.assertEqual(parsed, value)
        self.assertEqual(mode, "WRAPPED_UNIQUE_JSON")

    def test_two_distinct_certified_objects_are_ambiguous(self):
        first = certified()
        second = certified(mode="ABSTAIN", selected=None)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            extract_unique_certified_object(json.dumps(first) + "\n" + json.dumps(second))

    def test_nested_objects_do_not_become_candidates(self):
        value = certified()
        parsed, _ = extract_unique_certified_object("prefix " + json.dumps(value) + " suffix")
        self.assertEqual(parsed, value)

    def test_wrapped_object_passes_certificate_without_repair(self):
        value = certified()
        messages = FakeMessages(["analysis\n```json\n" + json.dumps(value) + "\n```"])
        client = EnvelopeTolerantApiReliabilityClient(
            client=SimpleNamespace(messages=messages),
            call_budget=SciAgentCallBudget(9, 1, 10),
        )
        result = client.certified_decide(
            {}, snapshot=ScientificMemorySnapshot(1, (), (), (), ()),
            current_evidence_id="current",
        )
        self.assertTrue(result.valid)
        self.assertFalse(result.repaired)
        self.assertEqual(client.audit[0]["extraction_mode"], "WRAPPED_UNIQUE_JSON")


if __name__ == "__main__":
    unittest.main()
