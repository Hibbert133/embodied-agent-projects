"""Bounded compensation-response micro-probe."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from src.probemem_sciagent.schemas import CompensationProbeEvidence


def summarize_compensation_response(
    records: Sequence[dict[str, Any]], *, contact_distance: float = 0.08,
) -> CompensationProbeEvidence:
    if not records:
        raise ValueError("compensation probe requires a non-empty prefix")
    metrics = [row["task_progress_metrics"] for row in records]
    objects = [np.asarray(row["object_position"], dtype=float) for row in metrics]
    goal = np.asarray(metrics[0]["goal_position"], dtype=float)
    initial_object = np.asarray(records[0]["observation"], dtype=float)[4:7]
    goal_direction = goal[:2] - initial_object[:2]
    response = objects[-1][:2] - initial_object[:2]
    denominator = float(np.linalg.norm(goal_direction) * np.linalg.norm(response))
    alignment = 0.0 if denominator == 0.0 else float(np.dot(goal_direction, response) / denominator)
    increments = [current[:2] - previous[:2] for previous, current in zip([initial_object, *objects[:-1]], objects)]
    moving = [item for item in increments if float(np.linalg.norm(item)) >= 1e-5]
    if not moving or float(np.linalg.norm(goal_direction)) == 0.0:
        consistency = 0.0
    else:
        unit_goal = goal_direction / np.linalg.norm(goal_direction)
        consistency = sum(float(np.dot(item / np.linalg.norm(item), unit_goal)) > 0 for item in moving) / len(moving)
    contact_values = [float(row["gripper_object_distance"]) <= contact_distance for row in metrics]
    first_contact = next((index for index, value in enumerate(contact_values) if value), None)
    contact_preserved = bool(
        first_contact is not None and sum(contact_values[first_contact:]) / len(contact_values[first_contact:]) >= 0.8
    )
    return CompensationProbeEvidence(
        expected_direction_alignment=max(-1.0, min(1.0, alignment)),
        object_response_magnitude=float(np.linalg.norm(objects[-1] - initial_object)),
        response_consistency=float(consistency), contact_preserved=contact_preserved,
        temporary_progress=float(metrics[-1]["progress_to_goal"]),
    )
