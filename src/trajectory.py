"""Typed trajectory records with NumPy-safe JSONL persistence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


@dataclass(frozen=True)
class TrajectoryStep:
    """One action and its resulting environment transition."""

    episode_id: int
    seed: int
    step: int
    observation: list[float]
    # ``action`` remains an alias for executed_action for old JSONL consumers.
    action: list[float]
    raw_action: list[float]
    perturbed_action: list[float]
    executed_action: list[float]
    was_clipped: bool
    reward: float
    success: bool
    terminated: bool
    truncated: bool

    @classmethod
    def from_transition(
        cls,
        *,
        episode_id: int,
        seed: int,
        step: int,
        observation: Sequence[float] | np.ndarray,
        action: Sequence[float] | np.ndarray,
        reward: float | np.generic,
        success: bool | np.bool_,
        terminated: bool | np.bool_,
        truncated: bool | np.bool_,
        raw_action: Sequence[float] | np.ndarray | None = None,
        perturbed_action: Sequence[float] | np.ndarray | None = None,
        executed_action: Sequence[float] | np.ndarray | None = None,
        was_clipped: bool | np.bool_ = False,
    ) -> "TrajectoryStep":
        if episode_id <= 0:
            raise ValueError("episode_id must be a positive integer")
        if step <= 0:
            raise ValueError("step must be a positive integer")
        if raw_action is None:
            raw_action = action
        if perturbed_action is None:
            perturbed_action = raw_action
        if executed_action is None:
            executed_action = action
        executed_list = (
            np.asarray(executed_action, dtype=float).reshape(-1).tolist()
        )
        return cls(
            episode_id=int(episode_id),
            seed=int(seed),
            step=int(step),
            observation=np.asarray(observation, dtype=float).reshape(-1).tolist(),
            action=executed_list,
            raw_action=np.asarray(raw_action, dtype=float).reshape(-1).tolist(),
            perturbed_action=(
                np.asarray(perturbed_action, dtype=float).reshape(-1).tolist()
            ),
            executed_action=executed_list,
            was_clipped=bool(was_clipped),
            reward=float(reward),
            success=bool(success),
            terminated=bool(terminated),
            truncated=bool(truncated),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrajectoryRecorder:
    """Collect one episode while enforcing sequential and monotonic state."""

    def __init__(self, episode_id: int, seed: int) -> None:
        if episode_id <= 0:
            raise ValueError("episode_id must be a positive integer")
        self.episode_id = int(episode_id)
        self.seed = int(seed)
        self._steps: list[TrajectoryStep] = []
        self._success_reached = False

    @property
    def steps(self) -> tuple[TrajectoryStep, ...]:
        return tuple(self._steps)

    def record(self, transition: TrajectoryStep) -> None:
        expected_step = len(self._steps) + 1
        if transition.episode_id != self.episode_id or transition.seed != self.seed:
            raise ValueError("transition episode_id or seed does not match recorder")
        if transition.step != expected_step:
            raise ValueError(
                f"expected trajectory step {expected_step}, got {transition.step}"
            )

        self._success_reached = self._success_reached or transition.success
        if transition.success != self._success_reached:
            transition = replace(transition, success=self._success_reached)
        self._steps.append(transition)

    def record_transition(
        self,
        *,
        step: int,
        observation: Sequence[float] | np.ndarray,
        action: Sequence[float] | np.ndarray,
        reward: float | np.generic,
        success: bool | np.bool_,
        terminated: bool | np.bool_,
        truncated: bool | np.bool_,
        raw_action: Sequence[float] | np.ndarray | None = None,
        perturbed_action: Sequence[float] | np.ndarray | None = None,
        executed_action: Sequence[float] | np.ndarray | None = None,
        was_clipped: bool | np.bool_ = False,
    ) -> None:
        self.record(
            TrajectoryStep.from_transition(
                episode_id=self.episode_id,
                seed=self.seed,
                step=step,
                observation=observation,
                action=action,
                raw_action=raw_action,
                perturbed_action=perturbed_action,
                executed_action=executed_action,
                was_clipped=was_clipped,
                reward=reward,
                success=success,
                terminated=terminated,
                truncated=truncated,
            )
        )

    def save_jsonl(self, path: Path | str) -> Path:
        return save_jsonl(self._steps, path)


def save_jsonl(steps: Iterable[TrajectoryStep], path: Path | str) -> Path:
    """Atomically write one JSON object per line using UTF-8."""

    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            for step in steps:
                file.write(json.dumps(step.to_dict(), ensure_ascii=False) + "\n")
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output
