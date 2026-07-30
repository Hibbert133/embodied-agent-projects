"""Deterministic controls for candidate-utility Agent experiments."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def choose_probe_greedy(evidence: Sequence[Mapping[str, Any]]) -> str:
    """Choose probe success first, then steps/distance; otherwise distance."""

    if len(evidence) < 2:
        raise ValueError("probe-greedy selection requires at least two candidates")
    candidate_ids = [str(item["candidate_id"]) for item in evidence]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate IDs must be unique")
    successful = [item for item in evidence if bool(item["success_within_probe_budget"])]
    if successful:
        selected = min(
            successful,
            key=lambda item: (
                int(item["steps"]),
                float(item["final_object_goal_distance"]),
                str(item["candidate_id"]),
            ),
        )
    else:
        selected = min(
            evidence,
            key=lambda item: (
                float(item["final_object_goal_distance"]),
                int(item["steps"]),
                str(item["candidate_id"]),
            ),
        )
    return str(selected["candidate_id"])


def choose_oracle_candidate(outcomes: Sequence[Mapping[str, Any]]) -> str:
    """Post-hoc upper bound using full outcomes; never an Agent input."""

    if len(outcomes) < 2:
        raise ValueError("Oracle selection requires at least two outcomes")
    candidate_ids = [str(item["candidate_id"]) for item in outcomes]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate IDs must be unique")
    selected = min(
        outcomes,
        key=lambda item: (
            0 if bool(item["success"]) else 1,
            int(item["steps"]),
            float(item["final_object_goal_distance"]),
            str(item["candidate_id"]),
        ),
    )
    return str(selected["candidate_id"])
