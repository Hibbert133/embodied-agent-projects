import json
from pathlib import Path
import unittest

from scripts.generate_probemem_sciagent_capability_manifest import build_units


ROOT = Path(__file__).resolve().parents[1]


class SciAgentCapabilityProtocolTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(
            (ROOT / "configs/probemem_sciagent/api_reliability_v1_3.json").read_text()
        )

    def test_fresh_seed_boundary_and_reserve(self):
        units = build_units(self.config)
        self.assertEqual([row["environment_seed"] for row in units], list(range(6150, 6200)))
        registry = json.loads(
            (ROOT / "configs/probemem_sciagent/seed_registry_v4.json").read_text()
        )
        self.assertEqual(registry["partitions"]["capability_contract_future_reserved"], [6200, 6299])

    def test_capability_contract_is_only_new_interface_mode(self):
        api = self.config["api"]
        self.assertEqual(api["response_envelope_mode"], "UNIQUE_CERTIFIED_OBJECT")
        self.assertEqual(api["capability_contract_mode"], "PER_REQUEST_TOKENS_V1")
        self.assertEqual(
            api["health_check_primary_calls"] + api["case_primary_calls"]
            + api["maximum_schema_repairs"],
            10,
        )
        self.assertEqual(api["transport_retries"], 0)

    def test_shadow_prohibitions_remain_complete(self):
        self.assertIn("no_action_execution", self.config["claim_boundary"])
        self.assertTrue(all(self.config["prohibitions"].values()))


if __name__ == "__main__":
    unittest.main()
