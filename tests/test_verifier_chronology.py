import unittest

from src.probemem_verifier.candidate_verifier import build_candidate_memory_summaries
from tests.probemem_verifier_helpers import COMP, RETRY, memory, record, signature


class VerifierChronologyTest(unittest.TestCase):
    def test_current_episode_outcome_cannot_enter_current_decision(self) -> None:
        store = memory([record(20, COMP, "ACCEPTED"), record(21, RETRY, "REJECTED")])
        summaries = build_candidate_memory_summaries(store, signature(21), episode_id=21)
        cited = set(summaries[COMP].global_record_ids + summaries[RETRY].global_record_ids)
        self.assertIn(f"record-20-{COMP}", cited)
        self.assertNotIn(f"record-21-{RETRY}", cited)

    def test_method_memory_accepts_only_one_selected_action_per_episode(self) -> None:
        store = memory([record(20, COMP, "ACCEPTED")])
        store.append_after_verification(record(21, RETRY, "REJECTED"))
        with self.assertRaises(ValueError):
            store.append_after_verification(record(21, COMP, "ACCEPTED"))


if __name__ == "__main__":
    unittest.main()
