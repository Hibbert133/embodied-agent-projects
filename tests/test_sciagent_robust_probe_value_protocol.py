import json
from pathlib import Path
import unittest

from scripts.generate_probemem_sciagent_robust_probe_value_manifest import build_units

ROOT = Path(__file__).resolve().parents[1]


class SciAgentRobustProbeValueProtocolTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "configs/probemem_sciagent/api_reliability_v1_6.json").read_text())

    def test_fresh_seed_boundary_and_reserve(self):
        self.assertEqual([row["environment_seed"] for row in build_units(self.config)], list(range(6600, 6650)))
        registry = json.loads((ROOT / "configs/probemem_sciagent/seed_registry_v7.json").read_text())
        self.assertEqual(registry["partitions"]["robust_probe_value_future_reserved"], [6650, 6749])

    def test_hard_deadline_and_robust_rule_are_frozen(self):
        api = self.config["api"]
        self.assertEqual(api["transport_deadline_mode"], "SUBPROCESS_HARD_DEADLINE_V1")
        self.assertEqual(api["hard_deadline_seconds"], 210)
        self.assertEqual(api["probe_value_contract_mode"], "ROBUST_QUANTIZED_EXPECTED_VALUE_OF_SAMPLE_INFORMATION_V1")
        self.assertEqual(self.config["robust_value_rule"]["maximum_current_probability_gap"], 0.10)

    def test_shadow_boundary_and_call_cap(self):
        api = self.config["api"]
        self.assertEqual(api["health_check_primary_calls"] + api["case_primary_calls"] + api["maximum_schema_repairs"], 10)
        self.assertEqual(api["transport_retries"], 0)
        self.assertTrue(all(self.config["prohibitions"].values()))


if __name__ == "__main__": unittest.main()
