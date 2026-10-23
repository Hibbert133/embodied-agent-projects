"""Deterministic Monte Carlo comparison of two weighted Beta posteriors."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any

import numpy as np

from src.probemem_verifier.weighted_posterior import WeightedPosteriorEstimate


@dataclass(frozen=True)
class PosteriorComparison:
    default_skill: str
    alternative_skill: str
    default_posterior_mean: float
    alternative_posterior_mean: float
    expected_utility_gain: float
    probability_alternative_better: float
    sample_count: int
    sampling_seed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def derive_comparison_seed(base_seed: int, *, stage: str, method: str, episode_id: int) -> int:
    if base_seed < 0 or episode_id <= 0:
        raise ValueError("comparison seed provenance is invalid")
    payload = f"{base_seed}|{stage}|{method}|{episode_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def compare_posteriors(
    default: WeightedPosteriorEstimate,
    alternative: WeightedPosteriorEstimate,
    *, sample_count: int = 10000, sampling_seed: int,
) -> PosteriorComparison:
    if default.skill == alternative.skill or sample_count != 10000:
        raise ValueError("comparison requires distinct skills and exactly 10,000 samples")
    rng = np.random.default_rng(sampling_seed)
    default_samples = rng.beta(default.alpha, default.beta, sample_count)
    alternative_samples = rng.beta(alternative.alpha, alternative.beta, sample_count)
    return PosteriorComparison(
        default_skill=default.skill,
        alternative_skill=alternative.skill,
        default_posterior_mean=default.posterior_mean,
        alternative_posterior_mean=alternative.posterior_mean,
        expected_utility_gain=alternative.posterior_mean - default.posterior_mean,
        probability_alternative_better=float(np.mean(alternative_samples > default_samples)),
        sample_count=sample_count,
        sampling_seed=sampling_seed,
    )
