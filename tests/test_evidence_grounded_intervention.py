from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.autoresearch import RecoveryPolicyConfig
from src.planner.evidence_grounded import (
    InterventionFamily,
    first_registered_probe_context,
    passive_correction_context,
    select_grounded_intervention,
)


class EvidenceGroundedInterventionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = RecoveryPolicyConfig.from_mapping(
            json.loads(
                Path("configs/autoresearch/recovery_policy_r1_c1.json").read_text(
                    encoding="utf-8"
                )
            )
        )
        cls.state = {
            "temporal_response": {
                "estimated_drift_xy": [0.001, -0.0005],
                "response_gain_xy": [0.01, 0.01],
                "normalized_residual_xy": [0.1, 0.2],
            }
        }

    def test_passive_stable_belief_builds_bounded_compensation(self) -> None:
        context = passive_correction_context(self.state)
        plan = select_grounded_intervention(
            plan_id="p1",
            evidence_id="e1",
            mechanism_belief="stable_bias",
            correction_context=context,
            recovery_config=self.config,
            evidence_source="initial_rollout",
        )
        self.assertEqual(plan.family, InterventionFamily.BIAS_COMPENSATION)
        self.assertEqual(plan.correction[2:], (0.0, 0.0))
        self.assertTrue(plan.requires_fresh_verification)

    def test_noise_belief_selects_zero_correction_retry(self) -> None:
        plan = select_grounded_intervention(
            plan_id="p2",
            evidence_id="e1",
            mechanism_belief="stochastic_noise",
            correction_context=None,
            recovery_config=self.config,
            evidence_source="initial_rollout",
        )
        self.assertEqual(plan.family, InterventionFamily.STOCHASTIC_RETRY)
        self.assertEqual(plan.correction, (0.0, 0.0, 0.0, 0.0))

    def test_registered_probe_uses_first_of_four_visible_repetitions(self) -> None:
        inference = {
            "estimated_drift_per_step": [0.001, 0.0],
            "axis_response_gain": [0.01, 0.01],
            "residual": 0.0,
        }
        repeated = {
            "probe_environment_steps": 64,
            "repetitions": [
                {"repeat_index": index, "transitions": [], "inference": inference}
                for index in range(4)
            ],
            "consistency": {"estimated_bias_std_norm": 0.0},
        }
        context = first_registered_probe_context(repeated)
        self.assertEqual(context["probe_environment_steps"], 64)
        self.assertEqual(context["inference"], inference)

    def test_oracle_fields_are_rejected(self) -> None:
        state = {**self.state, "condition_id": "fault_01"}
        with self.assertRaises(ValueError):
            passive_correction_context(state)


if __name__ == "__main__":
    unittest.main()
