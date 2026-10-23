"""Verified-only experience memory contract; no persistence implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.diagnosis import Hypothesis
from src.planner import CorrectiveIntervention
from src.verification import VerificationResult, VerificationStatus


@dataclass(frozen=True)
class VerifiedExperience:
    experience_id: str
    hypothesis: Hypothesis
    intervention: CorrectiveIntervention
    verification: VerificationResult

    def __post_init__(self) -> None:
        if not self.experience_id.strip():
            raise ValueError("experience_id must be non-empty")
        if self.verification.status is not VerificationStatus.ACCEPTED:
            raise ValueError("memory accepts only an ACCEPTED verification result")
        if self.intervention.hypothesis_id != self.hypothesis.hypothesis_id:
            raise ValueError("intervention and hypothesis provenance differ")
        if self.verification.intervention_id != self.intervention.intervention_id:
            raise ValueError("verification and intervention provenance differ")


class ExperienceMemory(Protocol):
    def add_verified(self, experience: VerifiedExperience) -> None: ...

    def query(self, evidence_signature: tuple[float, ...], limit: int) -> tuple[VerifiedExperience, ...]: ...
