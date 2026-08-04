"""Strict schemas for the ProbeMem verifier demo."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from src.probemem.compact_evidence import REGISTERED_SKILLS
from src.reasoning.evidence import validate_no_oracle_evidence


STATUSES = ("ACCEPTED", "INCONCLUSIVE", "REJECTED")


@dataclass(frozen=True)
class DeterministicProposal:
    selected_skill: str
    score: float
    threshold: float
    confidence_margin: float

    def __post_init__(self) -> None:
        if self.selected_skill not in REGISTERED_SKILLS:
            raise ValueError("deterministic proposal requires a registered skill")
        if not all(math.isfinite(value) for value in (self.score, self.threshold, self.confidence_margin)):
            raise ValueError("deterministic proposal values must be finite")
        if min(self.score, self.threshold, self.confidence_margin) < 0:
            raise ValueError("deterministic proposal values must be non-negative")
        if not math.isclose(self.confidence_margin, abs(self.score - self.threshold), abs_tol=1e-12):
            raise ValueError("confidence margin must equal abs(score - threshold)")
        # The frozen threshold is host-owned audit state and is intentionally
        # prohibited from Agent/GLM evidence payloads. Do not pass this host
        # proposal through the Agent-view leakage validator.

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateVerification:
    skill: str
    predicted_accept_probability: float
    predicted_status: str
    confidence: float
    memory_applicable: bool
    coverage_count: int
    supporting_record_ids: tuple[str, ...]
    contradicting_record_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.skill not in REGISTERED_SKILLS or self.predicted_status not in STATUSES:
            raise ValueError("candidate verification has invalid skill or status")
        if not 0.0 <= self.predicted_accept_probability <= 1.0 or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("candidate probabilities must be in [0, 1]")
        if type(self.memory_applicable) is not bool or self.coverage_count < 0:
            raise ValueError("candidate applicability or coverage is invalid")
        if self.memory_applicable != (self.coverage_count > 0):
            raise ValueError("memory applicability must reflect positive coverage")
        ids = self.supporting_record_ids + self.contradicting_record_ids
        if any(not value for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("candidate record IDs must be non-empty and unique")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["supporting_record_ids"] = list(self.supporting_record_ids)
        value["contradicting_record_ids"] = list(self.contradicting_record_ids)
        return value


@dataclass(frozen=True)
class OverrideDecision:
    default_skill: str
    final_skill: str
    verifier_called: bool
    override_applied: bool
    override_reason: str
    default_probability: float | None
    alternative_probability: float | None

    def __post_init__(self) -> None:
        if self.default_skill not in REGISTERED_SKILLS or self.final_skill not in REGISTERED_SKILLS:
            raise ValueError("override decision requires registered skills")
        if type(self.verifier_called) is not bool or type(self.override_applied) is not bool:
            raise ValueError("override flags must be booleans")
        if self.override_applied != (self.final_skill != self.default_skill):
            raise ValueError("override flag and final skill disagree")
        if not self.override_reason.strip():
            raise ValueError("override reason cannot be empty")
        for value in (self.default_probability, self.alternative_probability):
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError("override probabilities must be in [0, 1]")
        if not self.verifier_called and (self.default_probability is not None or self.alternative_probability is not None):
            raise ValueError("bypassed verifier cannot expose candidate probabilities")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
