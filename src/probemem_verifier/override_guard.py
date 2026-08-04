"""Conservative deterministic override guard."""

from __future__ import annotations

from typing import Mapping

from src.probemem.compact_evidence import REGISTERED_SKILLS
from src.probemem_verifier.candidate_verifier import AdmissionMemorySignals, CandidateMemorySummary
from src.probemem_verifier.schemas import CandidateVerification, OverrideDecision


def decide_override(
    *,
    default_skill: str,
    verifier_called: bool,
    candidates: Mapping[str, CandidateVerification] | None,
    summaries: Mapping[str, CandidateMemorySummary] | None,
    memory_signals: AdmissionMemorySignals | None,
    probability_margin_minimum: float = 0.15,
    coverage_minimum: int = 3,
    contradiction_rate_maximum: float = 0.30,
    confidence_minimum: float = 0.70,
) -> OverrideDecision:
    if default_skill not in REGISTERED_SKILLS:
        raise ValueError("override default must be registered")
    alternative_skill = next(skill for skill in REGISTERED_SKILLS if skill != default_skill)
    if not verifier_called:
        return OverrideDecision(
            default_skill, default_skill, False, False, "VERIFIER_BYPASSED",
            None, None,
        )
    if candidates is None or summaries is None or memory_signals is None:
        return OverrideDecision(
            default_skill, default_skill, True, False, "VERIFIER_FAIL_CLOSED",
            None, None,
        )
    if set(candidates) != set(REGISTERED_SKILLS) or set(summaries) != set(REGISTERED_SKILLS):
        return OverrideDecision(
            default_skill, default_skill, True, False, "VERIFIER_FAIL_CLOSED",
            None, None,
        )
    default = candidates[default_skill]
    alternative = candidates[alternative_skill]
    summary = summaries[alternative_skill]
    probability_margin = alternative.predicted_accept_probability - default.predicted_accept_probability
    contradiction_rate = (
        summary.contradiction_count / summary.coverage_count
        if summary.coverage_count else 1.0
    )
    blockers: list[str] = []
    if alternative.predicted_accept_probability <= default.predicted_accept_probability:
        blockers.append("ALTERNATIVE_NOT_BETTER")
    if probability_margin < probability_margin_minimum:
        blockers.append("PROBABILITY_MARGIN_TOO_SMALL")
    if not alternative.memory_applicable or alternative.coverage_count < coverage_minimum:
        blockers.append("INSUFFICIENT_ALTERNATIVE_COVERAGE")
    if contradiction_rate > contradiction_rate_maximum:
        blockers.append("ALTERNATIVE_CONTRADICTION_TOO_HIGH")
    if (
        memory_signals.global_preference != alternative_skill
        or memory_signals.recent_preference != alternative_skill
    ):
        blockers.append("RECENT_GLOBAL_PREFERENCE_NOT_ALIGNED")
    if alternative.confidence < confidence_minimum:
        blockers.append("VERIFIER_CONFIDENCE_TOO_LOW")
    return OverrideDecision(
        default_skill=default_skill,
        final_skill=default_skill if blockers else alternative_skill,
        verifier_called=True,
        override_applied=not blockers,
        override_reason="|".join(blockers) if blockers else "OVERRIDE_AUTHORIZED",
        default_probability=default.predicted_accept_probability,
        alternative_probability=alternative.predicted_accept_probability,
    )
