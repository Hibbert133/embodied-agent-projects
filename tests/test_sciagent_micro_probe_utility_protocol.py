import json
from pathlib import Path
import unittest

from scripts.generate_probemem_sciagent_micro_probe_utility_manifest import build_units
from scripts.run_probemem_sciagent_micro_probe_utility import (
    _integrity_violations, _is_valid_post_action, _latest_probe_assessment,
)


ROOT = Path(__file__).resolve().parents[1]


class MicroProbeUtilityProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(
            (ROOT / "configs/probemem_sciagent/micro_probe_utility_v1_7.json").read_text(encoding="utf-8")
        )

    def test_fresh_seed_partition_and_reserve_are_disjoint(self):
        registry = json.loads(
            (ROOT / "configs/probemem_sciagent/seed_registry_v8.json").read_text(encoding="utf-8")
        )
        self.assertEqual(self.config["seed_range"], [6750, 6849])
        self.assertEqual(registry["partitions"]["micro_probe_utility_future_reserved"], [6850, 6949])
        self.assertEqual(len(build_units(self.config)), 100)

    def test_random_namespaces_are_unique_per_unit(self):
        for unit in build_units(self.config):
            ids = [
                unit["initial_seed"], unit["mandatory_probe_seed"], unit["compensation_probe_seed"],
                *unit["retry_probe_seeds"], unit["paired_verification_seed"],
            ]
            self.assertEqual(len(ids), len(set(ids)))

    def test_protocol_forbids_online_recovery_and_memory(self):
        self.assertTrue(self.config["prohibitions"]["online_recovery_execution"])
        self.assertTrue(self.config["prohibitions"]["memory_write"])
        self.assertTrue(self.config["prohibitions"]["principle_update"])

    def test_current_call_audit_slice_cannot_reuse_prior_assessment(self):
        audit = [
            {"valid_probe_value_certificate": True, "probe_value_assessment": {"admitted": True}},
            {"valid_probe_value_certificate": False, "probe_value_assessment": None},
        ]
        self.assertIsNone(_latest_probe_assessment(audit, 1))

    def test_post_action_requires_certified_direct_action(self):
        self.assertFalse(_is_valid_post_action({"stage": "POST_PROBE", "valid": False, "certified_decision": None}))
        self.assertTrue(_is_valid_post_action({
            "stage": "POST_PROBE", "valid": True,
            "certified_decision": {"decision": {"decision_mode": "ACT_DIRECTLY"}},
        }))

    def test_integrity_audit_rejects_stale_cross_case_assessment(self):
        decisions = [{
            "episode_id": "e2", "stage": "PRE_PROBE", "valid": False,
            "request_hash": "request-e2", "audit_slice_start": 1, "audit_slice_end": 2,
            "persisted_before_probe": True, "probe_value_assessment": {"admitted": True},
        }]
        audit = [
            {"request_hash": "request-e1", "valid_probe_value_certificate": True},
            {"request_hash": "request-e2", "valid_probe_value_certificate": False},
        ]
        reasons = _integrity_violations(decisions=decisions, probes=[], utilities=[], audit=audit)
        self.assertIn("PROBE_ASSESSMENT_AUDIT_MISMATCH:e2", reasons)

    def test_integrity_audit_requires_post_decision_before_outcome(self):
        reasons = _integrity_violations(
            decisions=[], probes=[], utilities=[{"episode_id": "e1", "label": "NOT_EVALUABLE"}], audit=[],
        )
        self.assertIn("OUTCOME_BEFORE_POST_DECISION:e1", reasons)


if __name__ == "__main__":
    unittest.main()
