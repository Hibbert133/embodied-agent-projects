from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

import numpy as np

from src.anthropic_recovery_planner import AnthropicRecoveryPlanner, extract_proposal_json
from src.openai_recovery_planner import OpenAIRecoveryPlanner
from src.recovery_agent import (
    CompensatedPolicy,
    EpisodeEvidence,
    ExperimentProposal,
    PlannerHistoryItem,
    RuleBasedRecoveryPlanner,
    TrialOutcome,
    build_episode_evidence,
    run_budgeted_recovery,
    validate_proposal,
)
from src.rollout import EpisodeResult
from src.trajectory import TrajectoryStep
from src.trajectory_views import FORBIDDEN_AGENT_FIELDS


def metrics(step: int) -> dict[str, object]:
    return {
        "gripper_position": [0.0, 0.0, 0.0],
        "object_position": [0.1 + step * 0.01, 0.0, 0.0],
        "goal_position": [0.2, 0.0, 0.0],
        "gripper_object_distance": 0.1,
        "object_goal_distance": 0.1 - step * 0.01,
        "object_displacement_from_start": step * 0.01,
        "progress_to_goal": step * 0.01,
        "lateral_drift": 0.0,
    }


def record(step: int, success: bool = False) -> dict[str, object]:
    observation = np.zeros(39)
    next_observation = np.zeros(39)
    observation[0] = step - 1
    next_observation[0] = step
    return TrajectoryStep.from_transition(
        episode_id=1,
        seed=100,
        step=step,
        observation=observation,
        next_observation=next_observation,
        action=[0.1, 0.0, 0.0, 0.5],
        reward=1.0,
        success=success,
        terminated=False,
        truncated=False,
        task_progress_metrics=metrics(step),
    ).to_dict()


def episode_result(success: bool) -> EpisodeResult:
    return EpisodeResult(
        success=success,
        steps=2,
        episode_return=2.0,
        elapsed_time_ms=1.0,
        clipped_step_count=0,
        clipped_step_fraction=0.0,
        clipped_element_count=0,
        clipped_element_fraction=0.0,
        final_object_goal_distance=0.08,
        min_gripper_object_distance=0.1,
        object_displacement=0.02,
        progress_to_goal=0.02,
    )


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(nested_keys(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(nested_keys(item) for item in value))
    return set()


class BasePolicy:
    def get_action(self, observation: np.ndarray) -> np.ndarray:
        del observation
        return np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)


class FakeResponses:
    def __init__(self, proposal: dict[str, object]) -> None:
        self.proposal = proposal
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(
            id="resp_test",
            model="test-model-snapshot",
            output_text=json.dumps(self.proposal),
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15),
        )


class FakeMessages:
    def __init__(self, proposal: dict[str, object]) -> None:
        self.proposal = proposal
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(
            id="msg_test",
            model="glm-test-snapshot",
            content=[SimpleNamespace(type="text", text=json.dumps(self.proposal))],
            usage=SimpleNamespace(input_tokens=20, output_tokens=10),
        )


class RecoveryAgentTest(unittest.TestCase):
    def test_evidence_uses_only_agent_view_and_checks_continuity(self) -> None:
        first = record(1)
        second = record(2)
        second["observation"] = first["next_observation"]
        evidence = build_episode_evidence([first, second])
        self.assertEqual(evidence.steps, 2)
        self.assertFalse(FORBIDDEN_AGENT_FIELDS & nested_keys(evidence.to_dict()))

        second["observation"] = [99.0] * 39
        with self.assertRaisesRegex(ValueError, "continuous"):
            build_episode_evidence([first, second])

    def test_proposal_validation_rejects_out_of_bounds_values(self) -> None:
        proposal = ExperimentProposal("x", "positive", 0.03, "test", "test", 0.5)
        with self.assertRaisesRegex(ValueError, "allowed"):
            validate_proposal(proposal)
        with self.assertRaisesRegex(ValueError, "confidence"):
            validate_proposal(ExperimentProposal("x", "positive", 0.02, "a", "b", 1.5))

    def test_compensated_policy_changes_only_xy_command(self) -> None:
        policy = CompensatedPolicy(BasePolicy(), [0.02, -0.04, 0.0, 0.0])
        action = policy.get_action(np.zeros(39))
        np.testing.assert_allclose(action, [0.12, 0.16, 0.3, 0.4])
        with self.assertRaisesRegex(ValueError, "x or y"):
            CompensatedPolicy(BasePolicy(), [0.0, 0.0, 0.1, 0.0])

    def test_budgeted_loop_stops_on_success(self) -> None:
        calls: list[np.ndarray] = []
        observed_trials: list[int] = []

        def runner(trial: int, correction: np.ndarray) -> TrialOutcome:
            calls.append(correction)
            rows = [record(1), record(2, success=trial == 2)]
            rows[1]["observation"] = rows[0]["next_observation"]
            return TrialOutcome(episode_result(trial == 2), tuple(rows))

        result = run_budgeted_recovery(
            RuleBasedRecoveryPlanner(allowed_magnitudes=(0.02, 0.04)),
            runner,
            max_trials=5,
            allowed_magnitudes=(0.02, 0.04),
            trial_observer=lambda trial: observed_trials.append(trial.trial),
        )
        self.assertTrue(result.success)
        self.assertEqual(result.trials_used, 2)
        np.testing.assert_array_equal(calls[0], np.zeros(4))
        self.assertNotEqual(float(np.linalg.norm(calls[1])), 0.0)
        self.assertEqual(observed_trials, [1, 2])

    def test_active_planner_is_initialized_only_after_initial_failure(self) -> None:
        events: list[str] = []

        def runner(trial: int, correction: np.ndarray) -> TrialOutcome:
            del correction
            events.append(f"trial{trial}")
            rows = [record(1), record(2, success=trial == 2)]
            rows[1]["observation"] = rows[0]["next_observation"]
            return TrialOutcome(episode_result(trial == 2), tuple(rows))

        def initialize() -> RuleBasedRecoveryPlanner:
            events.append("probe")
            return RuleBasedRecoveryPlanner(allowed_magnitudes=(0.02,))

        result = run_budgeted_recovery(
            RuleBasedRecoveryPlanner(allowed_magnitudes=(0.02,)),
            runner,
            max_trials=2,
            allowed_magnitudes=(0.02,),
            planner_after_initial_failure=initialize,
        )
        self.assertTrue(result.success)
        self.assertEqual(events, ["trial1", "probe", "trial2"])

    def test_openai_planner_sends_only_compact_evidence(self) -> None:
        response_proposal = {
            "correction_axis": "x",
            "correction_direction": "negative",
            "correction_magnitude": 0.02,
            "hypothesis": "Object remains displaced along x.",
            "expected_effect": "Reduce x displacement.",
            "confidence": 0.7,
            "stop": False,
        }
        responses = FakeResponses(response_proposal)
        client = SimpleNamespace(responses=responses)
        evidence = EpisodeEvidence(
            seed=100,
            success=False,
            steps=2,
            episode_return=2.0,
            final_object_goal_distance=0.08,
            minimum_gripper_object_distance=0.1,
            object_displacement=0.02,
            progress_to_goal=0.02,
            lateral_drift=0.0,
            mean_commanded_action=(0.1, 0.0, 0.0, 0.5),
            net_gripper_displacement=(0.01, 0.0, 0.0),
            final_object_position=(0.12, 0.0, 0.0),
            goal_position=(0.2, 0.0, 0.0),
            temporal_summary=(),
        )
        planner = OpenAIRecoveryPlanner(
            model="test-model", allowed_magnitudes=(0.0, 0.02), client=client
        )
        initial = ExperimentProposal("none", "none", 0.0, "initial", "measure", 1.0)
        output = planner.propose(
            [PlannerHistoryItem(1, initial, evidence)], remaining_budget=4
        )
        self.assertEqual(output.proposal.correction_direction, "negative")
        self.assertEqual(output.audit["response_id"], "resp_test")
        payload = json.loads(str(responses.kwargs["input"]))
        self.assertFalse(FORBIDDEN_AGENT_FIELDS & nested_keys(payload))
        self.assertNotIn("OPENAI_API_KEY", str(payload))

    def test_anthropic_planner_sends_only_agent_visible_evidence(self) -> None:
        proposal = {
            "correction_axis": "x",
            "correction_direction": "negative",
            "correction_magnitude": 0.02,
            "hypothesis": "Observed x motion is inconsistent with commanded motion.",
            "expected_effect": "Reduce x drift.",
            "confidence": 0.6,
            "stop": False,
        }
        messages = FakeMessages(proposal)
        client = SimpleNamespace(messages=messages)
        evidence = EpisodeEvidence(
            seed=100, success=False, steps=2, episode_return=2.0,
            final_object_goal_distance=0.08, minimum_gripper_object_distance=0.1,
            object_displacement=0.02, progress_to_goal=0.02, lateral_drift=0.0,
            mean_commanded_action=(0.1, 0.0, 0.0, 0.5),
            net_gripper_displacement=(0.01, 0.0, 0.0),
            final_object_position=(0.12, 0.0, 0.0), goal_position=(0.2, 0.0, 0.0),
            temporal_summary=(),
        )
        initial = ExperimentProposal("none", "none", 0.0, "initial", "measure", 1.0)
        planner = AnthropicRecoveryPlanner(
            model="glm-test", base_url="https://example.invalid/anthropic",
            allowed_magnitudes=(0.0, 0.02), client=client,
            diagnostic_context={
                "protocol": "symmetric_world_frame_xy_v1",
                "inference": {
                    "dominant_axis": "x",
                    "estimated_direction": "positive",
                    "recommended_correction_direction": "negative",
                },
            },
        )
        output = planner.propose([PlannerHistoryItem(1, initial, evidence)], 4)
        self.assertEqual(output.proposal.correction_axis, "x")
        self.assertEqual(output.audit["response_id"], "msg_test")
        prompt = str(messages.kwargs["messages"])
        self.assertFalse(FORBIDDEN_AGENT_FIELDS & nested_keys(messages.kwargs["messages"]))
        self.assertNotIn("ANTHROPIC_API_KEY", prompt)
        self.assertIn("symmetric_world_frame_xy_v1", prompt)

    def test_anthropic_json_extraction_handles_reasoning_and_rejects_ambiguity(self) -> None:
        proposal = {
            "correction_axis": "x", "correction_direction": "negative",
            "correction_magnitude": 0.02, "hypothesis": "h",
            "expected_effect": "e", "confidence": 0.5, "stop": False,
        }
        wrapped = "<think>compare trial evidence</think>\n```json\n" + json.dumps(proposal) + "\n```"
        self.assertEqual(extract_proposal_json(wrapped), proposal)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            extract_proposal_json(json.dumps(proposal) + "\n" + json.dumps({**proposal, "confidence": 0.6}))
        with self.assertRaisesRegex(ValueError, "no proposal"):
            extract_proposal_json("I cannot decide yet")


if __name__ == "__main__":
    unittest.main()
