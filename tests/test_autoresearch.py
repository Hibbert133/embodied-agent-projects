from __future__ import annotations

import unittest

from src.autoresearch import (
    ExperimentBudget,
    RecoveryPolicyConfig,
    SkillOutcome,
    select_counterfactual_skill,
    select_noise_calibration,
    choose_runtime_skill,
    validate_recovery_policy_config,
)


def config(**changes: object) -> RecoveryPolicyConfig:
    values = {
        "config_id": "manual_v1",
        "probe_steps_per_direction": 8,
        "probe_magnitude": 0.2,
        "secondary_axis_threshold": 0.04,
        "dominance_ratio": 2.0,
        "allowed_schedules": ("whole", "phase_aware"),
        "offer_abstain": True,
        "evidence_detail": "temporal",
        "max_recovery_rollouts": 1,
    }
    values.update(changes)
    return RecoveryPolicyConfig(**values)  # type: ignore[arg-type]


class AutoresearchTest(unittest.TestCase):
    def test_runtime_config_changes_explicit_skill_boundary(self) -> None:
        diagnosis = {"estimated_action_bias": (0.10, 0.05)}
        simultaneous = choose_runtime_skill(config(dominance_ratio=2.0), diagnosis)
        dominant = choose_runtime_skill(config(dominance_ratio=1.5), diagnosis)
        self.assertEqual(simultaneous.skill_id, "simultaneous_xy_repair")
        self.assertEqual(dominant.skill_id, "dominant_axis_repair")
        self.assertEqual(dominant.schedule, "phase_aware")

    def test_runtime_config_abstains_below_visible_threshold(self) -> None:
        decision = choose_runtime_skill(
            config(secondary_axis_threshold=0.06),
            {"estimated_action_bias": (0.05, 0.01)},
        )
        self.assertEqual(decision.skill_id, "abstain_and_escalate")
        self.assertEqual(decision.schedule, "none")

    def test_config_rejects_values_outside_bounded_search_space(self) -> None:
        self.assertEqual(validate_recovery_policy_config(config()).probe_steps_per_direction, 8)
        with self.assertRaisesRegex(ValueError, "probe_steps"):
            validate_recovery_policy_config(config(probe_steps_per_direction=6))
        with self.assertRaisesRegex(ValueError, "offer_abstain"):
            validate_recovery_policy_config(config(offer_abstain=False))

    def test_counterfactual_prefers_success_then_cost_then_simplicity(self) -> None:
        rows = [
            SkillOutcome("case1", "dominant_axis_repair", "whole", True, 90, 0.04, 1),
            SkillOutcome("case1", "simultaneous_xy_repair", "whole", True, 70, 0.04, 2),
            SkillOutcome("case1", "abstain_and_escalate", "none", False, 0, 0.2, 0),
        ]
        self.assertEqual(select_counterfactual_skill(rows).skill_id, "simultaneous_xy_repair")
        tied = [rows[0], SkillOutcome("case1", "simultaneous_xy_repair", "whole", True, 90, 0.04, 2), rows[2]]
        self.assertEqual(select_counterfactual_skill(tied).skill_id, "dominant_axis_repair")

    def test_counterfactual_abstains_when_every_repair_fails(self) -> None:
        rows = [
            SkillOutcome("case1", "dominant_axis_repair", "whole", False, 500, 0.3, 1),
            SkillOutcome("case1", "abstain_and_escalate", "none", False, 0, 0.2, 0),
        ]
        self.assertEqual(select_counterfactual_skill(rows).skill_id, "abstain_and_escalate")

    def test_budget_fails_closed_before_overrun(self) -> None:
        budget = ExperimentBudget(max_api_calls=2, max_environment_steps=100)
        budget.consume_api_call(2)
        budget.consume_environment_steps(100)
        with self.assertRaisesRegex(RuntimeError, "API-call"):
            budget.consume_api_call()
        with self.assertRaisesRegex(RuntimeError, "environment-step"):
            budget.consume_environment_steps(1)

    def test_noise_calibration_uses_failure_target_clipping_and_lower_tie(self) -> None:
        rows = [
            {"noise_std": 0.25, "failure_rate": 0.3, "clipped_step_fraction": 0.2},
            {"noise_std": 0.30, "failure_rate": 0.6, "clipped_step_fraction": 0.2},
            {"noise_std": 0.35, "failure_rate": 0.4, "clipped_step_fraction": 0.2},
            {"noise_std": 0.40, "failure_rate": 0.5, "clipped_step_fraction": 0.7},
        ]
        self.assertEqual(select_noise_calibration(rows)["noise_std"], 0.30)


if __name__ == "__main__":
    unittest.main()
