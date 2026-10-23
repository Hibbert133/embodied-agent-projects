"""Deterministic action-outcome posteriors for development-only ACR replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np

from src.probemem.models import InterventionSkill


OUTCOMES = ("ACCEPTED", "INCONCLUSIVE", "REJECTED")
STATUS_UTILITY = np.asarray((1.0, 0.5, 0.0), dtype=float)
METHODS = (
    "always_compensation",
    "always_retry",
    "accepted_only_last",
    "posterior_greedy",
    "posterior_abstain",
)
COMPENSATION = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


@dataclass(frozen=True)
class ObservedActionOutcome:
    episode_id: int
    intervention_skill: InterventionSkill
    verification_status: str

    def __post_init__(self) -> None:
        if self.episode_id <= 0 or self.intervention_skill not in {COMPENSATION, RETRY}:
            raise ValueError("invalid chronological action outcome")
        if self.verification_status not in OUTCOMES:
            raise ValueError("invalid verification status")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["intervention_skill"] = self.intervention_skill.value
        return value


@dataclass(frozen=True)
class DistributionalDecision:
    method: str
    episode_id: int
    selected_skill: InterventionSkill | None
    reason: str
    compensation_alpha: tuple[float, float, float]
    retry_alpha: tuple[float, float, float]
    compensation_mean_utility: float
    retry_mean_utility: float
    probability_compensation_better: float | None
    history_episode_ids: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "selected_skill": self.selected_skill.value if self.selected_skill else None,
        }


def _validate_history(history: Sequence[ObservedActionOutcome], episode_id: int) -> None:
    if episode_id <= 0:
        raise ValueError("episode_id must be positive")
    ids = [item.episode_id for item in history]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ValueError("history must be strictly chronological with one selected outcome per episode")
    if any(item.episode_id >= episode_id for item in history):
        raise ValueError("current or future outcome cannot enter a decision")


def posterior_alpha(
    history: Sequence[ObservedActionOutcome], skill: InterventionSkill
) -> tuple[float, float, float]:
    if skill not in {COMPENSATION, RETRY}:
        raise ValueError("posterior requires a registered skill")
    counts = {status: 0 for status in OUTCOMES}
    for item in history:
        if item.intervention_skill is skill:
            counts[item.verification_status] += 1
    return tuple(1.0 + counts[status] for status in OUTCOMES)


def mean_utility(alpha: Sequence[float]) -> float:
    values = np.asarray(alpha, dtype=float)
    if values.shape != (3,) or np.any(values <= 0):
        raise ValueError("Dirichlet alpha must contain three positive values")
    return float(np.dot(values / values.sum(), STATUS_UTILITY))


def decide_distributional_action(
    *,
    method: str,
    episode_id: int,
    operational_index: int,
    history: Sequence[ObservedActionOutcome],
    exploration_episodes: int = 8,
    superiority_probability: float = 0.90,
    monte_carlo_samples: int = 20000,
    sampling_seed: int,
) -> DistributionalDecision:
    if method not in METHODS or operational_index <= 0:
        raise ValueError("unsupported method or operational index")
    if exploration_episodes <= 0 or monte_carlo_samples <= 0:
        raise ValueError("exploration and Monte Carlo budgets must be positive")
    if not 0.5 < superiority_probability < 1.0:
        raise ValueError("superiority probability must be in (0.5, 1)")
    _validate_history(history, episode_id)
    comp_alpha = posterior_alpha(history, COMPENSATION)
    retry_alpha = posterior_alpha(history, RETRY)
    comp_mean, retry_mean = mean_utility(comp_alpha), mean_utility(retry_alpha)
    probability: float | None = None

    if method == "always_compensation":
        selected, reason = COMPENSATION, "fixed compensation baseline"
    elif method == "always_retry":
        selected, reason = RETRY, "fixed retry baseline"
    elif operational_index <= exploration_episodes:
        selected = COMPENSATION if operational_index % 2 else RETRY
        reason = "frozen alternating exploration"
    elif method == "accepted_only_last":
        accepted = [item for item in history if item.verification_status == "ACCEPTED"]
        selected = accepted[-1].intervention_skill if accepted else RETRY
        reason = "reuse most recent accepted selected intervention" if accepted else "registered retry fallback"
    else:
        rng = np.random.default_rng(int(sampling_seed))
        comp_samples = rng.dirichlet(comp_alpha, size=monte_carlo_samples) @ STATUS_UTILITY
        retry_samples = rng.dirichlet(retry_alpha, size=monte_carlo_samples) @ STATUS_UTILITY
        probability = float(np.mean(comp_samples > retry_samples))
        if method == "posterior_greedy":
            selected = COMPENSATION if comp_mean > retry_mean else RETRY
            reason = "higher posterior mean action utility"
        elif probability >= superiority_probability:
            selected, reason = COMPENSATION, "compensation posterior superiority passed"
        elif probability <= 1.0 - superiority_probability:
            selected, reason = RETRY, "retry posterior superiority passed"
        else:
            selected, reason = None, "posterior action utilities remain insufficiently separated"

    return DistributionalDecision(
        method=method,
        episode_id=episode_id,
        selected_skill=selected,
        reason=reason,
        compensation_alpha=comp_alpha,
        retry_alpha=retry_alpha,
        compensation_mean_utility=comp_mean,
        retry_mean_utility=retry_mean,
        probability_compensation_better=probability,
        history_episode_ids=tuple(item.episode_id for item in history),
    )
