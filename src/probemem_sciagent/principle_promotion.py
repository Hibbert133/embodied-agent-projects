"""Deterministic principle promotion gate."""

from __future__ import annotations

from dataclasses import dataclass

from src.probemem_sciagent.schemas import HypothesisRecord


@dataclass(frozen=True)
class PromotionThresholds:
    minimum_independent_seeds: int = 3
    minimum_support: int = 4
    maximum_contradictions: int = 1
    minimum_support_rate: float = 0.75
    minimum_targeted_verifications: int = 1
    most_recent_must_not_be_rejected: bool = True


def promotion_rejection_reasons(
    hypothesis: HypothesisRecord, thresholds: PromotionThresholds = PromotionThresholds(),
) -> tuple[str, ...]:
    reasons: list[str] = []
    if hypothesis.status != "SUPPORTED": reasons.append("HYPOTHESIS_NOT_SUPPORTED")
    if hypothesis.independent_seed_count < thresholds.minimum_independent_seeds: reasons.append("INSUFFICIENT_INDEPENDENT_SEEDS")
    if hypothesis.support_count < thresholds.minimum_support: reasons.append("INSUFFICIENT_SUPPORT")
    if hypothesis.contradiction_count > thresholds.maximum_contradictions: reasons.append("TOO_MANY_CONTRADICTIONS")
    if hypothesis.support_rate < thresholds.minimum_support_rate: reasons.append("LOW_SUPPORT_RATE")
    if hypothesis.targeted_verification_count < thresholds.minimum_targeted_verifications: reasons.append("NO_TARGETED_VERIFICATION")
    if thresholds.most_recent_must_not_be_rejected and hypothesis.most_recent_verification_status == "REJECTED": reasons.append("MOST_RECENT_REJECTED")
    return tuple(reasons)


def can_promote_hypothesis(
    hypothesis: HypothesisRecord, thresholds: PromotionThresholds = PromotionThresholds(),
) -> bool:
    return not promotion_rejection_reasons(hypothesis, thresholds)
