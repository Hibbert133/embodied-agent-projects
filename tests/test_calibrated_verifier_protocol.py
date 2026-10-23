from __future__ import annotations

from itertools import product
import json
from pathlib import Path
import unittest

from scripts.generate_calibrated_verifier_manifest import build_units


ROOT = Path(__file__).resolve().parents[1]


class CalibratedVerifierProtocolTest(unittest.TestCase):
    def setUp(self):
        self.calibration = json.loads((ROOT / "configs/probemem_verifier/calibrated_v2_calibration.json").read_text(encoding="utf-8"))
        self.development = json.loads((ROOT / "configs/probemem_verifier/calibrated_v2_development.json").read_text(encoding="utf-8"))
        self.registry = json.loads((ROOT / "configs/probemem_verifier/seed_registry_v2.json").read_text(encoding="utf-8"))

    def test_seed_partitions_are_fresh_and_exact(self):
        parts = self.registry["new_partitions"]
        self.assertEqual(parts["calibrated_verifier_calibration"], [4800, 4899])
        self.assertEqual(parts["calibrated_verifier_prospective_development"], [4900, 5099])
        self.assertEqual(parts["calibrated_verifier_future_reserved"], [5100, 5299])
        self.assertEqual([row["environment_seed"] for row in build_units(self.calibration)], list(range(4800, 4900)))

    def test_grid_and_frozen_method_boundary(self):
        grid = self.calibration["calibration_grid"]
        self.assertEqual(len(list(product(*grid.values()))), 4800)
        self.assertEqual(self.calibration["posterior"]["comparison_samples"], 10000)
        self.assertEqual(self.calibration["posterior"]["credible_level"], 0.95)
        self.assertTrue(self.calibration["prohibitions"]["glm"])
        self.assertTrue(self.calibration["prohibitions"]["validation"])

    def test_development_fails_closed_before_calibration(self):
        self.assertEqual(self.development["status"], "BLOCKED_PENDING_CALIBRATION")
        self.assertIsNone(self.development["calibration_binding"])
        self.assertIsNone(self.development["frozen_thresholds"])

    def test_runner_isolated_from_v1_output_and_writes_selected_only(self):
        source = (ROOT / "scripts/probemem_calibrated_runner.py").read_text(encoding="utf-8")
        manifest = (ROOT / "scripts/generate_calibrated_verifier_manifest.py").read_text(encoding="utf-8")
        self.assertIn("outputs/probemem_calibrated_verifier", manifest)
        self.assertNotIn('outputs/probemem_verifier_demo/runs', manifest)
        self.assertIn("SELECTED_ACTION_ONLY", source)
        self.assertNotIn("candidate_outcomes=", source)


if __name__ == "__main__":
    unittest.main()
