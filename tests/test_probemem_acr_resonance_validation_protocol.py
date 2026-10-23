from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.check_probemem_acr_resonance_validation_seeds import validation_seeds
from src.probemem.resonance_policy import COMPENSATION, RETRY, decide_second_attempt


ROOT = Path(__file__).resolve().parents[1]


class ResonanceValidationProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads((ROOT / "configs/probemem_acr/resonance_validation_v1.json").read_text(encoding="utf-8"))

    def test_population_is_fixed_and_preserves_heldout(self) -> None:
        seeds = validation_seeds(self.config)
        self.assertEqual(seeds, [*range(3050, 3100), *range(3200, 3300)])
        self.assertFalse(set(seeds) & set(range(3100, 3200)))
        self.assertTrue(self.config["population"]["run_all_units_without_early_stopping"])

    def test_frozen_status_rule_matches_host_policy(self) -> None:
        frozen = self.config["frozen_status_rule"]
        self.assertEqual(frozen, {"ACCEPTED": "STOP_SUCCESS", "INCONCLUSIVE": RETRY.value, "REJECTED": COMPENSATION.value})
        for status, expected in (("ACCEPTED", None), ("INCONCLUSIVE", RETRY), ("REJECTED", COMPENSATION)):
            decision = decide_second_attempt(method="status_conditioned", first_verification_status=status,
                                             remaining_budget=500, reserved_second_verification_budget=500)
            self.assertIs(decision.selected_skill, expected)

    def test_namespaces_and_budget_are_frozen(self) -> None:
        namespaces = list(self.config["random_namespaces"].values())
        self.assertEqual(len(namespaces), len(set(namespaces)))
        self.assertEqual(self.config["budget"]["maximum_verification_attempts"], 2)
        self.assertEqual(self.config["budget"]["online_max_steps_per_case"], 1564)
        self.assertEqual(self.config["budget"]["evaluator_paired_collection_max_steps_per_case"], 2064)

    def test_validation_cannot_call_llm_or_execute_heldout(self) -> None:
        prohibitions = self.config["prohibitions"]
        self.assertTrue(prohibitions["call_llm"])
        self.assertTrue(prohibitions["run_heldout"])
        self.assertTrue(prohibitions["rerun_or_replace_validation"])


if __name__ == "__main__":
    unittest.main()
