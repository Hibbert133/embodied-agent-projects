"""Frozen deterministic selection from repeated Agent-visible candidate prefixes."""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Any, Mapping, Sequence

from src.reasoning.evidence import validate_no_oracle_evidence


def aggregate_candidate_repetitions(
    repetitions: Sequence[Mapping[str, Any]], *, candidate_id: str
) -> dict[str, Any]:
    """Aggregate repeated prefix summaries without evaluator outcomes."""

    if not repetitions:
        raise ValueError("at least one candidate repetition is required")
    for item in repetitions:
        validate_no_oracle_evidence(item)
        if str(item["candidate_id"]) != candidate_id:
            raise ValueError("candidate repetition ID mismatch")
    distances = [float(item["final_object_goal_distance"]) for item in repetitions]
    distance_std = pstdev(distances)
    result = {
        "candidate_id": candidate_id,
        "repetition_count": len(repetitions),
        "prefix_success_count": sum(
            bool(item["success_within_probe_budget"]) for item in repetitions
        ),
        "mean_final_object_goal_distance": mean(distances),
        "final_object_goal_distance_std": distance_std,
        "robust_distance_score": mean(distances) + distance_std,
        "mean_observed_steps": mean(float(item["observed_steps"]) for item in repetitions),
        "total_environment_steps": sum(
            int(item["observed_steps"]) for item in repetitions
        ),
    }
    validate_no_oracle_evidence(result)
    return result


def select_repeatability_candidate(
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    """Prefer repeated prefix success, then low robust distance and cost."""

    if len(candidates) != 2:
        raise ValueError("repeatability selector requires exactly two candidates")
    candidate_ids = [str(item["candidate_id"]) for item in candidates]
    if len(set(candidate_ids)) != 2:
        raise ValueError("candidate IDs must be unique")
    for item in candidates:
        validate_no_oracle_evidence(item)
    selected = min(
        candidates,
        key=lambda item: (
            -int(item["prefix_success_count"]),
            float(item["robust_distance_score"]),
            float(item["mean_observed_steps"]),
            str(item["candidate_id"]),
        ),
    )
    return str(selected["candidate_id"])
