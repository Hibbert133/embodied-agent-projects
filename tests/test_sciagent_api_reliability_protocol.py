import json
from pathlib import Path
import unittest

from scripts.generate_probemem_sciagent_api_reliability_manifest import build_units


ROOT = Path(__file__).resolve().parents[1]


class ApiReliabilityProtocolTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "configs/probemem_sciagent/api_reliability_v1_1.json").read_text())

    def test_manifest_has_fifty_fresh_units_and_independent_streams(self):
        units = build_units(self.config)
        self.assertEqual([row["environment_seed"] for row in units], list(range(5850, 5900)))
        self.assertTrue(all(row["initial_seed"] != row["mandatory_probe_seed"] for row in units))

    def test_health_plus_cases_plus_repair_equals_ten_calls(self):
        api = self.config["api"]
        self.assertEqual(api["health_check_primary_calls"] + api["case_primary_calls"] + api["maximum_schema_repairs"], 10)
        self.assertEqual(api["transport_retries"], 0)

    def test_claim_boundary_forbids_recovery_and_execution(self):
        self.assertIn("no_action_execution", self.config["claim_boundary"])
        self.assertTrue(all(self.config["prohibitions"][key] for key in ("action_execution", "memory_write", "principle_update", "paired_outcome_collection")))


if __name__ == "__main__": unittest.main()
