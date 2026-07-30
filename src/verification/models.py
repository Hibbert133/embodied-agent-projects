"""Verification rollout plans and outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from src.planner import CorrectiveIntervention


class VerificationStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class VerificationPlan:
    plan_id: str
    intervention_id: str
    max_steps: int

    @classmethod
    def from_intervention(
        cls, intervention: CorrectiveIntervention, *, plan_id: str
    ) -> "VerificationPlan":
        if not plan_id.strip():
            raise ValueError("verification plan requires an ID")
        return cls(plan_id, intervention.intervention_id, intervention.max_verification_steps)


@dataclass(frozen=True)
class VerificationResult:
    plan_id: str
    intervention_id: str
    evidence_id: str
    status: VerificationStatus
    observed_metrics: Mapping[str, float | bool]
    rationale: str

    def __post_init__(self) -> None:
        if not all(
            item.strip()
            for item in (self.plan_id, self.intervention_id, self.evidence_id, self.rationale)
        ):
            raise ValueError("verification result requires provenance and rationale")
        if not self.observed_metrics:
            raise ValueError("verification result requires observed metrics")


class VerificationEvaluator(Protocol):
    def evaluate(
        self,
        intervention: CorrectiveIntervention,
        evidence: Any,
    ) -> VerificationResult: ...
