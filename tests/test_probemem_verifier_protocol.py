import json
from pathlib import Path
import unittest

from scripts.generate_probemem_verifier_manifest import build_units


ROOT = Path(__file__).resolve().parents[1]


class ProbeMemVerifierProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads((ROOT / "configs/probemem_verifier/demo_v1.json").read_text(encoding="utf-8"))
        self.registry = json.loads((ROOT / "configs/probemem_verifier/seed_registry_v1.json").read_text(encoding="utf-8"))

    def test_fresh_seed_partition_and_reserve_are_exact(self) -> None:
        self.assertEqual(self.config["seed_range"], [4700, 4749])
        self.assertEqual(self.registry["new_partitions"]["verifier_demo_future_reserved"], [4750, 4799])
        units = build_units(self.config)
        self.assertEqual([row["environment_seed"] for row in units], list(range(4700, 4750)))
        self.assertTrue(all("outcome" not in key for row in units for key in row))

    def test_thresholds_and_scope_are_frozen(self) -> None:
        self.assertEqual(self.config["frozen_variance_threshold"], 0.11560838098372882)
        self.assertEqual(self.config["admission"]["ambiguity_margin"], 0.05)
        self.assertEqual(self.config["override_guard"]["probability_margin_minimum"], 0.15)
        self.assertEqual(self.config["override_guard"]["alternative_coverage_minimum"], 3)
        self.assertEqual(self.config["override_guard"]["alternative_contradiction_rate_maximum"], 0.30)
        self.assertEqual(self.config["override_guard"]["verifier_confidence_minimum"], 0.70)
        self.assertFalse(self.config["glm"]["enabled_for_registered_run"])
        self.assertTrue(all(self.config["prohibitions"].values()))

    def test_budget_is_unchanged(self) -> None:
        self.assertEqual(
            self.config["budget"],
            {"initial_max_steps": 500, "probe_max_steps": 64, "verification_max_steps": 500, "total_case_max_steps": 1064},
        )


if __name__ == "__main__":
    unittest.main()
