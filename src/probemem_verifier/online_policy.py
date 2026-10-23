"""Host-owned budgeted policy combining admission, verification, and guard."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from src.probemem.persistent_regime import FROZEN_CONSISTENCY_THRESHOLD
from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionMemory
from src.probemem_verifier.admission import AdmissionDecision, assess_admission
from src.probemem_verifier.candidate_verifier import (
    AdmissionMemorySignals,
    CandidateMemorySummary,
    DeterministicBayesianVerifier,
    build_candidate_memory_summaries,
    inspect_admission_memory,
)
from src.probemem_verifier.override_guard import decide_override
from src.probemem_verifier.schemas import CandidateVerification, DeterministicProposal, OverrideDecision


@dataclass(frozen=True)
class PolicyDecision:
    proposal: DeterministicProposal
    admission: AdmissionDecision
    memory_signals: AdmissionMemorySignals
    candidate_summaries: dict[str, CandidateMemorySummary]
    candidate_verifications: dict[str, CandidateVerification]
    override: OverrideDecision
    verifier_latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal": self.proposal.to_dict(),
            "admission": self.admission.to_dict(),
            "memory_signals": self.memory_signals.to_dict(),
            "candidate_summaries": {key: value.to_dict() for key, value in self.candidate_summaries.items()},
            "candidate_verifications": {key: value.to_dict() for key, value in self.candidate_verifications.items()},
            "override": self.override.to_dict(),
            "verifier_latency_ms": self.verifier_latency_ms,
        }


class BudgetedVerifierPolicy:
    def __init__(
        self, *, mode: str, ambiguity_margin: float = 0.05,
        probability_margin_minimum: float = 0.15, coverage_minimum: int = 3,
        contradiction_rate_maximum: float = 0.30, confidence_minimum: float = 0.70,
        verifier: DeterministicBayesianVerifier | None = None,
    ) -> None:
        if mode not in {"frozen_deterministic", "always_on_verifier", "budgeted_verifier"}:
            raise ValueError("unsupported verifier-demo policy mode")
        self.mode = mode
        self.ambiguity_margin = ambiguity_margin
        self.probability_margin_minimum = probability_margin_minimum
        self.coverage_minimum = coverage_minimum
        self.contradiction_rate_maximum = contradiction_rate_maximum
        self.confidence_minimum = confidence_minimum
        self.verifier = verifier or DeterministicBayesianVerifier(
            accepted_status_threshold=confidence_minimum,
            rejected_status_threshold=1.0 - confidence_minimum,
        )

    def decide(
        self, *, score: float, signature: ProbeRegimeSignature,
        memory: RegimeActionMemory, episode_id: int,
    ) -> PolicyDecision:
        default = (
            "INDEPENDENT_STOCHASTIC_RETRY"
            if score > FROZEN_CONSISTENCY_THRESHOLD
            else "BOUNDED_PLANAR_COMPENSATION"
        )
        proposal = DeterministicProposal(
            default, float(score), FROZEN_CONSISTENCY_THRESHOLD,
            abs(float(score) - FROZEN_CONSISTENCY_THRESHOLD),
        )
        if self.mode == "frozen_deterministic":
            admission_summaries: dict[str, CandidateMemorySummary] = {}
            signals = AdmissionMemorySignals(False, 0.0, False, None, None)
        else:
            # Budgeted admission performs only the host-side scalar/ID scan.
            # Detailed summaries are exposed to a verifier only after admission.
            admission_summaries = build_candidate_memory_summaries(
                memory, signature, episode_id=episode_id,
            )
            signals = inspect_admission_memory(admission_summaries)
        admission = assess_admission(
            proposal.confidence_margin, signals.memory_conflict, signals.memory_coverage,
            ambiguity_margin=self.ambiguity_margin,
            recent_contradiction=signals.recent_contradiction,
        )
        verifier_called = (
            self.mode == "always_on_verifier"
            or (self.mode == "budgeted_verifier" and admission.verifier_called)
        )
        if self.mode == "frozen_deterministic":
            verifier_called = False
        verifier_summaries = admission_summaries if verifier_called else {}
        verifications: dict[str, CandidateVerification] = {}
        latency_ms = 0.0
        if verifier_called:
            started = perf_counter()
            try:
                verifications = self.verifier.verify_both(verifier_summaries)
            except Exception:
                verifications = {}
            latency_ms = (perf_counter() - started) * 1000.0
        override = decide_override(
            default_skill=default, verifier_called=verifier_called,
            candidates=verifications or None, summaries=verifier_summaries or None,
            memory_signals=signals,
            probability_margin_minimum=self.probability_margin_minimum,
            coverage_minimum=self.coverage_minimum,
            contradiction_rate_maximum=self.contradiction_rate_maximum,
            confidence_minimum=self.confidence_minimum,
        )
        return PolicyDecision(
            proposal, admission, signals, verifier_summaries, verifications, override, latency_ms,
        )
