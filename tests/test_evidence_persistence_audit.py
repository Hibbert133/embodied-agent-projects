import copy
import unittest

from scripts.analyze_evidence_persistence import verify_records
from src.probemem.evidence_persistence import CONDITIONS, METHODS


class PersistenceRecordAuditTest(unittest.TestCase):
    def setUp(self):
        self.identity = {"experiment_run_id": "synthetic", "manifest_id": "m", "source_git_commit": "c"}
        self.decisions = [{**self.identity, "seed": 8000, "sequence": i + 1,
                           "source_context_oracle": c, "plan": {"requires_fresh_verification": True}}
                          for i, c in enumerate(CONDITIONS)]
        self.decisions.append({**self.identity, "seed": 8000, "sequence": 5,
                               "method": "UNCORRECTED", "plan": {"requires_fresh_verification": True}})
        self.outcomes = []
        for i, source in enumerate(CONDITIONS):
            for target in CONDITIONS:
                for method in METHODS:
                    control = method == "UNCORRECTED"
                    self.outcomes.append({**self.identity, "seed": 8000, "sequence": 6 + len(self.outcomes),
                        "decision_sequence": 5 if control else i + 1, "source_context_oracle": source,
                        "target_context_oracle": target, "method": method,
                        "branch_id": f'{target}_{"control" if control else source}',
                        "initial_state_hash": "state", "logical_probe_steps": 0 if control else 64,
                        "steps": 10, "success": True, "verification_status": "ACCEPTED",
                        "plan_executable": True, "reused": control and i > 0})

    def validate(self):
        return verify_records(self.decisions, self.outcomes, self.identity, [8000])

    def test_valid_full_cross_with_shared_control(self):
        result = self.validate()
        self.assertEqual(result["unique_branches"], 20)
        self.assertEqual(result["reused_control_rows"], 12)

    def test_record_corruptions_fail_closed(self):
        for key, value in (("sequence", 1), ("manifest_id", "other"), ("steps", 501),
                           ("decision_sequence", 5), ("success", False),
                           ("initial_state_hash", "other"), ("reused", True),
                           ("plan_executable", False)):
            with self.subTest(key=key):
                original = copy.deepcopy(self.outcomes[0])
                self.outcomes[0][key] = value
                with self.assertRaises(ValueError):
                    self.validate()
                self.outcomes[0] = original

    def test_late_plan_rejected_even_if_event_sequences_contiguous(self):
        self.decisions[3]["sequence"], self.outcomes[0]["sequence"] = 6, 4
        with self.assertRaisesRegex(ValueError, "precede"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
