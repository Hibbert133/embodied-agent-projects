"""Frozen prospective attempt-level continuous-feedback policy."""

from __future__ import annotations

from dataclasses import dataclass

from src.probemem.tools import InterventionSkill


PROGRESS_THRESHOLD_METRES = 0.0


@dataclass(frozen=True)
class ContinuousFeedbackDecision:
    selected_skill: InterventionSkill | None
    reason: str


def decide_from_progress(*, first_status: str, first_observed_progress: float) -> ContinuousFeedbackDecision:
    if first_status == "ACCEPTED":
        return ContinuousFeedbackDecision(None, "first_verification_accepted_stop")
    if first_status not in {"INCONCLUSIVE", "REJECTED"}:
        raise ValueError(f"unsupported first verification status: {first_status}")
    if first_observed_progress > PROGRESS_THRESHOLD_METRES:
        return ContinuousFeedbackDecision(InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY, "positive_progress_repeat_retry")
    return ContinuousFeedbackDecision(InterventionSkill.BOUNDED_PLANAR_COMPENSATION, "nonpositive_progress_switch_compensation")
