from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/autoresearch/heldout_intervention_v1.json"


class HeldoutInterventionProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_binds_exact_completed_allocation_run(self) -> None:
        self.assertEqual(
            self.config["source_allocation_manifest_id"],
            "a39271db862f28574ad9eb47de4b2bf476950b58749b21baaac59117cf75981c",
        )
        source = ROOT / self.config["source_allocation_directory"]
        status = json.loads((source / "run_status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "COMPLETED")
        self.assertEqual(status["operational_units"], 33)
        self.assertEqual(self.config["expected_operational_units"], 33)

    def test_methods_and_intervention_sources_are_frozen(self) -> None:
        self.assertEqual(len(self.config["methods"]), 6)
        semantics = self.config["intervention_semantics"]
        self.assertEqual(
            semantics["passive_compensation_source"],
            "initial StructuredEvidenceState temporal response",
        )
        self.assertEqual(
            semantics["probe_compensation_source"],
            "first repetition of the registered 64-step probe",
        )

    def test_verification_is_fresh_matched_and_bounded(self) -> None:
        verification = self.config["verification"]
        self.assertEqual(verification["maximum_steps"], 500)
        self.assertEqual(verification["perturbation_seed_namespace"], 4101)
        self.assertTrue(verification["shared_realization_across_methods"])
        self.assertTrue(verification["deduplicate_identical_interventions"])
        budget = self.config["budget"]
        self.assertEqual(
            budget["registered_probe_environment_steps"]
            + budget["minimum_reserved_verification_steps"],
            564,
        )
        self.assertEqual(budget["maximum_corrective_verifications"], 1)

    def test_useful_probe_is_evaluator_only_and_causal(self) -> None:
        causal = self.config["causal_metrics"]
        self.assertIn("probe changes intervention", causal["useful_probe"])
        self.assertTrue(causal["decision_probe_needed"].startswith("same definition"))
        self.assertFalse(self.config["heldout_retuning"])
        self.assertEqual(self.config["api_calls"], 0)


if __name__ == "__main__":
    unittest.main()
