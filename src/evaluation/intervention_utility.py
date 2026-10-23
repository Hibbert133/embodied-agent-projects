"""Evaluator-only ordering of matched fresh-verification outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isclose
from typing import Any, Mapping, Sequence


class UtilityComparison(str, Enum):
    LEFT = "left_better"
    RIGHT = "right_better"
    TIE = "tie"


_STATUS_RANK = {"REJECTED": 0, "INCONCLUSIVE": 1, "ACCEPTED": 2}


@dataclass(frozen=True)
class CandidateUtilityOutcome:
    candidate_id: str
    verification_status: str
    verification_steps: int
    final_object_goal_distance: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CandidateUtilityOutcome":
        try:
            outcome = cls(
                candidate_id=str(value["candidate_id"]),
                verification_status=str(value["verification_status"]),
                verification_steps=int(value["verification_steps"]),
                final_object_goal_distance=float(value["final_object_goal_distance"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid candidate utility outcome: {exc}") from exc
        if not outcome.candidate_id or outcome.verification_status not in _STATUS_RANK:
            raise ValueError("candidate identity and known verification status are required")
        if outcome.verification_steps <= 0 or outcome.final_object_goal_distance < 0:
            raise ValueError("candidate outcome metrics must be valid")
        return outcome


def compare_candidate_utility(
    left: CandidateUtilityOutcome,
    right: CandidateUtilityOutcome,
    *,
    distance_tolerance: float = 1e-12,
) -> UtilityComparison:
    """Compare matched outcomes using the preregistered evaluator ordering."""

    left_rank = _STATUS_RANK[left.verification_status]
    right_rank = _STATUS_RANK[right.verification_status]
    if left_rank != right_rank:
        return UtilityComparison.LEFT if left_rank > right_rank else UtilityComparison.RIGHT

    if left.verification_status == "ACCEPTED":
        if left.verification_steps != right.verification_steps:
            return (
                UtilityComparison.LEFT
                if left.verification_steps < right.verification_steps
                else UtilityComparison.RIGHT
            )
        if not isclose(
            left.final_object_goal_distance,
            right.final_object_goal_distance,
            abs_tol=distance_tolerance,
            rel_tol=0.0,
        ):
            return (
                UtilityComparison.LEFT
                if left.final_object_goal_distance < right.final_object_goal_distance
                else UtilityComparison.RIGHT
            )
        return UtilityComparison.TIE

    if not isclose(
        left.final_object_goal_distance,
        right.final_object_goal_distance,
        abs_tol=distance_tolerance,
        rel_tol=0.0,
    ):
        return (
            UtilityComparison.LEFT
            if left.final_object_goal_distance < right.final_object_goal_distance
            else UtilityComparison.RIGHT
        )
    if left.verification_steps != right.verification_steps:
        return (
            UtilityComparison.LEFT
            if left.verification_steps < right.verification_steps
            else UtilityComparison.RIGHT
        )
    return UtilityComparison.TIE


def best_candidate_ids(
    outcomes: Sequence[CandidateUtilityOutcome],
) -> tuple[str, ...]:
    """Return one winner or both IDs when two registered outcomes tie."""

    if len(outcomes) != 2 or len({item.candidate_id for item in outcomes}) != 2:
        raise ValueError("the v1 audit requires exactly two unique candidates")
    comparison = compare_candidate_utility(outcomes[0], outcomes[1])
    if comparison is UtilityComparison.LEFT:
        return (outcomes[0].candidate_id,)
    if comparison is UtilityComparison.RIGHT:
        return (outcomes[1].candidate_id,)
    return tuple(item.candidate_id for item in outcomes)
