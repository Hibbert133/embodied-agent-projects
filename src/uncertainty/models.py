"""Explicit uncertainty and evidence-acquisition decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class UncertaintyEstimate:
    estimate_id: str
    based_on_evidence_ids: tuple[str, ...]
    epistemic: float
    aleatoric: float
    overall: float
    missing_evidence: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        if not self.estimate_id.strip() or not self.based_on_evidence_ids:
            raise ValueError("uncertainty requires identity and evidence provenance")
        if any(not 0.0 <= value <= 1.0 for value in (self.epistemic, self.aleatoric, self.overall)):
            raise ValueError("uncertainty components must be in [0, 1]")
        if not self.rationale.strip():
            raise ValueError("uncertainty estimate requires a rationale")


class EvidenceAction(str, Enum):
    UPDATE_HYPOTHESIS = "update_hypothesis"
    REQUEST_PROBE = "request_probe"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class EvidenceAcquisitionDecision:
    decision_id: str
    estimate_id: str
    action: EvidenceAction
    rationale: str
    max_probe_steps: int = 0

    def __post_init__(self) -> None:
        if not self.decision_id.strip() or not self.estimate_id.strip() or not self.rationale.strip():
            raise ValueError("evidence decision requires IDs and rationale")
        if self.action is EvidenceAction.REQUEST_PROBE and self.max_probe_steps <= 0:
            raise ValueError("probe request requires a positive step budget")
        if self.action is not EvidenceAction.REQUEST_PROBE and self.max_probe_steps != 0:
            raise ValueError("only a probe request may reserve probe steps")
