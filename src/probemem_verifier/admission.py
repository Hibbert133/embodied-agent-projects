"""Outcome-blind admission for history-aware candidate verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any


@dataclass(frozen=True)
class AdmissionDecision:
    verifier_called: bool
    confidence_margin: float
    ambiguity_margin: float
    memory_conflict: bool
    memory_coverage: float
    recent_contradiction: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


def should_call_verifier(
    confidence_margin: float,
    memory_conflict: bool,
    memory_coverage: float,
    *,
    ambiguity_margin: float = 0.05,
    recent_contradiction: bool = False,
) -> bool:
    """Return the preregistered outcome-independent admission decision."""

    return assess_admission(
        confidence_margin,
        memory_conflict,
        memory_coverage,
        ambiguity_margin=ambiguity_margin,
        recent_contradiction=recent_contradiction,
    ).verifier_called


def assess_admission(
    confidence_margin: float,
    memory_conflict: bool,
    memory_coverage: float,
    *,
    ambiguity_margin: float = 0.05,
    recent_contradiction: bool = False,
) -> AdmissionDecision:
    values = (confidence_margin, memory_coverage, ambiguity_margin)
    if not all(math.isfinite(value) for value in values) or min(values) < 0:
        raise ValueError("admission values must be finite and non-negative")
    if type(memory_conflict) is not bool or type(recent_contradiction) is not bool:
        raise ValueError("admission conflict flags must be booleans")
    reasons: list[str] = []
    if confidence_margin <= ambiguity_margin:
        reasons.append("WITHIN_AMBIGUITY_BAND")
    if memory_coverage > 0 and memory_conflict:
        reasons.append("GLOBAL_RECENT_MEMORY_CONFLICT")
    if memory_coverage > 0 and recent_contradiction:
        reasons.append("RECENT_SIMILAR_CONTRADICTION")
    return AdmissionDecision(
        verifier_called=bool(reasons), confidence_margin=float(confidence_margin),
        ambiguity_margin=float(ambiguity_margin), memory_conflict=memory_conflict,
        memory_coverage=float(memory_coverage), recent_contradiction=recent_contradiction,
        reasons=tuple(reasons) if reasons else ("CLEAR_DEFAULT",),
    )
