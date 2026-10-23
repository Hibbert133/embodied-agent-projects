from __future__ import annotations

import unittest

from scripts.run_frozen_heldout_intervention import (
    intervention_changed,
    verification_status,
)
from src.planner.evidence_grounded import (
    GroundedInterventionPlan,
    InterventionFamily,
)


def plan(correction=(0.0, 0.0, 0.0, 0.0), family=InterventionFamily.STOCHASTIC_RETRY):
    return GroundedInterventionPlan(
        plan_id="plan",
        evidence_id="evidence",
        mechanism_belief=(
            "stochastic_noise" if family is InterventionFamily.STOCHASTIC_RETRY else "stable_bias"
        ),
        family=family,
        skill_id="retry" if family is InterventionFamily.STOCHASTIC_RETRY else "repair",
        schedule="whole",
        correction=correction,
        evidence_source="initial_rollout",
        requires_fresh_verification=True,
        rationale="test plan",
    )


class FrozenInterventionRunnerTest(unittest.TestCase):
    def test_verification_status_is_frozen_and_ordered(self) -> None:
        self.assertEqual(verification_status(True, 0.2, 0.3), "ACCEPTED")
        self.assertEqual(verification_status(False, 0.2, 0.3), "INCONCLUSIVE")
        self.assertEqual(verification_status(False, 0.3, 0.3), "REJECTED")

    def test_intervention_change_uses_executed_configuration(self) -> None:
        retry = plan()
        same_retry = plan()
        compensation = plan(
            correction=(-0.1, 0.0, 0.0, 0.0),
            family=InterventionFamily.BIAS_COMPENSATION,
        )
        self.assertFalse(intervention_changed(retry, same_retry))
        self.assertTrue(intervention_changed(retry, compensation))


if __name__ == "__main__":
    unittest.main()
