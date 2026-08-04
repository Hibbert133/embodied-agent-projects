"""Fail-closed calibrated override guard with complete condition audit."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from src.probemem.compact_evidence import REGISTERED_SKILLS
from src.probemem_verifier.applicability import ApplicabilityAssessment
from src.probemem_verifier.posterior_comparison import PosteriorComparison
from src.probemem_verifier.weighted_posterior import QueryConditionedCandidatePosterior


@dataclass(frozen=True)
class CalibratedGuardThresholds:
    minimum_superiority_probability: float
    minimum_expected_utility_gain: float
    minimum_alternative_effective_sample_size: float


@dataclass(frozen=True)
class CalibratedOverrideDecision:
    default_skill: str
    final_skill: str
    verifier_called: bool
    override_applied: bool
    override_reason: str
    default_probability: float | None
    alternative_probability: float | None
    condition_checks: tuple[tuple[str, bool], ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["condition_checks"] = {key: passed for key, passed in self.condition_checks}
        return value


def decide_calibrated_override(
    *, default_skill: str, verifier_called: bool,
    candidates: Mapping[str, QueryConditionedCandidatePosterior] | None,
    applicability: ApplicabilityAssessment | None,
    comparison: PosteriorComparison | None,
    thresholds: CalibratedGuardThresholds,
) -> CalibratedOverrideDecision:
    if default_skill not in REGISTERED_SKILLS:
        raise ValueError("calibrated guard default must be registered")
    alternative_skill = next(skill for skill in REGISTERED_SKILLS if skill != default_skill)
    if not verifier_called:
        return CalibratedOverrideDecision(default_skill, default_skill, False, False, "VERIFIER_BYPASSED", None, None, ())
    if candidates is None or applicability is None or comparison is None or set(candidates) != set(REGISTERED_SKILLS):
        return CalibratedOverrideDecision(default_skill, default_skill, True, False, "VERIFIER_FAIL_CLOSED", None, None, ())
    default = candidates[default_skill].global_posterior
    alternative = candidates[alternative_skill].global_posterior
    checks = (
        ("DEFAULT_MEMORY_APPLICABLE", applicability.candidates[default_skill].applicable),
        ("ALTERNATIVE_MEMORY_APPLICABLE", applicability.candidates[alternative_skill].applicable),
        ("SUPERIORITY_PROBABILITY", comparison.probability_alternative_better >= thresholds.minimum_superiority_probability),
        ("EXPECTED_UTILITY_GAIN", comparison.expected_utility_gain >= thresholds.minimum_expected_utility_gain),
        ("ALTERNATIVE_EFFECTIVE_SAMPLE_SIZE", alternative.effective_sample_size >= thresholds.minimum_alternative_effective_sample_size),
        ("CREDIBLE_INTERVAL_SEPARATION", alternative.credible_lower > default.credible_upper),
        ("GLOBAL_RECENT_AGREEMENT", applicability.preference_agreement and applicability.global_preference == alternative_skill),
        ("ALTERNATIVE_CONTRADICTION", "HIGH_CONTRADICTION" not in applicability.candidates[alternative_skill].rejection_reasons),
    )
    blockers = tuple(name for name, passed in checks if not passed)
    return CalibratedOverrideDecision(
        default_skill=default_skill,
        final_skill=default_skill if blockers else alternative_skill,
        verifier_called=True,
        override_applied=not blockers,
        override_reason="|".join(blockers) if blockers else "OVERRIDE_AUTHORIZED",
        default_probability=default.posterior_mean,
        alternative_probability=alternative.posterior_mean,
        condition_checks=checks,
    )
