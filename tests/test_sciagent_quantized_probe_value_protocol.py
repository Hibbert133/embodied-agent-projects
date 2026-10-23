import json
from pathlib import Path
import unittest

from scripts.generate_probemem_sciagent_quantized_probe_value_manifest import build_units


ROOT = Path(__file__).resolve().parents[1]


class SciAgentQuantizedProbeValueProtocolTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(
            (ROOT / "configs/probemem_sciagent/api_reliability_v1_5.json").read_text()
        )

    def test_fresh_seed_boundary_and_reserve(self):
        self.assertEqual(
            [row["environment_seed"] for row in build_units(self.config)],
            list(range(6450, 6500)),
        )
        registry = json.loads(
            (ROOT / "configs/probemem_sciagent/seed_registry_v6.json").read_text()
        )
        self.assertEqual(
            registry["partitions"]["quantized_probe_value_future_reserved"],
            [6500, 6599],
        )

    def test_quantized_contract_and_call_budget_are_frozen(self):
        api = self.config["api"]
        self.assertEqual(
            api["probe_value_contract_mode"],
            "QUANTIZED_EXPECTED_VALUE_OF_SAMPLE_INFORMATION_V1",
        )
        self.assertEqual(
            api["health_check_primary_calls"] + api["case_primary_calls"]
            + api["maximum_schema_repairs"], 10,
        )
        self.assertEqual(api["transport_retries"], 0)

    def test_shadow_gate_forbids_execution(self):
        self.assertEqual(self.config["success_gate"]["maximum_probe_admission_rate"], 0.5)
        self.assertTrue(all(self.config["prohibitions"].values()))
        self.assertIn("no_action_execution", self.config["claim_boundary"])


if __name__ == "__main__":
    unittest.main()
