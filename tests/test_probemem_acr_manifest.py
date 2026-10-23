"""Static tests for the frozen ProbeMem-ACR manifest inputs."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.generate_probemem_acr_manifest import IMPLEMENTATION_PATHS


ROOT = Path(__file__).resolve().parents[1]


class ProbeMemAcrManifestTest(unittest.TestCase):
    def test_manifest_hashes_every_formal_implementation(self) -> None:
        required = {
            "src/probemem/action_memory.py",
            "src/probemem/action_evidence.py",
            "src/probemem/action_prediction.py",
            "src/probemem/resonance.py",
            "src/probemem/intervention_memory_gate.py",
            "scripts/run_probemem_acr_development.py",
            "scripts/analyze_probemem_acr.py",
        }
        self.assertTrue(required <= {item.as_posix() for item in IMPLEMENTATION_PATHS})

    def test_config_freezes_population_budget_and_no_api(self) -> None:
        config = json.loads(
            (ROOT / "configs/probemem_acr/development_v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["seed_range"], [1100, 1199])
        self.assertEqual(config["budget"]["evaluator_paired_collection_max_steps"], 1564)
        self.assertEqual(config["scope"]["api_calls"], 0)
        self.assertFalse(config["scope"]["validation"])
        self.assertFalse(config["v2_coverage_baseline"]["append_current_stream"])


if __name__ == "__main__":
    unittest.main()
