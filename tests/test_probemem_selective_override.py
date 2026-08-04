import unittest

from src.probe.directional import BiasEstimate
from src.probemem.models import InterventionSkill
from src.probemem.selective_override import (
    agreed_memory_preference,
    assess_probe_ambiguity,
    guard_memory_override,
)


COMP = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def estimate(bias_x: float) -> BiasEstimate:
    return BiasEstimate(
        dominant_axis="x", estimated_direction="positive",
        estimated_drift_per_step=(bias_x, 0.0), axis_response_gain=(1.0, 1.0),
        residual=0.0, confidence=1.0,
        recommended_correction_axis="x", recommended_correction_direction="negative",
    )


def memory_payload(comp_global: float, retry_global: float, comp_recent: float, retry_recent: float) -> dict:
    return {
        "memory_cutoff_episode_id": 21,
        "candidate_actions": {
            COMP.value: {
                "global": {"accepted_probability": comp_global},
                "recent": {"accepted_probability": comp_recent},
            },
            RETRY.value: {
                "global": {"accepted_probability": retry_global},
                "recent": {"accepted_probability": retry_recent},
            },
        },
    }


class ProbeMemSelectiveOverrideTest(unittest.TestCase):
    def test_stable_leave_one_out_decision_bypasses_glm(self) -> None:
        assessment = assess_probe_ambiguity(tuple(estimate(0.02) for _ in range(4)))
        self.assertFalse(assessment.ambiguous)
        self.assertFalse(assessment.should_call_glm)
        decision = guard_memory_override(
            assessment=assessment, proposed_skill=RETRY,
            memory_payload=memory_payload(0.1, 0.9, 0.1, 0.9),
        )
        self.assertEqual(decision.selected_skill, COMP)
        self.assertFalse(decision.override_authorized)

    def test_outlier_sensitive_probe_is_ambiguous_without_outcomes(self) -> None:
        assessment = assess_probe_ambiguity((estimate(0.0), estimate(0.0), estimate(0.0), estimate(0.4)))
        self.assertTrue(assessment.ambiguous)
        self.assertTrue(assessment.should_call_glm)
        self.assertEqual(assessment.full_action, RETRY)
        self.assertIn(COMP, assessment.leave_one_out_actions)

    def test_override_requires_global_recent_agreement(self) -> None:
        assessment = assess_probe_ambiguity((estimate(0.0), estimate(0.0), estimate(0.0), estimate(0.4)))
        agreeing = memory_payload(0.8, 0.2, 0.7, 0.3)
        self.assertEqual(agreed_memory_preference(agreeing), COMP)
        accepted = guard_memory_override(
            assessment=assessment, proposed_skill=COMP, memory_payload=agreeing,
        )
        self.assertTrue(accepted.override_authorized)
        self.assertEqual(accepted.selected_skill, COMP)

        conflicting = memory_payload(0.8, 0.2, 0.3, 0.7)
        self.assertIsNone(agreed_memory_preference(conflicting))
        rejected = guard_memory_override(
            assessment=assessment, proposed_skill=COMP, memory_payload=conflicting,
        )
        self.assertFalse(rejected.override_authorized)
        self.assertTrue(rejected.fallback_used)
        self.assertEqual(rejected.selected_skill, RETRY)

    def test_abstaining_proposal_falls_back_in_primary_policy(self) -> None:
        assessment = assess_probe_ambiguity((estimate(0.0), estimate(0.0), estimate(0.0), estimate(0.4)))
        decision = guard_memory_override(
            assessment=assessment, proposed_skill=None,
            memory_payload=memory_payload(0.5, 0.5, 0.5, 0.5),
        )
        self.assertTrue(decision.fallback_used)
        self.assertEqual(decision.selected_skill, assessment.full_action)


if __name__ == "__main__":
    unittest.main()
