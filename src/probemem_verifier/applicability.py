"""Explicit query applicability checks for weighted action posteriors."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from src.probemem.regime_memory import ACTION_SKILLS
from src.probemem_verifier.weighted_posterior import QueryConditionedCandidatePosterior


@dataclass(frozen=True)
class ApplicabilityThresholds:
    minimum_effective_sample_size: float
    maximum_nearest_distance: float
    minimum_weighted_coverage: float
    maximum_weighted_contradiction_rate: float

    def __post_init__(self) -> None:
        if min(
            self.minimum_effective_sample_size,
            self.maximum_nearest_distance,
            self.minimum_weighted_coverage,
            self.maximum_weighted_contradiction_rate,
        ) < 0 or self.maximum_weighted_contradiction_rate > 1:
            raise ValueError("applicability thresholds are invalid")


@dataclass(frozen=True)
class MemoryApplicability:
    skill: str
    applicable: bool
    rejection_reasons: tuple[str, ...]
    condition_checks: tuple[tuple[str, bool], ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["rejection_reasons"] = list(self.rejection_reasons)
        value["condition_checks"] = {key: passed for key, passed in self.condition_checks}
        return value


@dataclass(frozen=True)
class ApplicabilityAssessment:
    candidates: dict[str, MemoryApplicability]
    global_preference: str | None
    recent_preference: str | None
    preference_agreement: bool
    preference_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": {key: value.to_dict() for key, value in self.candidates.items()},
            "global_preference": self.global_preference,
            "recent_preference": self.recent_preference,
            "preference_agreement": self.preference_agreement,
            "preference_reason": self.preference_reason,
        }


def assess_applicability(
    candidates: Mapping[str, QueryConditionedCandidatePosterior],
    thresholds: ApplicabilityThresholds,
) -> ApplicabilityAssessment:
    required = {skill.value for skill in ACTION_SKILLS}
    if set(candidates) != required:
        raise ValueError("applicability requires both registered actions")
    global_preference = _preference(candidates, "global")
    recent_preference = _preference(candidates, "recent")
    agreement = global_preference is not None and global_preference == recent_preference
    preference_reason = (
        "GLOBAL_RECENT_AGREEMENT" if agreement
        else "GLOBAL_RECENT_UNRESOLVED" if global_preference is None or recent_preference is None
        else "GLOBAL_RECENT_CONFLICT"
    )
    result: dict[str, MemoryApplicability] = {}
    for skill, bundle in candidates.items():
        posterior = bundle.global_posterior
        checks = (
            ("EFFECTIVE_SAMPLE_SIZE", posterior.effective_sample_size >= thresholds.minimum_effective_sample_size),
            ("LOCAL_COVERAGE", posterior.nearest_distance is not None and posterior.nearest_distance <= thresholds.maximum_nearest_distance),
            ("WEIGHTED_COVERAGE", posterior.weighted_coverage >= thresholds.minimum_weighted_coverage),
            ("CONTRADICTION_RATE", posterior.weighted_contradiction_rate <= thresholds.maximum_weighted_contradiction_rate),
            ("GLOBAL_RECENT_AGREEMENT", agreement),
        )
        names = {
            "EFFECTIVE_SAMPLE_SIZE": "LOW_EFFECTIVE_SAMPLE_SIZE",
            "LOCAL_COVERAGE": "OUTSIDE_LOCAL_COVERAGE",
            "WEIGHTED_COVERAGE": "LOW_WEIGHTED_COVERAGE",
            "CONTRADICTION_RATE": "HIGH_CONTRADICTION",
            "GLOBAL_RECENT_AGREEMENT": preference_reason,
        }
        reasons = tuple(names[name] for name, passed in checks if not passed)
        result[skill] = MemoryApplicability(skill, not reasons, reasons, checks)
    return ApplicabilityAssessment(result, global_preference, recent_preference, agreement, preference_reason)


def _preference(candidates: Mapping[str, QueryConditionedCandidatePosterior], scope: str) -> str | None:
    ordered = [skill.value for skill in ACTION_SKILLS]
    values = [
        (candidates[skill].global_posterior if scope == "global" else candidates[skill].recent_posterior).posterior_mean
        for skill in ordered
    ]
    if abs(values[0] - values[1]) <= 1e-12:
        return None
    return ordered[0] if values[0] > values[1] else ordered[1]
