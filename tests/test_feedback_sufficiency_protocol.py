from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.check_probemem_acr_feedback_sufficiency_seeds import development_seeds
from scripts.analyze_feedback_sufficiency_audit import _auc
from scripts.generate_feedback_sufficiency_manifest import IMPLEMENTATION_PATHS, build_population_units


ROOT = Path(__file__).resolve().parents[1]


class FeedbackSufficiencyProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads((ROOT / "configs/probemem_acr/verification_feedback_sufficiency_development_v1.json").read_text(encoding="utf-8"))

    def test_fresh_development_range_and_reservation(self) -> None:
        self.assertEqual(development_seeds(self.config), list(range(3300, 3500)))
        self.assertEqual(self.config["seed_partitions"]["reserved_not_executed"], [3500, 3599])
        self.assertFalse(set(development_seeds(self.config)) & set(range(3100, 3200)))

    def test_label_blind_stop_and_four_realizations(self) -> None:
        self.assertFalse(self.config["stopping_rule"]["reads_verification_outcomes"])
        self.assertEqual(self.config["first_retry_realizations"], 4)

    def test_prohibitions_block_scope_expansion(self) -> None:
        prohibited = self.config["prohibitions"]
        for key in ("fit_selector", "call_llm", "write_online_memory", "run_validation", "run_heldout"):
            self.assertTrue(prohibited[key])

    def test_manifest_has_independent_repeated_streams(self) -> None:
        units = build_population_units(self.config)
        self.assertEqual(len(units), 200)
        for unit in units:
            streams = [unit["initial_perturbation_seed"], unit["diagnostic_probe_seed"], *unit["first_verification_seeds"], *unit["paired_second_verification_seeds"]]
            self.assertEqual(len(streams), len(set(streams)))
            self.assertEqual(len(unit["first_verification_seeds"]), 4)

    def test_manifest_hashes_collector_and_analyzer(self) -> None:
        paths = {path.as_posix() for path in IMPLEMENTATION_PATHS}
        self.assertIn("scripts/run_feedback_sufficiency_audit.py", paths)
        self.assertIn("scripts/analyze_feedback_sufficiency_audit.py", paths)

    def test_auc_has_frozen_orientation_and_tie_handling(self) -> None:
        self.assertEqual(_auc([1, 1, 0, 0], [3.0, 2.0, 1.0, 0.0]), 1.0)
        self.assertEqual(_auc([1, 0], [1.0, 1.0]), 0.5)
        self.assertIsNone(_auc([1, 1], [0.0, 1.0]))


if __name__ == "__main__":
    unittest.main()
