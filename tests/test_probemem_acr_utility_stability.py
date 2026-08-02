"""Protocol and estimator tests for repeated ACR utility verification."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.analyze_probemem_acr_utility_stability import (
    COMPENSATION,
    RETRY,
    _bootstrap_reliability,
    _winner,
)
from scripts.generate_probemem_acr_utility_stability_manifest import IMPLEMENTATION_PATHS
from scripts.run_probemem_acr_utility_stability import _compensation_is_constructible, _load_inputs


ROOT = Path(__file__).resolve().parents[1]


class ProbeMemAcrUtilityStabilityTest(unittest.TestCase):
    def test_protocol_is_repeated_paired_development_only(self) -> None:
        config = json.loads(
            (ROOT / "configs/probemem_acr/utility_realization_stability_v2.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["registered_condition"], "fault_05")
        self.assertEqual(config["verification_repetitions"], 6)
        self.assertEqual(config["seed_partitions"]["development"], [1800, 1899])
        self.assertIn("both registered candidate skills", config["stopping_rule"]["operational_eligibility"])
        self.assertEqual(config["stopping_rule"]["target_operational_cases"], 20)
        self.assertFalse(config["stopping_rule"]["reads_candidate_outcomes"])
        self.assertTrue(config["prohibitions"]["fit_selector"])
        self.assertTrue(config["prohibitions"]["call_llm"])
        self.assertTrue(config["prohibitions"]["run_validation"])

    def test_manifest_tracks_collector_analyzer_and_agent_evidence(self) -> None:
        paths = {path.as_posix() for path in IMPLEMENTATION_PATHS}
        self.assertIn("scripts/run_probemem_acr_utility_stability.py", paths)
        self.assertIn("scripts/analyze_probemem_acr_utility_stability.py", paths)
        self.assertIn("src/reasoning/evidence.py", paths)
        self.assertIn("src/reasoning/structured_evidence.py", paths)

    def test_registered_fault_and_recovery_inputs_load(self) -> None:
        config = json.loads(
            (ROOT / "configs/probemem_acr/utility_realization_stability_v2.json").read_text(encoding="utf-8")
        )
        fault, recovery = _load_inputs(config)
        self.assertEqual(fault.condition_id, "fault_05")
        self.assertTrue(recovery.config_id)

    def test_candidate_eligibility_is_checked_without_outcomes(self) -> None:
        # The callable contract has no candidate-result argument; a real probe
        # context is integration-tested by the formal collector.
        self.assertNotIn("outcome", _compensation_is_constructible.__annotations__)

    def test_winner_is_status_then_progress_then_cost(self) -> None:
        accepted = {"status_utility": 1.0, "progress": 0.0, "steps": 500.0}
        rejected = {"status_utility": 0.0, "progress": 1.0, "steps": 1.0}
        self.assertEqual(_winner(accepted, rejected), COMPENSATION)
        left = {"status_utility": 0.5, "progress": 0.2, "steps": 500.0}
        right = {"status_utility": 0.5, "progress": 0.1, "steps": 1.0}
        self.assertEqual(_winner(left, right), COMPENSATION)
        left = {"status_utility": 0.5, "progress": 0.1, "steps": 20.0}
        right = {"status_utility": 0.5, "progress": 0.1, "steps": 30.0}
        self.assertEqual(_winner(left, right), COMPENSATION)
        self.assertEqual(_winner(right, left), RETRY)

    def test_cluster_bootstrap_is_reproducible(self) -> None:
        left = _bootstrap_reliability([(4, 6), (3, 5)], seed=9501, resamples=100)
        right = _bootstrap_reliability([(4, 6), (3, 5)], seed=9501, resamples=100)
        self.assertEqual(left, right)
        self.assertIsNotNone(left)


if __name__ == "__main__":
    unittest.main()
