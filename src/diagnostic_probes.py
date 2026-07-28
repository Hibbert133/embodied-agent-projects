"""Leakage-safe active probes for estimating planar execution bias.

The estimator consumes only commanded actions and observed gripper state
transitions. Hidden perturbation parameters are deliberately absent from all
agent-visible dataclasses; they belong only in downstream audit tables.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from src.task_metrics import extract_push_positions


PROBE_DIRECTIONS: tuple[tuple[str, np.ndarray], ...] = (
    ("x_positive", np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)),
    ("x_negative", np.array([-1.0, 0.0, 0.0, 0.0], dtype=np.float32)),
    ("y_positive", np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)),
    ("y_negative", np.array([0.0, -1.0, 0.0, 0.0], dtype=np.float32)),
)


@dataclass(frozen=True)
class ProbeResult:
    """One reset-and-probe result containing causally available measurements."""

    seed: int
    direction: str
    commanded_action: tuple[float, float, float, float]
    steps: int
    start_gripper_position: tuple[float, float, float]
    end_gripper_position: tuple[float, float, float]
    gripper_displacement: tuple[float, float, float]
    minimum_gripper_object_distance: float
    object_displacement: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BiasEstimate:
    """Agent-side estimate, not an injected-bias label."""

    dominant_axis: str
    estimated_direction: str
    estimated_drift_per_step: tuple[float, float]
    axis_response_gain: tuple[float, float]
    residual: float
    confidence: float
    recommended_correction_axis: str
    recommended_correction_direction: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_agent_probe_context(
    results: Sequence[ProbeResult], estimate: BiasEstimate
) -> dict[str, Any]:
    """Build the only probe payload permitted to reach a recovery planner."""

    return {
        "protocol": "symmetric_world_frame_xy_v1",
        "probe_environment_steps": sum(result.steps for result in results),
        "transitions": [result.to_dict() for result in results],
        "inference": estimate.to_dict(),
    }


StepFunction = Callable[[np.ndarray], tuple[np.ndarray, float, bool, bool, Mapping[str, Any]]]


def run_symmetric_probes(
    env_factory: Callable[[], Any],
    *,
    seed: int,
    perturbation_factory: Callable[[], Any],
    magnitude: float = 0.2,
    steps: int = 8,
) -> tuple[ProbeResult, ...]:
    """Run +x/-x/+y/-y from identical seeded resets.

    Each probe owns a fresh environment and perturbation instance. This keeps
    reset state identical and prevents stochastic state from leaking across
    probes. No rendering is performed.
    """

    if not 0.0 < magnitude <= 1.0 or steps <= 0:
        raise ValueError("probe magnitude must be in (0, 1] and steps must be positive")
    results: list[ProbeResult] = []
    for direction, unit_action in PROBE_DIRECTIONS:
        env = env_factory()
        perturbation = perturbation_factory()
        try:
            observation, _ = env.reset(seed=seed)
            perturbation.reset(seed)
            start_gripper, start_object, _ = extract_push_positions(observation)
            minimum_distance = float(np.linalg.norm(start_gripper - start_object))
            command = unit_action * np.float32(magnitude)
            completed = 0
            for _ in range(steps):
                perturbed = np.asarray(perturbation.apply(command), dtype=np.float32)
                executed = np.clip(perturbed, env.action_space.low, env.action_space.high)
                observation, _, terminated, truncated, _ = env.step(executed)
                gripper, object_position, _ = extract_push_positions(observation)
                minimum_distance = min(
                    minimum_distance, float(np.linalg.norm(gripper - object_position))
                )
                completed += 1
                if terminated or truncated:
                    break
            end_gripper, end_object, _ = extract_push_positions(observation)
            displacement = end_gripper - start_gripper
            results.append(
                ProbeResult(
                    seed=seed,
                    direction=direction,
                    commanded_action=tuple(float(x) for x in command),
                    steps=completed,
                    start_gripper_position=tuple(float(x) for x in start_gripper),
                    end_gripper_position=tuple(float(x) for x in end_gripper),
                    gripper_displacement=tuple(float(x) for x in displacement),
                    minimum_gripper_object_distance=minimum_distance,
                    object_displacement=float(np.linalg.norm(end_object - start_object)),
                )
            )
        finally:
            env.close()
    return tuple(results)


def estimate_planar_bias(results: Sequence[ProbeResult]) -> BiasEstimate:
    """Estimate common drift using symmetric-pair cancellation.

    For an approximately local response ``delta = gain * command + drift``, the
    average of positive and negative probe displacements cancels the command
    term. This is an inference from visible transitions, not Oracle bias access.
    """

    by_direction = {result.direction: result for result in results}
    required = {name for name, _ in PROBE_DIRECTIONS}
    missing = required - set(by_direction)
    if missing:
        raise ValueError(f"missing symmetric probe directions: {sorted(missing)}")
    if len(by_direction) != len(results):
        raise ValueError("probe directions must be unique")

    velocities: dict[str, np.ndarray] = {}
    commands: dict[str, np.ndarray] = {}
    for name in required:
        result = by_direction[name]
        if result.steps <= 0:
            raise ValueError("probe results must contain positive step counts")
        velocities[name] = np.asarray(result.gripper_displacement[:2]) / result.steps
        commands[name] = np.asarray(result.commanded_action[:2])

    pair_drifts = np.stack(
        [
            0.5 * (velocities["x_positive"] + velocities["x_negative"]),
            0.5 * (velocities["y_positive"] + velocities["y_negative"]),
        ]
    )
    drift = np.mean(pair_drifts, axis=0)
    residual = float(np.linalg.norm(pair_drifts[0] - pair_drifts[1]))
    gains = []
    for axis, positive, negative in (
        (0, "x_positive", "x_negative"),
        (1, "y_positive", "y_negative"),
    ):
        command_span = commands[positive][axis] - commands[negative][axis]
        if np.isclose(command_span, 0.0):
            raise ValueError("opposite probe commands must have a nonzero span")
        gains.append(float((velocities[positive][axis] - velocities[negative][axis]) / command_span))

    axis_index = int(np.argmax(np.abs(drift)))
    axis = ("x", "y")[axis_index]
    direction = "positive" if drift[axis_index] >= 0.0 else "negative"
    correction_direction = "negative" if direction == "positive" else "positive"
    signal = float(abs(drift[axis_index]))
    competing = float(abs(drift[1 - axis_index]))
    confidence = signal / (signal + competing + residual + 1e-12)
    return BiasEstimate(
        dominant_axis=axis,
        estimated_direction=direction,
        estimated_drift_per_step=(float(drift[0]), float(drift[1])),
        axis_response_gain=(gains[0], gains[1]),
        residual=residual,
        confidence=float(np.clip(confidence, 0.0, 1.0)),
        recommended_correction_axis=axis,
        recommended_correction_direction=correction_direction,
    )
