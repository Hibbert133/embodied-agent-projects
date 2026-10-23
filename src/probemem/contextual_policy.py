"""Bayesian contextual action-utility models for development-only ACR replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Sequence

import numpy as np

from src.probemem.distributional_policy import COMPENSATION, RETRY
from src.probemem.intervention_utility import INTERVENTION_APPLICABILITY_FEATURES
from src.probemem.models import InterventionSkill


CONTEXTUAL_METHODS = ("contextual_greedy", "contextual_abstain")


@dataclass(frozen=True)
class ContextualOutcome:
    episode_id: int
    intervention_skill: InterventionSkill
    utility: float
    evidence_values: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.episode_id <= 0 or self.intervention_skill not in {COMPENSATION, RETRY}:
            raise ValueError("invalid contextual action outcome")
        if self.utility not in {0.0, 0.5, 1.0}:
            raise ValueError("contextual utility must use the frozen ordinal values")
        if len(self.evidence_values) != len(INTERVENTION_APPLICABILITY_FEATURES):
            raise ValueError("contextual outcome has an invalid evidence signature")
        if not all(math.isfinite(value) for value in self.evidence_values):
            raise ValueError("contextual evidence values must be finite")


@dataclass(frozen=True)
class ContextualActionPrediction:
    intervention_skill: InterventionSkill
    history_count: int
    mean_utility: float
    latent_variance: float


@dataclass(frozen=True)
class ContextualDecision:
    method: str
    episode_id: int
    selected_skill: InterventionSkill | None
    reason: str
    compensation: ContextualActionPrediction
    retry: ContextualActionPrediction
    probability_compensation_better: float
    history_episode_ids: tuple[int, ...]
    standardization_episode_ids: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["selected_skill"] = self.selected_skill.value if self.selected_skill else None
        value["compensation"]["intervention_skill"] = self.compensation.intervention_skill.value
        value["retry"]["intervention_skill"] = self.retry.intervention_skill.value
        return value


def _validate_history(history: Sequence[ContextualOutcome], episode_id: int) -> None:
    ids = [item.episode_id for item in history]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ValueError("contextual history must contain one chronological outcome per episode")
    if any(item.episode_id >= episode_id for item in history):
        raise ValueError("current or future outcome cannot enter a contextual decision")


def _standardize(
    history: Sequence[ContextualOutcome], query: Sequence[float], *, epsilon: float
) -> tuple[np.ndarray, np.ndarray, tuple[int, ...]]:
    if epsilon <= 0:
        raise ValueError("standardization epsilon must be positive")
    query_array = np.asarray(query, dtype=float)
    if query_array.shape != (len(INTERVENTION_APPLICABILITY_FEATURES),):
        raise ValueError("query has an invalid contextual feature shape")
    if not history:
        return np.empty((0, query_array.size), dtype=float), query_array * 0.0, ()
    matrix = np.asarray([item.evidence_values for item in history], dtype=float)
    mean = np.mean(matrix, axis=0)
    scale = np.std(matrix, axis=0)
    scale[scale <= epsilon] = 1.0
    return (matrix - mean) / scale, (query_array - mean) / scale, tuple(item.episode_id for item in history)


def _predict_action(
    *,
    skill: InterventionSkill,
    history: Sequence[ContextualOutcome],
    standardized_history: np.ndarray,
    standardized_query: np.ndarray,
    prior_precision: float,
    noise_variance: float,
) -> ContextualActionPrediction:
    indices = [index for index, item in enumerate(history) if item.intervention_skill is skill]
    dimension = standardized_query.size + 1
    covariance = np.eye(dimension, dtype=float) / prior_precision
    coefficients = np.zeros(dimension, dtype=float)
    if indices:
        features = np.column_stack((np.ones(len(indices)), standardized_history[indices]))
        targets = np.asarray([history[index].utility - 0.5 for index in indices], dtype=float)
        precision = prior_precision * np.eye(dimension) + features.T @ features / noise_variance
        covariance = np.linalg.inv(precision)
        coefficients = covariance @ features.T @ targets / noise_variance
    query = np.concatenate(([1.0], standardized_query))
    mean = float(np.clip(0.5 + query @ coefficients, 0.0, 1.0))
    variance = float(max(query @ covariance @ query, 1e-12))
    return ContextualActionPrediction(skill, len(indices), mean, variance)


def decide_contextual_action(
    *,
    method: str,
    episode_id: int,
    operational_index: int,
    query_values: Sequence[float],
    history: Sequence[ContextualOutcome],
    exploration_episodes: int = 16,
    prior_precision: float = 1.0,
    noise_variance: float = 0.25,
    superiority_probability: float = 0.80,
    standardization_epsilon: float = 1e-12,
) -> ContextualDecision:
    if method not in CONTEXTUAL_METHODS or operational_index <= 0:
        raise ValueError("unsupported contextual method or operational index")
    if exploration_episodes <= 0 or prior_precision <= 0 or noise_variance <= 0:
        raise ValueError("contextual model constants must be positive")
    if not 0.5 < superiority_probability < 1.0:
        raise ValueError("contextual superiority probability must be in (0.5, 1)")
    _validate_history(history, episode_id)
    matrix, query, standardization_ids = _standardize(
        history, query_values, epsilon=standardization_epsilon
    )
    compensation = _predict_action(
        skill=COMPENSATION, history=history, standardized_history=matrix,
        standardized_query=query, prior_precision=prior_precision, noise_variance=noise_variance,
    )
    retry = _predict_action(
        skill=RETRY, history=history, standardized_history=matrix,
        standardized_query=query, prior_precision=prior_precision, noise_variance=noise_variance,
    )
    difference_mean = compensation.mean_utility - retry.mean_utility
    difference_std = math.sqrt(compensation.latent_variance + retry.latent_variance)
    probability = 0.5 * (1.0 + math.erf(difference_mean / difference_std / math.sqrt(2.0)))

    if operational_index <= exploration_episodes:
        selected = COMPENSATION if operational_index % 2 else RETRY
        reason = "frozen alternating contextual exploration"
    elif method == "contextual_greedy":
        selected = COMPENSATION if compensation.mean_utility > retry.mean_utility else RETRY
        reason = "higher contextual posterior mean utility"
    elif probability >= superiority_probability:
        selected, reason = COMPENSATION, "contextual compensation superiority passed"
    elif probability <= 1.0 - superiority_probability:
        selected, reason = RETRY, "contextual retry superiority passed"
    else:
        selected, reason = None, "context-conditioned action utilities remain insufficiently separated"

    return ContextualDecision(
        method=method,
        episode_id=episode_id,
        selected_skill=selected,
        reason=reason,
        compensation=compensation,
        retry=retry,
        probability_compensation_better=probability,
        history_episode_ids=tuple(item.episode_id for item in history),
        standardization_episode_ids=standardization_ids,
    )
