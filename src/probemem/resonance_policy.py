"""Frozen attempt-level policies for a second recovery verification.

This module consumes only the result of the first fresh verification.  It does
not inspect the evaluator-only outcomes of either second-attempt candidate.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.probemem.models import InterventionSkill


COMPENSATION = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY

AGENT_METHODS = (
    "single_retry",
    "repeat_retry",
    "switch_compensation",
    "status_conditioned",
    "rejection_abstain",
)
EVALUATOR_METHODS = ("oracle_second",)
METHODS = AGENT_METHODS + EVALUATOR_METHODS
VALID_STATUSES = frozenset({"ACCEPTED", "INCONCLUSIVE", "REJECTED"})


@dataclass(frozen=True)
class SecondAttemptDecision:
    method: str
    first_verification_status: str
    request_second_attempt: bool
    selected_skill: InterventionSkill | None
    reason: str
    remaining_budget: int


def decide_second_attempt(
    *,
    method: str,
    first_verification_status: str,
    remaining_budget: int,
    reserved_second_verification_budget: int,
) -> SecondAttemptDecision:
    """Choose at most one second verification from Agent-visible feedback."""
    if method not in AGENT_METHODS:
        raise ValueError(f"unsupported Agent method: {method}")
    if first_verification_status not in VALID_STATUSES:
        raise ValueError(f"unsupported verification status: {first_verification_status}")
    if remaining_budget < 0 or reserved_second_verification_budget <= 0:
        raise ValueError("budgets must be non-negative with a positive reservation")
    if first_verification_status == "ACCEPTED":
        return SecondAttemptDecision(
            method, first_verification_status, False, None,
            "first_verification_accepted_stop", remaining_budget,
        )
    if method == "single_retry":
        return SecondAttemptDecision(
            method, first_verification_status, False, None,
            "single_attempt_protocol_stop", remaining_budget,
        )
    if method == "rejection_abstain" and first_verification_status == "REJECTED":
        return SecondAttemptDecision(
            method, first_verification_status, False, None,
            "rejected_feedback_abstain_to_save_cost", remaining_budget,
        )
    if remaining_budget < reserved_second_verification_budget:
        return SecondAttemptDecision(
            method, first_verification_status, False, None,
            "insufficient_budget_for_second_verification", remaining_budget,
        )
    if method == "repeat_retry":
        selected = RETRY
    elif method == "switch_compensation":
        selected = COMPENSATION
    elif method == "status_conditioned":
        selected = RETRY if first_verification_status == "INCONCLUSIVE" else COMPENSATION
    elif method == "rejection_abstain":
        selected = RETRY
    else:  # pragma: no cover - registry validation above makes this unreachable
        raise AssertionError(method)
    return SecondAttemptDecision(
        method, first_verification_status, True, selected,
        f"second_attempt_selected_from_{first_verification_status.lower()}_feedback",
        remaining_budget,
    )
