import json
from pathlib import Path
import unittest

from scripts.generate_probemem_sciagent_probe_value_manifest import build_units


ROOT = Path(__file__).resolve().parents[1]


class SciAgentProbeValueProtocolTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(
            (ROOT / "configs/probemem_sciagent/api_reliability_v1_4.json").read_text()
        )

    def test_fresh_seed_boundary_and_reserve(self):
        units = build_units(self.config)
        self.assertEqual([row["environment_seed"] for row in units], list(range(6300, 6350)))
        registry = json.loads(
            (ROOT / "configs/probemem_sciagent/seed_registry_v5.json").read_text()
        )
        self.assertEqual(registry["partitions"]["probe_value_future_reserved"], [6350, 6449])

    def test_only_probe_value_contract_is_added_to_v13_interface(self):
        api = self.config["api"]
        self.assertEqual(api["response_envelope_mode"], "UNIQUE_CERTIFIED_OBJECT")
        self.assertEqual(api["capability_contract_mode"], "PER_REQUEST_TOKENS_V1")
        self.assertEqual(
            api["probe_value_contract_mode"],
            "EXPECTED_VALUE_OF_SAMPLE_INFORMATION_V1",
        )
        self.assertEqual(
            api["health_check_primary_calls"] + api["case_primary_calls"]
            + api["maximum_schema_repairs"], 10,
        )
        self.assertEqual(api["transport_retries"], 0)

    def test_budget_sensitive_shadow_gate_is_frozen(self):
        gate = self.config["success_gate"]
        self.assertEqual(gate["maximum_probe_admission_rate"], 0.5)
        self.assertEqual(gate["minimum_probe_rejections"], 4)
        self.assertIn("no_action_execution", self.config["claim_boundary"])
        self.assertTrue(all(self.config["prohibitions"].values()))


if __name__ == "__main__":
    unittest.main()
