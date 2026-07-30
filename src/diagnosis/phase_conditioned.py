"""Phase-conditioned planar response consistency from schema-v2 Agent View."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from src.task_metrics import classify_push_phase, extract_push_positions
from src.trajectory import build_agent_view


@dataclass(frozen=True)
class PhaseResponseEstimate:
    phase: str
    sample_count: int
    axis_response_gain: tuple[float, float]
    estimated_drift_per_step: tuple[float, float]
    normalized_residual: tuple[float, float]
    normalized_residual_norm: float
    action_excitation: tuple[float, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PhaseConditionedEstimate:
    phase_estimates: tuple[PhaseResponseEstimate, ...]
    phase_sample_counts: dict[str, int]
    phase_inconsistency: float
    eligible_sample_fraction: float
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_estimates": [estimate.to_dict() for estimate in self.phase_estimates],
            "phase_sample_counts": self.phase_sample_counts,
            "phase_inconsistency": self.phase_inconsistency,
            "eligible_sample_fraction": self.eligible_sample_fraction,
            "sample_count": self.sample_count,
        }


def _fit_phase(phase: str, rows: Sequence[Mapping[str, Any]]) -> PhaseResponseEstimate:
    commands = np.asarray([row["commanded_action"][:2] for row in rows], dtype=float)
    deltas = []
    for row in rows:
        before, _, _ = extract_push_positions(row["observation"])
        after, _, _ = extract_push_positions(row["next_observation"])
        deltas.append(after[:2] - before[:2])
    displacement = np.asarray(deltas, dtype=float)
    gains: list[float] = []
    drifts: list[float] = []
    residuals: list[float] = []
    excitations: list[float] = []
    for axis in range(2):
        command = commands[:, axis]
        target = displacement[:, axis]
        design = np.column_stack((command, np.ones(command.size)))
        gain, drift = np.linalg.lstsq(design, target, rcond=None)[0]
        prediction = design @ np.array([gain, drift])
        rmse = float(np.sqrt(np.mean(np.square(target - prediction))))
        normalized = float(np.clip(rmse / max(float(np.std(target)), 1e-9), 0.0, 1.0))
        gains.append(float(gain))
        drifts.append(float(drift))
        residuals.append(normalized)
        excitations.append(float(np.std(command)))
    return PhaseResponseEstimate(
        phase=phase,
        sample_count=len(rows),
        axis_response_gain=(gains[0], gains[1]),
        estimated_drift_per_step=(drifts[0], drifts[1]),
        normalized_residual=(residuals[0], residuals[1]),
        normalized_residual_norm=float(np.linalg.norm(residuals) / np.sqrt(2.0)),
        action_excitation=(excitations[0], excitations[1]),
    )


def estimate_phase_conditioned_response(
    transitions: Sequence[Mapping[str, Any]], *, minimum_phase_samples: int = 8,
    contact_distance: float = 0.08, near_goal_distance: float = 0.08,
) -> PhaseConditionedEstimate:
    """Fit independent response models within visible task phases.

    ``phase_inconsistency`` is the eligible-sample-weighted mean of normalized
    per-phase residual norms. Its direction is pre-registered: larger values imply
    less repeatable within-phase response and a stronger need for a probe.
    """
    if minimum_phase_samples < 3:
        raise ValueError("minimum_phase_samples must be at least 3")
    if len(transitions) < minimum_phase_samples:
        raise ValueError("insufficient transitions for phase-conditioned estimate")
    rows = [build_agent_view(row) for row in transitions]
    for previous, current in zip(rows, rows[1:]):
        if int(current["step"]) != int(previous["step"]) + 1:
            raise ValueError("agent transitions must have contiguous step numbers")
        if not np.allclose(
            np.asarray(previous["next_observation"], dtype=float),
            np.asarray(current["observation"], dtype=float),
            rtol=1e-7, atol=1e-9,
        ):
            raise ValueError("agent transitions are not state-continuous")
    grouped: dict[str, list[Mapping[str, Any]]] = {
        phase: [] for phase in ("approach", "push", "near_goal")
    }
    for row in rows:
        phase = classify_push_phase(
            row["observation"], contact_distance=contact_distance,
            near_goal_distance=near_goal_distance,
        )
        grouped[phase].append(row)
    estimates = tuple(
        _fit_phase(phase, grouped[phase])
        for phase in ("approach", "push", "near_goal")
        if len(grouped[phase]) >= minimum_phase_samples
    )
    if not estimates:
        raise ValueError("no phase has enough samples for a response estimate")
    eligible = sum(estimate.sample_count for estimate in estimates)
    inconsistency = sum(
        estimate.sample_count * estimate.normalized_residual_norm
        for estimate in estimates
    ) / eligible
    return PhaseConditionedEstimate(
        phase_estimates=estimates,
        phase_sample_counts={phase: len(grouped[phase]) for phase in grouped},
        phase_inconsistency=float(inconsistency),
        eligible_sample_fraction=eligible / len(rows),
        sample_count=len(rows),
    )
