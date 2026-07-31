from __future__ import annotations

from dataclasses import replace
import unittest

import numpy as np

from src.reasoning import (
    EvidenceSource,
    build_structured_evidence_state,
)
from src.uncertainty import (
    EvidenceAction,
    EvidenceDecisionKind,
    select_evidence_action,
)


def observation(hand_x: float, hand_y: float) -> list[float]:
    value = np.zeros(39, dtype=float)
    value[0:3] = [hand_x, hand_y, 0.2]
    value[4:7] = [0.5, 0.5, 0.02]
    value[-3:] = [0.8, 0.8, 0.02]
    return value.tolist()


def agent_transitions(*, success: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    current = observation(0.0, 0.0)
    for index in range(12):
        action_x = 0.5 if index % 2 == 0 else -0.5
        action_y = 0.25 if index % 3 else -0.25
        next_value = np.asarray(current, dtype=float)
        next_value[0] += 0.01 * action_x + 0.001
        next_value[1] += 0.01 * action_y - 0.001
        next_observation = next_value.tolist()
        final_success = success and index == 11
        rows.append(
            {
                "schema_version": 2,
                "episode_id": 1,
                "seed": 330,
                "step": index + 1,
                "observation": current,
                "next_observation": next_observation,
                "commanded_action": [action_x, action_y, 0.0, 1.0],
                "reward": 0.0,
                "success": final_success,
                "terminated": final_success,
                "truncated": False,
                "task_progress_metrics": {},
            }
        )
        current = next_observation
    return rows


class StructuredEvidenceTest(unittest.TestCase):
    def build(self, *, success: bool = False):
        return build_structured_evidence_state(
            agent_transitions(success=success),
            evidence_id="failed-rollout-330",
            historical_verified_case_count=3,
        )

    def test_builds_causal_state_and_packet(self) -> None:
        state = self.build()
        self.assertEqual(state.schema_version, 1)
        self.assertEqual(state.source, EvidenceSource.FAILED_ROLLOUT)
        self.assertEqual(state.seed, 330)
        self.assertEqual(state.environment_step_cost, 12)
        self.assertTrue(state.decision_required)
        self.assertEqual(state.historical_verified_case_count, 3)
        self.assertEqual(state.temporal_response.sample_count, 12)
        self.assertEqual(state.phase_response.sample_counts["approach"], 12)
        self.assertIn("repeat_consistency", state.missing_evidence)
        packet = state.to_evidence_packet()
        self.assertEqual(packet.evidence_id, state.evidence_id)
        self.assertEqual(packet.step_count, 12)
        self.assertNotIn("perturbation_type", packet.payload)
        self.assertNotIn("seed", packet.payload)

    def test_successful_initial_rollout_requires_no_decision(self) -> None:
        state = self.build(success=True)
        self.assertFalse(state.decision_required)
        decision = select_evidence_action(state, 0, decision_id="decision-success")
        self.assertEqual(decision.action, EvidenceDecisionKind.CONTINUE)
        self.assertEqual(decision.reserved_probe_budget, 0)
        self.assertEqual(decision.reserved_verification_budget, 0)

    def test_direct_and_nested_oracle_fields_fail_closed(self) -> None:
        direct = agent_transitions()
        direct[0]["raw_action"] = [0.0, 0.0, 0.0, 1.0]
        with self.assertRaisesRegex(ValueError, "Oracle-only"):
            build_structured_evidence_state(direct, evidence_id="direct-leak")

        nested = agent_transitions()
        nested[0]["task_progress_metrics"] = {"condition_id": "fault_01"}
        with self.assertRaisesRegex(ValueError, "Oracle-only"):
            build_structured_evidence_state(nested, evidence_id="nested-leak")

        evaluator_label = agent_transitions()
        evaluator_label[0]["task_progress_metrics"] = {
            "diagnostic_probe_needed": True
        }
        with self.assertRaisesRegex(ValueError, "Oracle-only"):
            build_structured_evidence_state(
                evaluator_label, evidence_id="evaluator-label-leak"
            )

    def test_attempt_id_above_v1_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "attempt_id"):
            build_structured_evidence_state(
                agent_transitions(), evidence_id="late-attempt", attempt_id=3
            )

    def test_high_score_reserves_probe_and_verification(self) -> None:
        state = self.build()
        high = replace(
            state,
            phase_response=replace(state.phase_response, phase_inconsistency=0.95),
        )
        decision = select_evidence_action(
            high, 564, decision_id="decision-request"
        )
        self.assertEqual(
            decision.action, EvidenceDecisionKind.REQUEST_DIAGNOSTIC_PROBE
        )
        self.assertEqual(decision.reserved_probe_budget, 64)
        self.assertEqual(decision.reserved_verification_budget, 500)
        self.assertEqual(
            decision.to_legacy_decision().action, EvidenceAction.REQUEST_PROBE
        )

    def test_probe_fails_closed_when_verification_reservation_is_short(self) -> None:
        state = self.build()
        high = replace(
            state,
            phase_response=replace(state.phase_response, phase_inconsistency=0.95),
        )
        decision = select_evidence_action(
            high, 563, decision_id="decision-abstain"
        )
        self.assertEqual(decision.action, EvidenceDecisionKind.ABSTAIN)
        self.assertEqual(
            decision.budget_rejection_reason,
            "insufficient_probe_and_verification_budget",
        )

    def test_low_score_continues_only_with_verification_budget(self) -> None:
        state = self.build()
        low = replace(
            state,
            phase_response=replace(state.phase_response, phase_inconsistency=0.2),
        )
        continued = select_evidence_action(
            low, 500, decision_id="decision-continue"
        )
        self.assertEqual(continued.action, EvidenceDecisionKind.CONTINUE)
        self.assertEqual(continued.reserved_verification_budget, 500)
        abstained = select_evidence_action(
            low, 499, decision_id="decision-no-verification"
        )
        self.assertEqual(abstained.action, EvidenceDecisionKind.ABSTAIN)
        self.assertEqual(
            abstained.budget_rejection_reason, "insufficient_verification_budget"
        )


if __name__ == "__main__":
    unittest.main()
