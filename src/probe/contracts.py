"""Authorization, planning, and execution contracts for diagnostic probes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from src.reasoning import EvidencePacket
from src.uncertainty import EvidenceAcquisitionDecision, EvidenceAction


class ProbeKind(str, Enum):
    DIRECTIONAL_ACTION = "directional_action"
    REPEATED_ACTION = "repeated_action"
    EXPLORATORY_PUSH = "exploratory_push"
    LOW_FORCE_CONTACT = "low_force_contact"
    CUSTOM = "custom"


@dataclass(frozen=True)
class ProbePlan:
    plan_id: str
    authorized_by_decision_id: str
    kind: ProbeKind
    objective: str
    target_uncertainty: str
    expected_observation: str
    max_steps: int
    stop_conditions: tuple[str, ...]
    safety_constraints: tuple[str, ...]
    parameters: Mapping[str, Any]

    @classmethod
    def from_decision(
        cls,
        decision: EvidenceAcquisitionDecision,
        *,
        plan_id: str,
        kind: ProbeKind,
        objective: str,
        target_uncertainty: str,
        expected_observation: str,
        max_steps: int,
        stop_conditions: tuple[str, ...],
        safety_constraints: tuple[str, ...],
        parameters: Mapping[str, Any],
    ) -> "ProbePlan":
        if decision.action is not EvidenceAction.REQUEST_PROBE:
            raise ValueError("probe planning requires an explicit REQUEST_PROBE decision")
        if max_steps <= 0 or max_steps > decision.max_probe_steps:
            raise ValueError("probe plan exceeds its authorized interaction budget")
        if not all(
            item.strip()
            for item in (plan_id, objective, target_uncertainty, expected_observation)
        ):
            raise ValueError("probe plan requires identity, objective, and prediction")
        if not safety_constraints:
            raise ValueError("probe plan requires explicit safety constraints")
        return cls(
            plan_id,
            decision.decision_id,
            kind,
            objective,
            target_uncertainty,
            expected_observation,
            max_steps,
            stop_conditions,
            safety_constraints,
            parameters,
        )


@dataclass(frozen=True)
class ProbeEvidence:
    plan_id: str
    evidence: EvidencePacket
    steps: int
    termination_reason: str
    information_summary: str

    def __post_init__(self) -> None:
        if self.steps < 0 or self.steps > self.evidence.step_count:
            raise ValueError("probe step cost must be represented by its evidence")
        if not self.termination_reason.strip() or not self.information_summary.strip():
            raise ValueError("probe evidence requires termination and information summaries")


class ProbePlanner(Protocol):
    def plan(
        self,
        decision: EvidenceAcquisitionDecision,
        hypotheses: tuple[Any, ...],
    ) -> ProbePlan: ...


class ProbeExecutor(Protocol):
    def execute(self, plan: ProbePlan) -> ProbeEvidence: ...
