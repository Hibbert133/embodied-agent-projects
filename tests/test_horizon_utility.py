import unittest

from src.horizon_utility import build_prefix_evidence
from src.trajectory import TrajectoryStep


def record(step: int, *, x: float, success: bool = False):
    transition = TrajectoryStep.from_transition(
        episode_id=1,
        seed=1,
        step=step,
        observation=[0.0, 0.0],
        next_observation=[0.0, 0.0],
        action=[0.0],
        reward=0.0,
        success=success,
        terminated=False,
        truncated=False,
        task_progress_metrics={
            "gripper_position": [0.0, 0.0, 0.0],
            "object_position": [x, 0.0, 0.0],
            "goal_position": [1.0, 0.0, 0.0],
            "gripper_object_distance": 0.04 if step >= 2 else 0.1,
            "object_goal_distance": 1.0 - x,
            "object_displacement_from_start": x,
            "progress_to_goal": x,
            "lateral_drift": 0.0,
        },
    )
    return transition.to_agent_view()


class HorizonUtilityTest(unittest.TestCase):
    def test_prefix_is_causal_and_reports_temporal_features(self):
        records = [record(1, x=0.0), record(2, x=0.02), record(3, x=0.03, success=True)]
        evidence = build_prefix_evidence(records, candidate_id="repair", horizon=2)
        self.assertEqual(evidence["observed_steps"], 2)
        self.assertFalse(evidence["success_within_probe_budget"])
        self.assertEqual(evidence["first_near_contact_step"], 2)
        self.assertEqual(evidence["first_object_motion_step"], 2)
        self.assertAlmostEqual(evidence["progress_to_goal"], 0.02)

    def test_noncontiguous_agent_trace_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "contiguous"):
            build_prefix_evidence([record(2, x=0.0)], candidate_id="repair", horizon=2)


if __name__ == "__main__":
    unittest.main()
