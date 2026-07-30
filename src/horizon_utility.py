"""Leakage-safe temporal summaries for candidate recovery trajectories."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from src.trajectory_views import AGENT_FIELDS, FORBIDDEN_AGENT_FIELDS


def build_prefix_evidence(
    records: Sequence[Mapping[str, Any]], *, candidate_id: str, horizon: int
) -> dict[str, Any]:
    """Summarize only Agent-visible transitions available by ``horizon``."""

    if horizon <= 0 or not records:
        raise ValueError("positive horizon and non-empty records are required")
    prefix = [record for record in records if int(record["step"]) <= horizon]
    if not prefix:
        raise ValueError("trajectory has no transition within the requested horizon")
    expected_steps = list(range(1, len(prefix) + 1))
    if [int(record["step"]) for record in prefix] != expected_steps:
        raise ValueError("Agent trajectory steps must be contiguous and one-indexed")
    for record in prefix:
        if set(record) != set(AGENT_FIELDS):
            raise ValueError("horizon evidence requires exact schema-v2 Agent View")
        if FORBIDDEN_AGENT_FIELDS & set(record):
            raise ValueError("horizon evidence contains Oracle fields")

    metrics = [record["task_progress_metrics"] for record in prefix]
    final = metrics[-1]
    steps = len(prefix)
    lookback_index = max(0, steps - 21)
    lookback_steps = steps - (lookback_index + 1)
    if lookback_steps:
        recent_slope = (
            float(final["progress_to_goal"])
            - float(metrics[lookback_index]["progress_to_goal"])
        ) / lookback_steps
    else:
        recent_slope = float(final["progress_to_goal"])
    near_contact = [
        float(metric["gripper_object_distance"]) <= 0.05 for metric in metrics
    ]
    first_near_contact = next(
        (index + 1 for index, value in enumerate(near_contact) if value), None
    )
    first_motion = next(
        (
            index + 1
            for index, metric in enumerate(metrics)
            if float(metric["object_displacement_from_start"]) >= 0.01
        ),
        None,
    )
    stagnant_tail = 0
    object_positions = [
        np.asarray(metric["object_position"], dtype=float) for metric in metrics
    ]
    for previous, current in zip(
        reversed(object_positions[:-1]), reversed(object_positions[1:])
    ):
        if float(np.linalg.norm(current - previous)) >= 1e-4:
            break
        stagnant_tail += 1

    return {
        "candidate_id": candidate_id,
        "horizon": horizon,
        "observed_steps": steps,
        "steps": steps,
        "success_within_probe_budget": any(bool(record["success"]) for record in prefix),
        "final_object_goal_distance": float(final["object_goal_distance"]),
        "progress_to_goal": float(final["progress_to_goal"]),
        "progress_per_step": float(final["progress_to_goal"]) / steps,
        "recent_20_step_progress_slope": recent_slope,
        "minimum_gripper_object_distance": min(
            float(metric["gripper_object_distance"]) for metric in metrics
        ),
        "near_contact_fraction": sum(near_contact) / steps,
        "first_near_contact_step": first_near_contact,
        "first_object_motion_step": first_motion,
        "object_displacement": float(final["object_displacement_from_start"]),
        "stagnant_tail_steps": stagnant_tail,
    }
