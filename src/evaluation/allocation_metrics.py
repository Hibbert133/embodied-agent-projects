"""Pure metrics for the frozen budgeted evidence-allocation experiment."""

from __future__ import annotations

from math import sqrt
from typing import Sequence

import numpy as np


def accuracy(truth: Sequence[str], prediction: Sequence[str]) -> float | None:
    _validate_equal_nonempty(truth, prediction)
    if not truth:
        return None
    return sum(a == b for a, b in zip(truth, prediction)) / len(truth)


def balanced_accuracy(
    truth: Sequence[str], prediction: Sequence[str]
) -> float | None:
    _validate_equal_nonempty(truth, prediction)
    labels = sorted(set(truth))
    if len(labels) < 2:
        return None
    recalls = []
    for label in labels:
        indices = [index for index, value in enumerate(truth) if value == label]
        recalls.append(
            sum(prediction[index] == label for index in indices) / len(indices)
        )
    return sum(recalls) / len(recalls)


def wilson_interval(
    successes: int, total: int, *, z: float = 1.959963984540054
) -> tuple[float, float] | None:
    if total <= 0 or not 0 <= successes <= total:
        return None
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total**2))
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def roc_auc(labels: Sequence[bool], scores: Sequence[float]) -> float | None:
    """Mann-Whitney ROC AUC with average ranks for tied scores."""

    _validate_equal_nonempty(labels, scores)
    positive = sum(labels)
    negative = len(labels) - positive
    if positive == 0 or negative == 0:
        return None
    ordered = sorted(enumerate(scores), key=lambda item: (float(item[1]), item[0]))
    ranks = [0.0] * len(scores)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and float(ordered[end][1]) == float(ordered[start][1]):
            end += 1
        average_rank = ((start + 1) + end) / 2.0
        for index, _ in ordered[start:end]:
            ranks[index] = average_rank
        start = end
    positive_rank_sum = sum(rank for rank, label in zip(ranks, labels) if label)
    return (positive_rank_sum - positive * (positive + 1) / 2.0) / (
        positive * negative
    )


def average_precision(labels: Sequence[bool], scores: Sequence[float]) -> float | None:
    """PR AUC as non-interpolated average precision, with tied-score groups."""

    _validate_equal_nonempty(labels, scores)
    positive = sum(labels)
    negative = len(labels) - positive
    if positive == 0 or negative == 0:
        return None
    thresholds = sorted({float(score) for score in scores}, reverse=True)
    previous_recall = 0.0
    result = 0.0
    for threshold in thresholds:
        selected = [float(score) >= threshold for score in scores]
        true_positive = sum(label and chosen for label, chosen in zip(labels, selected))
        false_positive = sum(
            (not label) and chosen for label, chosen in zip(labels, selected)
        )
        recall = true_positive / positive
        precision = true_positive / (true_positive + false_positive)
        result += (recall - previous_recall) * precision
        previous_recall = recall
    return result


def paired_win_tie_loss(
    left: Sequence[bool], right: Sequence[bool]
) -> dict[str, int]:
    _validate_equal_nonempty(left, right)
    return {
        "win": sum(bool(a) and not bool(b) for a, b in zip(left, right)),
        "tie": sum(bool(a) == bool(b) for a, b in zip(left, right)),
        "loss": sum(not bool(a) and bool(b) for a, b in zip(left, right)),
    }


def stratified_paired_bootstrap_difference(
    left: Sequence[float],
    right: Sequence[float],
    strata: Sequence[str],
    *,
    repetitions: int,
    seed: int,
) -> dict[str, float | int] | None:
    """Bootstrap the paired mean difference, resampling within mechanisms."""

    _validate_equal_nonempty(left, right)
    if len(left) != len(strata):
        raise ValueError("paired bootstrap strata length differs from values")
    if not left:
        return None
    if repetitions <= 0:
        raise ValueError("bootstrap repetitions must be positive")
    by_stratum = {
        label: np.asarray(
            [index for index, value in enumerate(strata) if value == label], dtype=int
        )
        for label in sorted(set(strata))
    }
    differences = np.asarray(left, dtype=float) - np.asarray(right, dtype=float)
    generator = np.random.default_rng(seed)
    samples = np.empty(repetitions, dtype=float)
    for repetition in range(repetitions):
        chosen = np.concatenate(
            [generator.choice(indices, size=len(indices), replace=True) for indices in by_stratum.values()]
        )
        samples[repetition] = float(np.mean(differences[chosen]))
    return {
        "paired_units": len(left),
        "repetitions": repetitions,
        "mean_difference": float(np.mean(differences)),
        "ci95_lower": float(np.quantile(samples, 0.025)),
        "ci95_upper": float(np.quantile(samples, 0.975)),
    }


def _validate_equal_nonempty(left: Sequence[object], right: Sequence[object]) -> None:
    if len(left) != len(right):
        raise ValueError("metric inputs must have equal lengths")
