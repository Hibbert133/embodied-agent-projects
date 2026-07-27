from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.trajectory import TrajectoryRecorder, TrajectoryStep


class TrajectoryTest(unittest.TestCase):
    def make_step(self, *, step: int, success: bool) -> TrajectoryStep:
        return TrajectoryStep.from_transition(
            episode_id=1,
            seed=42,
            step=step,
            observation=np.array([1.0, 2.5], dtype=np.float32),
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
        self.assertEqual(
            set(data),
            {
                "episode_id",
                "seed",
                "step",
                "observation",
                "action",
                "raw_action",
                "perturbed_action",
                "executed_action",
                "was_clipped",
                "reward",
                "success",
                "terminated",
                "truncated",
            },
        )

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
