"""Bounded corrective-intervention contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol


class CriterionOperator(str, Enum):
    LESS_EQUAL = "less_equal"
    GREATER_EQUAL = "greater_equal"
    EQUAL = "equal"


@dataclass(frozen=True)
class VerificationCriterion:
    metric: str
    operator: CriterionOperator
    threshold: float | bool

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ValueError("verification criterion requires a metric")


@dataclass(frozen=True)
class CorrectiveIntervention:
    intervention_id: str
    hypothesis_id: str
    strategy: str
    parameters: Mapping[str, Any]
    predicted_effect: str
    verification_criteria: tuple[VerificationCriterion, ...]
    max_verification_steps: int

    def __post_init__(self) -> None:
        if not all(
            item.strip()
            for item in (
                self.intervention_id,
                self.hypothesis_id,
                self.strategy,
                self.predicted_effect,
            )
        ):
            raise ValueError("intervention requires identity, hypothesis, and prediction")
        if not self.verification_criteria or self.max_verification_steps <= 0:
            raise ValueError("intervention requires verification criteria and budget")


class InterventionPlanner(Protocol):
    def propose(self, hypothesis: Any, evidence: tuple[Any, ...]) -> CorrectiveIntervention: ...
