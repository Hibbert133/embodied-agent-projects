from pathlib import Path
import unittest

from scripts.audit_online_memory_action_changes import (
    audit_action_changes,
    classify_change,
    summarize_cases,
)


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "outputs/probemem_online/sequential_runs/probemem_online_gate_c_20260803T095434Z_f346d23912a9"
BOOTSTRAP = ROOT / "outputs/probemem_online/bootstrap_runs/probemem_online_bootstrap_20260803T093056Z_6e6c4ba0f6fe/action_outcome_records.json"


class OnlineMemoryCausalAuditTest(unittest.TestCase):
    def test_change_effect_uses_frozen_status_order(self) -> None:
        self.assertEqual(classify_change("REJECTED", "ACCEPTED"), "HELPFUL")
        self.assertEqual(classify_change("ACCEPTED", "REJECTED"), "HARMFUL")
        self.assertEqual(classify_change("ACCEPTED", "ACCEPTED"), "TIE")

    def test_registered_audit_reconstructs_twelve_prior_only_snapshots(self) -> None:
        audit = audit_action_changes(RUN, BOOTSTRAP)
        self.assertEqual(audit["summary"]["effects"], {"HELPFUL": 4, "TIE": 5, "HARMFUL": 3})
        self.assertEqual(audit["summary"]["chronology_violations"], 0)
        self.assertEqual(
            audit["summary"]["all_change_directions"],
            ["INDEPENDENT_STOCHASTIC_RETRY->BOUNDED_PLANAR_COMPENSATION"],
        )
        for case in audit["action_change_cases"]:
            self.assertLess(case["chronology_audit"]["maximum_retrieved_episode_id"], case["episode_id"])

    def test_summary_does_not_promote_a_threshold(self) -> None:
        summary = summarize_cases([])
        self.assertIn("do not identify a deployable ambiguity threshold", summary["claim_boundary"])


if __name__ == "__main__":
    unittest.main()
