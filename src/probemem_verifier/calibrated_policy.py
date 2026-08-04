"""Frozen-admission policies for weighted and calibrated verifier methods."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from src.probemem.persistent_regime import FROZEN_CONSISTENCY_THRESHOLD
from src.probemem.regime_memory import ACTION_SKILLS, ProbeRegimeSignature, RegimeActionMemory
from src.probemem_verifier.admission import AdmissionDecision, assess_admission
from src.probemem_verifier.applicability import ApplicabilityAssessment, ApplicabilityThresholds, assess_applicability
from src.probemem_verifier.calibrated_override_guard import CalibratedGuardThresholds, CalibratedOverrideDecision, decide_calibrated_override
from src.probemem_verifier.candidate_verifier import AdmissionMemorySignals, CandidateMemorySummary, build_candidate_memory_summaries, inspect_admission_memory
from src.probemem_verifier.override_guard import decide_override
from src.probemem_verifier.posterior_comparison import PosteriorComparison, compare_posteriors, derive_comparison_seed
from src.probemem_verifier.schemas import CandidateVerification, DeterministicProposal, OverrideDecision
from src.probemem_verifier.weighted_posterior import QueryConditionedCalibratedVerifier, QueryConditionedCandidatePosterior


@dataclass(frozen=True)
class WeightedPolicyDecision:
    proposal: DeterministicProposal
    admission: AdmissionDecision
    memory_signals: AdmissionMemorySignals
    candidate_summaries: dict[str, CandidateMemorySummary]
    weighted_posteriors: dict[str, QueryConditionedCandidatePosterior]
    v1_candidate_verifications: dict[str, CandidateVerification]
    applicability: ApplicabilityAssessment | None
    comparison: PosteriorComparison | None
    override: OverrideDecision | CalibratedOverrideDecision
    verifier_latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal": self.proposal.to_dict(), "admission": self.admission.to_dict(),
            "memory_signals": self.memory_signals.to_dict(),
            "candidate_summaries": {key: value.to_dict() for key, value in self.candidate_summaries.items()},
            "weighted_posteriors": {key: value.to_dict() for key, value in self.weighted_posteriors.items()},
            "v1_candidate_verifications": {key: value.to_dict() for key, value in self.v1_candidate_verifications.items()},
            "applicability": None if self.applicability is None else self.applicability.to_dict(),
            "comparison": None if self.comparison is None else self.comparison.to_dict(),
            "override": self.override.to_dict(), "verifier_latency_ms": self.verifier_latency_ms,
        }


class WeightedVerifierPolicy:
    def __init__(
        self, *, mode: str, stage: str, comparison_seed: int, ambiguity_margin: float = 0.05,
        verifier: QueryConditionedCalibratedVerifier | None = None,
        applicability_thresholds: ApplicabilityThresholds | None = None,
        guard_thresholds: CalibratedGuardThresholds | None = None,
        v1_probability_margin: float = 0.15, v1_coverage_minimum: int = 3,
        v1_contradiction_maximum: float = 0.30, v1_confidence_minimum: float = 0.70,
    ) -> None:
        if mode not in {"weighted_v1_guard", "calibrated_v2"}:
            raise ValueError("unsupported weighted verifier policy mode")
        if mode == "calibrated_v2" and (applicability_thresholds is None or guard_thresholds is None):
            raise ValueError("calibrated policy requires frozen thresholds")
        self.mode, self.stage, self.comparison_seed = mode, stage, comparison_seed
        self.ambiguity_margin, self.verifier = ambiguity_margin, verifier or QueryConditionedCalibratedVerifier()
        self.applicability_thresholds, self.guard_thresholds = applicability_thresholds, guard_thresholds
        self.v1_probability_margin, self.v1_coverage_minimum = v1_probability_margin, v1_coverage_minimum
        self.v1_contradiction_maximum, self.v1_confidence_minimum = v1_contradiction_maximum, v1_confidence_minimum

    def decide(self, *, score: float, signature: ProbeRegimeSignature, memory: RegimeActionMemory, episode_id: int) -> WeightedPolicyDecision:
        default = "INDEPENDENT_STOCHASTIC_RETRY" if score > FROZEN_CONSISTENCY_THRESHOLD else "BOUNDED_PLANAR_COMPENSATION"
        proposal = DeterministicProposal(default, float(score), FROZEN_CONSISTENCY_THRESHOLD, abs(float(score) - FROZEN_CONSISTENCY_THRESHOLD))
        summaries = build_candidate_memory_summaries(memory, signature, episode_id=episode_id)
        signals = inspect_admission_memory(summaries)
        admission = assess_admission(proposal.confidence_margin, signals.memory_conflict, signals.memory_coverage, ambiguity_margin=self.ambiguity_margin, recent_contradiction=signals.recent_contradiction)
        if not admission.verifier_called:
            override = (
                decide_override(default_skill=default, verifier_called=False, candidates=None, summaries=None, memory_signals=None)
                if self.mode == "weighted_v1_guard"
                else decide_calibrated_override(default_skill=default, verifier_called=False, candidates=None, applicability=None, comparison=None, thresholds=self.guard_thresholds)
            )
            return WeightedPolicyDecision(proposal, admission, signals, {}, {}, {}, None, None, override, 0.0)
        started = perf_counter()
        posteriors = self.verifier.verify_both(memory, signature, episode_id=episode_id)
        alternative = next(skill.value for skill in ACTION_SKILLS if skill.value != default)
        seed = derive_comparison_seed(self.comparison_seed, stage=self.stage, method=self.mode, episode_id=episode_id)
        comparison = compare_posteriors(posteriors[default].global_posterior, posteriors[alternative].global_posterior, sampling_seed=seed)
        v1_candidates = {skill: _as_v1_candidate(bundle) for skill, bundle in posteriors.items()}
        applicability = None
        if self.mode == "weighted_v1_guard":
            override = decide_override(default_skill=default, verifier_called=True, candidates=v1_candidates, summaries=summaries, memory_signals=signals, probability_margin_minimum=self.v1_probability_margin, coverage_minimum=self.v1_coverage_minimum, contradiction_rate_maximum=self.v1_contradiction_maximum, confidence_minimum=self.v1_confidence_minimum)
        else:
            applicability = assess_applicability(posteriors, self.applicability_thresholds)
            override = decide_calibrated_override(default_skill=default, verifier_called=True, candidates=posteriors, applicability=applicability, comparison=comparison, thresholds=self.guard_thresholds)
        return WeightedPolicyDecision(proposal, admission, signals, summaries, posteriors, v1_candidates, applicability, comparison, override, (perf_counter() - started) * 1000.0)


def _as_v1_candidate(bundle: QueryConditionedCandidatePosterior) -> CandidateVerification:
    estimate = bundle.global_posterior
    probability = estimate.posterior_mean
    status = "ACCEPTED" if probability >= 0.70 else "REJECTED" if probability <= 0.30 else "INCONCLUSIVE"
    return CandidateVerification(bundle.skill, probability, status, probability, bool(estimate.record_ids), len(estimate.record_ids), estimate.supporting_record_ids, estimate.contradicting_record_ids)
