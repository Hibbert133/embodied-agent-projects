from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/autoresearch/heldout_allocation_v1.json"


class HeldoutAllocationProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_frozen_sources_exist(self) -> None:
        self.assertTrue(ROOT.joinpath("docs/research/frozen_execution_plan_v1.md").is_file())
        self.assertTrue(ROOT.joinpath("docs/protocols/heldout_allocation_v1.md").is_file())

    def test_seed_threshold_and_phase_definition_are_frozen(self) -> None:
        self.assertEqual(self.config["seed_start"], 330)
        self.assertEqual(self.config["num_seeds"], 10)
        self.assertEqual(self.config["allocation"]["threshold"], 0.91612970415368)
        self.assertEqual(self.config["allocation"]["minimum_phase_samples"], 8)
        self.assertEqual(self.config["allocation"]["contact_distance_m"], 0.08)
        self.assertEqual(self.config["allocation"]["near_goal_distance_m"], 0.08)

    def test_condition_to_mechanism_mapping_is_frozen(self) -> None:
        conditions = self.config["conditions"]
        self.assertEqual([item["condition_id"] for item in conditions], [
            "fault_01", "fault_02", "fault_03", "fault_04", "fault_05"
        ])
        self.assertEqual(
            [item["evaluator_mechanism"] for item in conditions],
            ["stable_bias"] * 4 + ["stochastic_noise"],
        )
        self.assertEqual(
            [item.get("parameters", {}).get("bias") for item in conditions[:4]],
            [
                [0.145, 0.0, 0.0, 0.0],
                [-0.18, 0.0, 0.0, 0.0],
                [0.0, -0.198, 0.0, 0.0],
                [0.14, -0.14, 0.0, 0.0],
            ],
        )

    def test_budget_preserves_probe_and_fresh_verification(self) -> None:
        budget = self.config["budget"]
        self.assertEqual(budget["total_case_environment_steps"], 1064)
        self.assertEqual(budget["registered_probe_environment_steps"], 64)
        self.assertEqual(budget["minimum_reserved_verification_steps"], 500)
        self.assertEqual(budget["maximum_diagnostic_probes"], 1)
        self.assertEqual(budget["maximum_corrective_verifications"], 1)
        self.assertEqual(budget["maximum_attempt_id"], 2)
        self.assertEqual(
            self.config["max_initial_steps"]
            + budget["registered_probe_environment_steps"]
            + budget["minimum_reserved_verification_steps"],
            budget["total_case_environment_steps"],
        )

    def test_probe_outcome_and_allocation_thresholds_are_distinct(self) -> None:
        self.assertEqual(
            self.config["registered_probe"]["outcome_classifier_threshold"],
            0.11560838098372882,
        )
        self.assertNotEqual(
            self.config["registered_probe"]["outcome_classifier_threshold"],
            self.config["allocation"]["threshold"],
        )

    def test_protocol_forbids_heldout_retuning_and_overwrite(self) -> None:
        self.assertFalse(self.config["heldout_retuning"])
        self.assertFalse(self.config["overwrite_existing_run"])
        self.assertTrue(
            self.config["promotion_gate"]["require_both_probe_need_classes"]
        )
        self.assertEqual(
            self.config["evaluator_labels"]["single_class_status"],
            "INCOMPLETE_FOR_PROBE_NEED_EVALUATION",
        )


if __name__ == "__main__":
    unittest.main()
