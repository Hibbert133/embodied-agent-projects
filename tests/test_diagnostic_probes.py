from __future__ import annotations

import unittest

from src.diagnostic_probes import BiasEstimate, ProbeResult, build_agent_probe_context, estimate_planar_bias, summarize_probe_consistency
from src.recovery_agent import EpisodeEvidence, ExperimentProposal, PlannerHistoryItem, ProbeGuidedRecoveryPlanner


def probe(direction: str, command: tuple[float, float], velocity: tuple[float, float]) -> ProbeResult:
    steps = 8
    displacement = (velocity[0] * steps, velocity[1] * steps, 0.0)
    return ProbeResult(
        seed=100,
        direction=direction,
        commanded_action=(command[0], command[1], 0.0, 0.0),
        steps=steps,
        start_gripper_position=(0.0, 0.0, 0.0),
        end_gripper_position=displacement,
        gripper_displacement=displacement,
        minimum_gripper_object_distance=0.2,
        object_displacement=0.0,
    )


class DiagnosticProbeTest(unittest.TestCase):
    def test_repeat_consistency_separates_stable_and_variable_visible_estimates(self) -> None:
        def estimate(x: float, y: float) -> BiasEstimate:
            return BiasEstimate("x", "positive", (x, y), (1.0, 1.0), 0.01, 0.8, "x", "negative")
        stable = summarize_probe_consistency([estimate(0.1, 0.0)] * 4)
        variable = summarize_probe_consistency([
            estimate(0.1, 0.0), estimate(-0.1, 0.08), estimate(0.02, -0.1), estimate(0.15, 0.1)
        ])
        self.assertAlmostEqual(stable.estimated_bias_std_norm, 0.0)
        self.assertGreater(variable.estimated_bias_std_norm, 0.05)
        self.assertLess(variable.dominant_axis_sign_agreement, 1.0)
    def test_symmetric_estimator_recovers_axis_sign_and_opposing_correction(self) -> None:
        # Local synthetic dynamics: velocity = 0.5 * command + [0.03, 0.005].
        rows = [
            probe("x_positive", (0.2, 0.0), (0.13, 0.005)),
            probe("x_negative", (-0.2, 0.0), (-0.07, 0.005)),
            probe("y_positive", (0.0, 0.2), (0.03, 0.105)),
            probe("y_negative", (0.0, -0.2), (0.03, -0.095)),
        ]
        estimate = estimate_planar_bias(rows)
        self.assertEqual(estimate.dominant_axis, "x")
        self.assertEqual(estimate.estimated_direction, "positive")
        self.assertEqual(estimate.recommended_correction_direction, "negative")
        self.assertAlmostEqual(estimate.estimated_drift_per_step[0], 0.03)
        self.assertAlmostEqual(estimate.axis_response_gain[0], 0.5)

    def test_estimator_is_deterministic_and_agent_output_has_no_oracle_labels(self) -> None:
        rows = [
            probe("x_positive", (0.2, 0.0), (0.09, -0.02)),
            probe("x_negative", (-0.2, 0.0), (-0.11, -0.02)),
            probe("y_positive", (0.0, 0.2), (-0.01, 0.08)),
            probe("y_negative", (0.0, -0.2), (-0.01, -0.12)),
        ]
        first = estimate_planar_bias(rows)
        second = estimate_planar_bias(rows)
        self.assertEqual(first, second)
        forbidden = {"perturbation_type", "bias_axis", "bias_sign", "bias_magnitude"}
        for row in rows:
            self.assertFalse(forbidden & set(row.to_dict()))
        context_text = str(build_agent_probe_context(rows, first))
        for forbidden_field in forbidden:
            self.assertNotIn(forbidden_field, context_text)

    def test_estimator_requires_complete_unique_pairs(self) -> None:
        row = probe("x_positive", (0.2, 0.0), (0.1, 0.0))
        with self.assertRaisesRegex(ValueError, "missing"):
            estimate_planar_bias([row])
        with self.assertRaisesRegex(ValueError, "unique"):
            estimate_planar_bias([row, row, probe("x_negative", (-0.2, 0.0), (-0.1, 0.0)), probe("y_positive", (0.0, 0.2), (0.0, 0.1)), probe("y_negative", (0.0, -0.2), (0.0, -0.1))])

    def test_probe_guided_planner_opposes_estimated_drift(self) -> None:
        rows = [
            probe("x_positive", (0.2, 0.0), (0.13, 0.005)),
            probe("x_negative", (-0.2, 0.0), (-0.07, 0.005)),
            probe("y_positive", (0.0, 0.2), (0.03, 0.105)),
            probe("y_negative", (0.0, -0.2), (0.03, -0.095)),
        ]
        context = build_agent_probe_context(rows, estimate_planar_bias(rows))
        planner = ProbeGuidedRecoveryPlanner(context, allowed_magnitudes=(0.02, 0.06, 0.10))
        evidence = EpisodeEvidence(
            seed=100, success=False, steps=1, episode_return=0.0,
            final_object_goal_distance=0.2, minimum_gripper_object_distance=0.1,
            object_displacement=0.0, progress_to_goal=0.0, lateral_drift=0.0,
            mean_commanded_action=(0.0, 0.0, 0.0, 0.0),
            net_gripper_displacement=(0.0, 0.0, 0.0),
            final_object_position=(0.0, 0.0, 0.0), goal_position=(0.2, 0.0, 0.0),
            temporal_summary=(),
        )
        initial = ExperimentProposal("none", "none", 0.0, "initial", "measure", 1.0)
        output = planner.propose([PlannerHistoryItem(1, initial, evidence)], 1)
        self.assertEqual(output.proposal.correction_axis, "x")
        self.assertEqual(output.proposal.correction_direction, "negative")
        self.assertEqual(output.proposal.correction_magnitude, 0.06)


if __name__ == "__main__":
    unittest.main()
