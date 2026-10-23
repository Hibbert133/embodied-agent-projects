"""Leakage-safe planar execution estimates from a failed rollout.

The local model is fitted independently for x and y:
``gripper_delta = response_gain * commanded_action + execution_drift``.
Only schema-v2 Agent View transitions are accepted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from src.task_metrics import extract_push_positions
from src.trajectory import build_agent_view


@dataclass(frozen=True)
class PassivePlanarEstimate:
    estimated_drift_per_step: tuple[float, float]
    axis_response_gain: tuple[float, float]
    normalized_residual: tuple[float, float]
    action_excitation: tuple[float, float]
    axis_confidence: tuple[float, float]
    overall_confidence: float
    uncertainty: float
    dominant_axis: str
    estimated_direction: str
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_probe_inference(self) -> dict[str, Any]:
        """Return the visible inference shape consumed by recovery skills."""

        correction_direction = (
            "negative" if self.estimated_direction == "positive" else "positive"
        )
        return {
            "dominant_axis": self.dominant_axis,
            "estimated_direction": self.estimated_direction,
            "estimated_drift_per_step": self.estimated_drift_per_step,
            "axis_response_gain": self.axis_response_gain,
            "residual": float(np.linalg.norm(self.normalized_residual)),
            "confidence": self.overall_confidence,
            "recommended_correction_axis": self.dominant_axis,
            "recommended_correction_direction": correction_direction,
        }


def estimate_passive_planar_drift(
    transitions: Sequence[Mapping[str, Any]],
    *,
    minimum_samples: int = 8,
    excitation_scale: float = 0.05,
) -> PassivePlanarEstimate:
    """Fit a local planar response model from causally available transitions."""

    if minimum_samples < 3 or excitation_scale <= 0.0:
        raise ValueError("minimum_samples >= 3 and positive excitation_scale are required")
    if len(transitions) < minimum_samples:
        raise ValueError(
            f"passive estimate requires at least {minimum_samples} transitions"
        )

    agent_rows = [build_agent_view(row) for row in transitions]
    for previous, current in zip(agent_rows, agent_rows[1:]):
        if int(current["step"]) != int(previous["step"]) + 1:
            raise ValueError("agent transitions must have contiguous step numbers")
        if not np.allclose(
            np.asarray(previous["next_observation"], dtype=float),
            np.asarray(current["observation"], dtype=float),
            rtol=1e-7,
            atol=1e-9,
        ):
            raise ValueError("agent transitions are not state-continuous")

    commands = np.asarray(
        [row["commanded_action"][:2] for row in agent_rows], dtype=float
    )
    deltas = []
    for row in agent_rows:
        before, _, _ = extract_push_positions(row["observation"])
        after, _, _ = extract_push_positions(row["next_observation"])
        deltas.append(after[:2] - before[:2])
    displacement = np.asarray(deltas, dtype=float)

    gains: list[float] = []
    drifts: list[float] = []
    residuals: list[float] = []
    excitations: list[float] = []
    confidences: list[float] = []
    for axis in range(2):
        command = commands[:, axis]
        target = displacement[:, axis]
        design = np.column_stack((command, np.ones(command.size)))
        gain, drift = np.linalg.lstsq(design, target, rcond=None)[0]
        prediction = design @ np.array([gain, drift])
        rmse = float(np.sqrt(np.mean(np.square(target - prediction))))
        target_scale = max(float(np.std(target)), 1e-9)
        normalized_residual = float(np.clip(rmse / target_scale, 0.0, 1.0))
        excitation = float(np.std(command))
        excitation_score = float(np.clip(excitation / excitation_scale, 0.0, 1.0))
        confidence = excitation_score * (1.0 - normalized_residual)
        gains.append(float(gain))
        drifts.append(float(drift))
        residuals.append(normalized_residual)
        excitations.append(excitation)
        confidences.append(float(np.clip(confidence, 0.0, 1.0)))

    overall_confidence = float(np.mean(confidences))
    dominant_index = int(np.argmax(np.abs(drifts)))
    direction = "positive" if drifts[dominant_index] >= 0.0 else "negative"
    return PassivePlanarEstimate(
        estimated_drift_per_step=(drifts[0], drifts[1]),
        axis_response_gain=(gains[0], gains[1]),
        normalized_residual=(residuals[0], residuals[1]),
        action_excitation=(excitations[0], excitations[1]),
        axis_confidence=(confidences[0], confidences[1]),
        overall_confidence=overall_confidence,
        uncertainty=1.0 - overall_confidence,
        dominant_axis=("x", "y")[dominant_index],
        estimated_direction=direction,
        sample_count=len(agent_rows),
    )
