import unittest

from src.probemem_verifier.candidate_verifier import validate_glm_candidate_mapping
from tests.probemem_verifier_helpers import COMP, RETRY


def candidate(skill, record_id):
    return {
        "predicted_accept_probability": 0.8,
        "predicted_status": "ACCEPTED",
        "confidence": 0.8,
        "memory_applicable": True,
        "coverage_count": 1,
        "supporting_record_ids": [record_id],
        "contradicting_record_ids": [],
    }


class VerifierMemoryLeakageTest(unittest.TestCase):
    def test_unknown_future_or_counterfactual_id_fails_closed(self) -> None:
        payload = {COMP: candidate(COMP, "allowed"), RETRY: candidate(RETRY, "future-or-counterfactual")}
        with self.assertRaises(ValueError):
            validate_glm_candidate_mapping(payload, allowed_memory_ids={"allowed"})

    def test_oracle_field_is_rejected(self) -> None:
        payload = {COMP: candidate(COMP, "allowed"), RETRY: candidate(RETRY, "allowed-2")}
        payload[COMP]["oracle_winner"] = True
        with self.assertRaises((KeyError, ValueError)):
            validate_glm_candidate_mapping(payload, allowed_memory_ids={"allowed", "allowed-2"})


if __name__ == "__main__":
    unittest.main()
