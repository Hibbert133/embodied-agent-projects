"""Frozen v1 budget-aware evidence-allocation semantics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Sequence

from src.reasoning.structured_evidence import StructuredEvidenceState
from src.uncertainty.models import (
    EvidenceAcquisitionDecision,
    EvidenceAction,
)


TOTAL_CASE_BUDGET_V1 = 1064
REGISTERED_PROBE_COST_V1 = 64
MINIMUM_RESERVED_VERIFICATION_BUDGET_V1 = 500
FROZEN_PHASE_THRESHOLD_V1 = 0.91612970415368


class EvidenceDecisionKind(str, Enum):
    CONTINUE = "CONTINUE"
    REQUEST_DIAGNOSTIC_PROBE = "REQUEST_DIAGNOSTIC_PROBE"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class EvidenceDecision:
    decision_id: str
    evidence_state_id: str
    action: EvidenceDecisionKind
    decision_required: bool
    total_case_budget: int
    remaining_budget_before: int
    consumed_budget_before: int
    reserved_probe_budget: int
    reserved_verification_budget: int
    rationale: str
    budget_rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.evidence_state_id.strip():
            raise ValueError("evidence decision requires identity and provenance")
        if not self.rationale.strip():
            raise ValueError("evidence decision requires a rationale")
        if self.total_case_budget <= 0 or not 0 <= self.remaining_budget_before <= self.total_case_budget:
            raise ValueError("invalid total or remaining case budget")
        if self.consumed_budget_before != self.total_case_budget - self.remaining_budget_before:
            raise ValueError("consumed and remaining budgets are inconsistent")
        if min(self.reserved_probe_budget, self.reserved_verification_budget) < 0:
            raise ValueError("reserved budgets must be non-negative")
        if self.action is EvidenceDecisionKind.REQUEST_DIAGNOSTIC_PROBE:
            required = self.reserved_probe_budget + self.reserved_verification_budget
            if self.reserved_probe_budget <= 0 or self.reserved_verification_budget <= 0:
                raise ValueError("probe decision must reserve probe and verification budgets")
            if self.remaining_budget_before < required:
                raise ValueError("probe decision exceeds remaining budget")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_legacy_decision(self) -> EvidenceAcquisitionDecision:
        action = {
            EvidenceDecisionKind.CONTINUE: EvidenceAction.UPDATE_HYPOTHESIS,
            EvidenceDecisionKind.REQUEST_DIAGNOSTIC_PROBE: EvidenceAction.REQUEST_PROBE,
            EvidenceDecisionKind.ABSTAIN: EvidenceAction.ABSTAIN,
        }[self.action]
        return EvidenceAcquisitionDecision(
            decision_id=self.decision_id,
            estimate_id=self.evidence_state_id,
            action=action,
            rationale=self.rationale,
            max_probe_steps=(
                self.reserved_probe_budget
                if self.action is EvidenceDecisionKind.REQUEST_DIAGNOSTIC_PROBE
                else 0
            ),
        )


def select_evidence_action(
    evidence_state: StructuredEvidenceState,
    remaining_budget: int,
    verified_history: Sequence[Any] = (),
    *,
    decision_id: str,
    threshold: float = FROZEN_PHASE_THRESHOLD_V1,
    total_case_budget: int = TOTAL_CASE_BUDGET_V1,
    registered_probe_cost: int = REGISTERED_PROBE_COST_V1,
    minimum_reserved_verification_budget: int = MINIMUM_RESERVED_VERIFICATION_BUDGET_V1,
) -> EvidenceDecision:
    """Allocate the one registered probe without consuming Oracle information."""

    del verified_history  # Reserved for the later chronological-memory experiment.
    if not 0 <= remaining_budget <= total_case_budget:
        raise ValueError("remaining_budget must be within the total case budget")
    if min(registered_probe_cost, minimum_reserved_verification_budget) <= 0:
        raise ValueError("probe and verification budgets must be positive")
    common = {
        "decision_id": decision_id,
        "evidence_state_id": evidence_state.evidence_id,
        "decision_required": evidence_state.decision_required,
        "total_case_budget": total_case_budget,
        "remaining_budget_before": remaining_budget,
        "consumed_budget_before": total_case_budget - remaining_budget,
    }
    if not evidence_state.decision_required:
        return EvidenceDecision(
            **common,
            action=EvidenceDecisionKind.CONTINUE,
            reserved_probe_budget=0,
            reserved_verification_budget=0,
            rationale="initial rollout succeeded; adaptation is not required",
        )
    if remaining_budget < minimum_reserved_verification_budget:
        return EvidenceDecision(
            **common,
            action=EvidenceDecisionKind.ABSTAIN,
            reserved_probe_budget=0,
            reserved_verification_budget=0,
            rationale="remaining budget cannot support fresh verification",
            budget_rejection_reason="insufficient_verification_budget",
        )
    if evidence_state.phase_response.phase_inconsistency < threshold:
        return EvidenceDecision(
            **common,
            action=EvidenceDecisionKind.CONTINUE,
            reserved_probe_budget=0,
            reserved_verification_budget=minimum_reserved_verification_budget,
            rationale="frozen evidence score supports continuing without a probe",
        )
    required = registered_probe_cost + minimum_reserved_verification_budget
    if remaining_budget < required:
        return EvidenceDecision(
            **common,
            action=EvidenceDecisionKind.ABSTAIN,
            reserved_probe_budget=0,
            reserved_verification_budget=minimum_reserved_verification_budget,
            rationale="probe would consume the budget reserved for fresh verification",
            budget_rejection_reason="insufficient_probe_and_verification_budget",
        )
    return EvidenceDecision(
        **common,
        action=EvidenceDecisionKind.REQUEST_DIAGNOSTIC_PROBE,
        reserved_probe_budget=registered_probe_cost,
        reserved_verification_budget=minimum_reserved_verification_budget,
        rationale="frozen evidence score justifies the registered diagnostic probe",
    )
