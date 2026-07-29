"""Typed, leakage-safe recovery skills for online robotic-agent selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from src.planar_recovery import estimate_planar_correction
from src.recovery_agent import DEFAULT_CORRECTION_MAGNITUDES


@dataclass(frozen=True)
class RecoverySkillContract:
    """A callable recovery capability with explicit grounding and cost."""

    skill_id: str
    description: str
    correction: tuple[float, float, float, float]
    preconditions: tuple[str, ...]
    expected_effect: str
    rollout_cost: int
    verifier_metrics: tuple[str, ...]
    failure_modes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_planar_recovery_skills(
    diagnostic_context: Mapping[str, Any],
    *,
    allowed_magnitudes: Sequence[float] = DEFAULT_CORRECTION_MAGNITUDES,
) -> tuple[dict[str, Any], tuple[RecoverySkillContract, ...]]:
    """Build grounded candidates from active-probe evidence, never fault truth."""

    estimate = estimate_planar_correction(
        diagnostic_context, allowed_magnitudes=allowed_magnitudes
    )
    dominant = np.asarray(estimate.dominant_axis_correction, dtype=float)
    simultaneous = np.asarray(estimate.simultaneous_correction, dtype=float)
    common_verifiers = (
        "success", "final_object_goal_distance", "progress_to_goal",
        "minimum_gripper_object_distance",
    )
    skills = (
        RecoverySkillContract(
            skill_id="dominant_axis_repair",
            description="Compensate only the largest inferred planar bias component.",
            correction=tuple(float(value) for value in dominant),
            preconditions=("one inferred axis dominates", "one recovery rollout remains"),
            expected_effect="Reduce drift on the dominant inferred axis.",
            rollout_cost=1,
            verifier_metrics=common_verifiers,
            failure_modes=("ignored secondary-axis drift", "under-compensation"),
        ),
        RecoverySkillContract(
            skill_id="simultaneous_xy_repair",
            description="Compensate both independently inferred planar bias components.",
            correction=tuple(float(value) for value in simultaneous),
            preconditions=("both planar estimates are available", "one recovery rollout remains"),
            expected_effect="Reduce x/y drift in one bounded recovery rollout.",
            rollout_cost=1,
            verifier_metrics=common_verifiers,
            failure_modes=("probe model mismatch", "phase-dependent over-correction"),
        ),
    )
    structured_diagnosis = {
        "protocol": "symmetric_world_frame_xy_v1",
        "evidence_source": "commanded actions and observed gripper transitions",
        "estimated_action_bias": estimate.estimated_action_bias,
        "axis_confidence": estimate.confidence,
        "estimation_residual": float(
            diagnostic_context.get("inference", {}).get("residual", 0.0)
        ),
        "probe_environment_steps": int(
            diagnostic_context.get("probe_environment_steps", 0)
        ),
    }
    return structured_diagnosis, skills


def select_skill(
    skills: Sequence[RecoverySkillContract], skill_id: str
) -> RecoverySkillContract:
    matches = [skill for skill in skills if skill.skill_id == skill_id]
    if len(matches) != 1:
        raise ValueError(f"unknown or ambiguous recovery skill: {skill_id}")
    return matches[0]
