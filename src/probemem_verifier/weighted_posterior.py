"""Query-conditioned weighted Beta posteriors over chronological action memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Sequence

import numpy as np
from scipy.stats import beta as beta_distribution

from src.probemem.regime_memory import (
    ACTION_SKILLS,
    ProbeRegimeSignature,
    RegimeActionExperience,
    RegimeActionMemory,
    normalized_regime_distance,
    regime_distance_scales,
)
from src.reasoning.evidence import validate_no_oracle_evidence


@dataclass(frozen=True)
class WeightedPosteriorEstimate:
    skill: str
    scope: str
    alpha: float
    beta: float
    posterior_mean: float
    posterior_variance: float
    credible_lower: float
    credible_upper: float
    nearest_distance: float | None
    weighted_coverage: float
    effective_sample_size: float
    weighted_contradiction_rate: float
    record_ids: tuple[str, ...]
    record_weights: tuple[float, ...]
    supporting_record_ids: tuple[str, ...]
    contradicting_record_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.skill not in {skill.value for skill in ACTION_SKILLS}:
            raise ValueError("weighted posterior requires a registered skill")
        if self.scope not in {"global", "recent"}:
            raise ValueError("weighted posterior scope is invalid")
        if self.alpha <= 0 or self.beta <= 0:
            raise ValueError("Beta parameters must be positive")
        if len(self.record_ids) != len(set(self.record_ids)):
            raise ValueError("duplicate record IDs cannot inflate posterior evidence")
        if len(self.record_ids) != len(self.record_weights):
            raise ValueError("posterior record IDs and weights disagree")
        numeric = (
            self.alpha, self.beta, self.posterior_mean, self.posterior_variance,
            self.credible_lower, self.credible_upper, self.weighted_coverage,
            self.effective_sample_size, self.weighted_contradiction_rate,
            *self.record_weights,
        )
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("weighted posterior values must be finite")
        if not 0 <= self.posterior_mean <= 1 or not 0 <= self.credible_lower <= self.credible_upper <= 1:
            raise ValueError("posterior probability or interval is invalid")
        if not 0 <= self.weighted_contradiction_rate <= 1:
            raise ValueError("weighted contradiction rate must be in [0, 1]")
        if self.nearest_distance is not None and (not math.isfinite(self.nearest_distance) or self.nearest_distance < 0):
            raise ValueError("nearest distance is invalid")
        if not self.record_ids and any((self.weighted_coverage, self.effective_sample_size)):
            raise ValueError("empty posterior cannot have memory coverage")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("record_ids", "record_weights", "supporting_record_ids", "contradicting_record_ids"):
            value[key] = list(value[key])
        return value


@dataclass(frozen=True)
class QueryConditionedCandidatePosterior:
    skill: str
    global_posterior: WeightedPosteriorEstimate
    recent_posterior: WeightedPosteriorEstimate

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "global_posterior": self.global_posterior.to_dict(),
            "recent_posterior": self.recent_posterior.to_dict(),
        }


class QueryConditionedCalibratedVerifier:
    """Frozen distance-weighted posterior estimator; it never selects an action."""

    def __init__(
        self, *, top_k: int = 10, recent_count: int = 10,
        prior_alpha: float = 1.0, prior_beta: float = 1.0,
        credible_level: float = 0.95,
    ) -> None:
        if top_k <= 0 or recent_count <= 0 or prior_alpha <= 0 or prior_beta <= 0:
            raise ValueError("weighted verifier limits and priors must be positive")
        if not 0 < credible_level < 1:
            raise ValueError("credible level must be in (0, 1)")
        self.top_k = top_k
        self.recent_count = recent_count
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        self.credible_level = credible_level

    def verify_both(
        self, memory: RegimeActionMemory, query: ProbeRegimeSignature, *, episode_id: int,
    ) -> dict[str, QueryConditionedCandidatePosterior]:
        if query.episode_id != episode_id:
            raise ValueError("query and chronological cutoff differ")
        all_prior = memory.prior(episode_id)
        scales = regime_distance_scales(all_prior)
        result: dict[str, QueryConditionedCandidatePosterior] = {}
        for skill in ACTION_SKILLS:
            action_prior = memory.prior(episode_id, skill)
            ranked = tuple(sorted(
                action_prior,
                key=lambda record: (
                    normalized_regime_distance(query, record.probe_signature, scales),
                    record.episode_id,
                ),
            )[:self.top_k])
            recent = tuple(action_prior[-self.recent_count:])
            result[skill.value] = QueryConditionedCandidatePosterior(
                skill=skill.value,
                global_posterior=self._estimate(skill.value, "global", ranked, query, scales),
                recent_posterior=self._estimate(skill.value, "recent", recent, query, scales),
            )
        validate_no_oracle_evidence({key: value.to_dict() for key, value in result.items()})
        return result

    def _estimate(
        self, skill: str, scope: str, records: Sequence[RegimeActionExperience],
        query: ProbeRegimeSignature, scales: np.ndarray,
    ) -> WeightedPosteriorEstimate:
        ids = tuple(record.record_id for record in records)
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate record IDs cannot inflate effective sample size")
        distances = tuple(normalized_regime_distance(query, record.probe_signature, scales) for record in records)
        weights = tuple(1.0 / (1.0 + distance) for distance in distances)
        accepted = sum(weight for weight, record in zip(weights, records) if record.observed_status == "ACCEPTED")
        unresolved = sum(weight for weight, record in zip(weights, records) if record.observed_status == "INCONCLUSIVE")
        rejected = sum(weight for weight, record in zip(weights, records) if record.observed_status == "REJECTED")
        alpha = self.prior_alpha + accepted + 0.5 * unresolved
        beta = self.prior_beta + rejected + 0.5 * unresolved
        mean = alpha / (alpha + beta)
        variance = alpha * beta / ((alpha + beta) ** 2 * (alpha + beta + 1.0))
        tail = (1.0 - self.credible_level) / 2.0
        lower, upper = beta_distribution.ppf((tail, 1.0 - tail), alpha, beta)
        coverage = sum(weights)
        squared = sum(weight * weight for weight in weights)
        ess = 0.0 if not weights else coverage * coverage / squared
        return WeightedPosteriorEstimate(
            skill=skill, scope=scope, alpha=float(alpha), beta=float(beta),
            posterior_mean=float(mean), posterior_variance=float(variance),
            credible_lower=float(lower), credible_upper=float(upper),
            nearest_distance=None if not distances else float(min(distances)),
            weighted_coverage=float(coverage), effective_sample_size=float(ess),
            weighted_contradiction_rate=0.0 if coverage == 0 else float(rejected / coverage),
            record_ids=ids, record_weights=tuple(float(value) for value in weights),
            supporting_record_ids=tuple(record.record_id for record in records if record.observed_status == "ACCEPTED"),
            contradicting_record_ids=tuple(record.record_id for record in records if record.observed_status == "REJECTED"),
        )
