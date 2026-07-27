from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.trajectory import TrajectoryRecorder, TrajectoryStep
from src.trajectory_views import AGENT_FIELDS, FORBIDDEN_AGENT_FIELDS, build_agent_view


class TrajectoryTest(unittest.TestCase):
    def make_step(self, *, step: int, success: bool) -> TrajectoryStep:
        return TrajectoryStep.from_transition(
            episode_id=1,
            seed=42,
            step=step,
            observation=np.array([1.0, 2.5], dtype=np.float32),
            next_observation=np.array([1.5, 3.0], dtype=np.float32),
            action=np.array([0.1, -0.2], dtype=np.float32),
            reward=np.float32(3.25),
            success=np.bool_(success),
            terminated=np.bool_(False),
            truncated=np.bool_(False),
        )

    def test_numpy_arrays_and_scalars_are_serializable(self) -> None:
        step = self.make_step(step=1, success=True)
        serialized = json.dumps(step.to_dict())
        data = json.loads(serialized)

        self.assertEqual(data["observation"], [1.0, 2.5])
        self.assertAlmostEqual(data["action"][0], 0.1, places=6)
        self.assertEqual(data["reward"], 3.25)
        self.assertIs(data["success"], True)
        self.assertIsInstance(data["seed"], int)

    def test_jsonl_save_writes_required_fields(self) -> None:
        recorder = TrajectoryRecorder(episode_id=1, seed=42)
        recorder.record(self.make_step(step=1, success=False))
        recorder.record(self.make_step(step=2, success=True))

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "nested" / "trajectory.jsonl"
            saved_path = recorder.save_jsonl(path)
            lines = saved_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        data = json.loads(lines[0])
        self.assertTrue({
                "episode_id",
                "seed",
                "step",
                "observation",
                "next_observation",
                "action",
                "raw_action",
                "perturbed_action",
                "executed_action",
                "was_clipped",
                "reward",
                "success",
                "terminated",
                "truncated", "schema_version", "commanded_action", "task_progress_metrics",
                "perturbation_type", "perturbation_parameters", "clipped_element_count"
            }.issubset(data))

    def test_agent_and_oracle_views(self) -> None:
        step = TrajectoryStep.from_transition(episode_id=1,seed=42,step=1,observation=[1,2],next_observation=[2,3],action=[.2,.2],raw_action=[.1,.2],perturbed_action=[.2,.2],reward=1,success=False,terminated=False,truncated=False,perturbation_type="action_bias",perturbation_parameters={"bias":[.1,0]})
        agent=step.to_agent_view(); oracle=step.to_oracle_view()
        self.assertEqual(set(agent), set(AGENT_FIELDS))
        self.assertFalse(FORBIDDEN_AGENT_FIELDS & set(agent))
        self.assertEqual(agent["commanded_action"], oracle["raw_action"])
        self.assertNotEqual(agent["commanded_action"], oracle["perturbed_action"])
        self.assertEqual(oracle["perturbation_type"],"action_bias")
        self.assertIn("executed_action",oracle)

    def test_agent_view_rejects_missing_required_fields(self) -> None:
        record = self.make_step(step=1, success=False).to_dict()
        del record["next_observation"]
        with self.assertRaisesRegex(ValueError, "next_observation"):
            build_agent_view(record)

    def test_schema_version_is_two(self) -> None:
        self.assertEqual(self.make_step(step=1, success=False).schema_version, 2)

    def test_success_never_changes_back_to_false(self) -> None:
        recorder = TrajectoryRecorder(episode_id=1, seed=42)
        recorder.record(self.make_step(step=1, success=False))
        recorder.record(self.make_step(step=2, success=True))
        recorder.record(self.make_step(step=3, success=False))

        self.assertEqual(
            [step.success for step in recorder.steps], [False, True, True]
        )


if __name__ == "__main__":
    unittest.main()
