"""Tests for the frozen ProbeMem-ACR retry-utility replication."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.analyze_probemem_acr_retry_utility_replication import _bootstrap_rank_ci
from scripts.generate_probemem_acr_retry_replication_manifest import IMPLEMENTATION_PATHS


ROOT = Path(__file__).resolve().parents[1]


class ProbeMemAcrRetryReplicationTest(unittest.TestCase):
    def test_manifest_tracks_collector_analyzer_and_agent_evidence_source(self) -> None:
        paths = {path.as_posix() for path in IMPLEMENTATION_PATHS}
        self.assertIn("scripts/run_probemem_acr_retry_utility_replication.py", paths)
        self.assertIn("scripts/analyze_probemem_acr_retry_utility_replication.py", paths)
        self.assertIn("src/probemem/intervention_utility.py", paths)
        self.assertIn("src/reasoning/evidence.py", paths)

    def test_protocol_is_single_condition_direction_only_and_no_api(self) -> None:
        config = json.loads(
            (ROOT / "configs/probemem_acr/retry_utility_replication_v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["registered_condition"], "fault_05")
        self.assertEqual(
            set(config["registered_directional_hypotheses"]),
            {"phase_inconsistency", "probe_mean_estimation_residual"},
        )
        self.assertTrue(config["prohibitions"]["fit_threshold"])
        self.assertTrue(config["prohibitions"]["call_llm"])
        self.assertTrue(config["prohibitions"]["run_validation"])
        self.assertEqual(config["seed_partitions"]["development_replication"], [1400, 1499])

    def test_rank_bootstrap_is_reproducible(self) -> None:
        left = _bootstrap_rank_ci([2.0, 3.0], [0.0, 1.0], seed=9401, resamples=100)
        right = _bootstrap_rank_ci([2.0, 3.0], [0.0, 1.0], seed=9401, resamples=100)
        self.assertEqual(left, right)
        self.assertEqual(left, {"low": 1.0, "high": 1.0})


if __name__ == "__main__":
    unittest.main()
