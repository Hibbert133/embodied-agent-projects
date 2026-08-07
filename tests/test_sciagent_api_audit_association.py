import unittest

from scripts.run_probemem_sciagent_api_reliability import _latest_probe_assessment


class SciAgentApiAuditAssociationTest(unittest.TestCase):
    def test_transport_failure_does_not_reuse_prior_assessment(self):
        audit = [
            {"valid_probe_value_certificate": True, "probe_value_assessment": {"admitted": True}},
            {"valid_probe_value_certificate": False, "probe_value_contract_applied": True},
        ]
        self.assertIsNone(_latest_probe_assessment(audit, 1))

    def test_repair_assessment_is_bound_to_current_call_slice(self):
        audit = [
            {"valid_probe_value_certificate": True, "probe_value_assessment": {"admitted": False}},
            {"valid_probe_value_certificate": False},
            {"valid_probe_value_certificate": True, "probe_value_assessment": {"admitted": True}},
        ]
        self.assertEqual(_latest_probe_assessment(audit, 1), {"admitted": True})

    def test_invalid_slice_fails_closed(self):
        with self.assertRaises(ValueError):
            _latest_probe_assessment([], 1)


if __name__ == "__main__":
    unittest.main()
