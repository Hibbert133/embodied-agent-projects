"""Transparent reference gate for architecture tests and future ablations."""

from __future__ import annotations

from dataclasses import dataclass

from src.uncertainty.models import (
    EvidenceAcquisitionDecision,
    EvidenceAction,
    UncertaintyEstimate,
)


@dataclass(frozen=True)
class ThresholdEvidencePolicy:
    high_uncertainty_threshold: float = 0.6

    def __post_init__(self) -> None:
        if not 0.0 <= self.high_uncertainty_threshold <= 1.0:
            raise ValueError("uncertainty threshold must be in [0, 1]")

    def decide(
        self,
        estimate: UncertaintyEstimate,
        *,
        decision_id: str,
        available_probe_steps: int,
    ) -> EvidenceAcquisitionDecision:
        if estimate.overall >= self.high_uncertainty_threshold:
            if available_probe_steps <= 0:
                return EvidenceAcquisitionDecision(
                    decision_id,
                    estimate.estimate_id,
                    EvidenceAction.ABSTAIN,
                    "uncertainty is high but no diagnostic interaction budget remains",
                )
            return EvidenceAcquisitionDecision(
                decision_id,
                estimate.estimate_id,
                EvidenceAction.REQUEST_PROBE,
                "uncertainty exceeds the configured evidence threshold",
                available_probe_steps,
            )
        return EvidenceAcquisitionDecision(
            decision_id,
            estimate.estimate_id,
            EvidenceAction.UPDATE_HYPOTHESIS,
            "available evidence is sufficient under the configured threshold",
        )
