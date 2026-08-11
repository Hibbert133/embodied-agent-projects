"""Frozen distributional estimands for micro-probe identifiability v1.8."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Iterable, Sequence

from src.probemem_sciagent.schemas import CompensationProbeEvidence, RetryProbeEvidence


@dataclass(frozen=True)
class ProbeContrast:
    compensation_support: float
    retry_support: float
    probe_contrast: float


@dataclass(frozen=True)
class DistributionalTarget:
    compensation_accept_rate: float
    retry_accept_rate: float
    utility_margin: float
    decisive_label: str


def build_probe_contrast(
    compensation: CompensationProbeEvidence, retry: RetryProbeEvidence,
) -> ProbeContrast:
    compensation_support = (
        max(0.0, compensation.expected_direction_alignment)
        * compensation.response_consistency
        * float(compensation.contact_preserved)
    )
    retry_support = retry.positive_progress_rate * (1.0 - retry.severe_failure_rate)
    return ProbeContrast(compensation_support, retry_support, compensation_support - retry_support)


def build_distributional_target(
    compensation_statuses: Sequence[str], retry_statuses: Sequence[str], *, decisive_margin: float,
) -> DistributionalTarget:
    if len(compensation_statuses) != len(retry_statuses) or not compensation_statuses:
        raise ValueError("paired non-empty realization sequences are required")
    if not 0.0 < decisive_margin <= 1.0:
        raise ValueError("decisive margin must be in (0, 1]")
    allowed = {"ACCEPTED", "INCONCLUSIVE", "REJECTED"}
    if any(value not in allowed for value in (*compensation_statuses, *retry_statuses)):
        raise ValueError("invalid verification status")
    compensation_rate = sum(value == "ACCEPTED" for value in compensation_statuses) / len(compensation_statuses)
    retry_rate = sum(value == "ACCEPTED" for value in retry_statuses) / len(retry_statuses)
    margin = compensation_rate - retry_rate
    if margin >= decisive_margin:
        label = "COMPENSATION_SUPERIOR"
    elif margin <= -decisive_margin:
        label = "RETRY_SUPERIOR"
    else:
        label = "NON_DECISIVE"
    return DistributionalTarget(compensation_rate, retry_rate, margin, label)


def roc_auc(labels: Sequence[int], scores: Sequence[float]) -> float:
    if len(labels) != len(scores) or not labels:
        raise ValueError("labels and scores must be non-empty and aligned")
    positives = [score for label, score in zip(labels, scores) if label == 1]
    negatives = [score for label, score in zip(labels, scores) if label == 0]
    if len(positives) + len(negatives) != len(labels) or not positives or not negatives:
        raise ValueError("ROC AUC requires both binary classes")
    wins = sum(
        1.0 if positive > negative else (0.5 if positive == negative else 0.0)
        for positive in positives for negative in negatives
    )
    return wins / (len(positives) * len(negatives))


def spearman_rank_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("rank correlation requires aligned sequences")
    left_ranks = _average_ranks(left)
    right_ranks = _average_ranks(right)
    left_mean = sum(left_ranks) / len(left_ranks)
    right_mean = sum(right_ranks) / len(right_ranks)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left_ranks, right_ranks))
    left_ss = sum((x - left_mean) ** 2 for x in left_ranks)
    right_ss = sum((y - right_mean) ** 2 for y in right_ranks)
    denominator = math.sqrt(left_ss * right_ss)
    return 0.0 if denominator == 0.0 else numerator / denominator


def stratified_auc_bootstrap(
    labels: Sequence[int], scores: Sequence[float], *, samples: int, seed: int,
) -> tuple[float, float]:
    if samples <= 0:
        raise ValueError("bootstrap sample count must be positive")
    positive = [score for label, score in zip(labels, scores) if label == 1]
    negative = [score for label, score in zip(labels, scores) if label == 0]
    if not positive or not negative:
        raise ValueError("stratified bootstrap requires both classes")
    generator = random.Random(seed)
    values = []
    for _ in range(samples):
        resampled_positive = [generator.choice(positive) for _ in positive]
        resampled_negative = [generator.choice(negative) for _ in negative]
        values.append(roc_auc(
            [1] * len(resampled_positive) + [0] * len(resampled_negative),
            resampled_positive + resampled_negative,
        ))
    values.sort()
    return (_percentile(values, 0.025), _percentile(values, 0.975))


def candidate_winner_reversal_count(
    compensation_statuses: Sequence[str], retry_statuses: Sequence[str],
) -> int:
    if len(compensation_statuses) != len(retry_statuses):
        raise ValueError("candidate realizations must be paired")
    order = {"REJECTED": 0, "INCONCLUSIVE": 1, "ACCEPTED": 2}
    signs = {
        (order[compensation] > order[retry]) - (order[compensation] < order[retry])
        for compensation, retry in zip(compensation_statuses, retry_statuses)
    }
    return int(1 in signs and -1 in signs)


def _average_ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(indexed):
        stop = start + 1
        while stop < len(indexed) and indexed[stop][1] == indexed[start][1]:
            stop += 1
        rank = (start + 1 + stop) / 2.0
        for index, _ in indexed[start:stop]:
            ranks[index] = rank
        start = stop
    return ranks


def _percentile(values: Sequence[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(values[lower])
    fraction = position - lower
    return float(values[lower] + (values[upper] - values[lower]) * fraction)
