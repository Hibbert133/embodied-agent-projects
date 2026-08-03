"""Leakage-explicit metrics for the post-hoc retry-value audit."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any


def binary_roc_auc(labels: Sequence[bool], scores: Sequence[float]) -> float | None:
    """Return pairwise, tie-aware ROC AUC or ``None`` for a single-class set."""
    if len(labels) != len(scores) or not labels:
        raise ValueError("labels and scores must be equal-length and non-empty")
    positive = [score for label, score in zip(labels, scores) if label]
    negative = [score for label, score in zip(labels, scores) if not label]
    if not positive or not negative:
        return None
    wins = sum(
        1.0 if pos > neg else 0.5 if pos == neg else 0.0
        for pos in positive
        for neg in negative
    )
    return wins / (len(positive) * len(negative))


def average_precision(labels: Sequence[bool], scores: Sequence[float]) -> float | None:
    """Return grouped-threshold average precision or ``None`` without positives."""
    if len(labels) != len(scores) or not labels:
        raise ValueError("labels and scores must be equal-length and non-empty")
    positives = sum(labels)
    if positives == 0 or positives == len(labels):
        return None
    grouped: dict[float, list[bool]] = {}
    for label, score in zip(labels, scores):
        grouped.setdefault(score, []).append(label)
    true_positive = 0
    selected = 0
    previous_recall = 0.0
    result = 0.0
    for score in sorted(grouped, reverse=True):
        bucket = grouped[score]
        true_positive += sum(bucket)
        selected += len(bucket)
        recall = true_positive / positives
        precision = true_positive / selected
        result += (recall - previous_recall) * precision
        previous_recall = recall
    return result


def threshold_frontier(
    *, labels: Sequence[bool], scores: Sequence[float], costs: Sequence[int], score_name: str,
) -> list[dict[str, Any]]:
    """Describe all score thresholds without selecting an online operating point."""
    if not labels or len(labels) != len(scores) or len(labels) != len(costs):
        raise ValueError("labels, scores, and costs must be equal-length and non-empty")
    if any(cost < 0 for cost in costs):
        raise ValueError("costs must be non-negative")
    thresholds: list[float] = [math.inf, *sorted(set(scores), reverse=True), -math.inf]
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        selected = [index for index, score in enumerate(scores) if score >= threshold]
        recovered = sum(labels[index] for index in selected)
        added_steps = sum(costs[index] for index in selected)
        rows.append({
            "score_name": score_name,
            "threshold": threshold,
            "retry_requests": len(selected),
            "retry_request_rate": len(selected) / len(labels),
            "recovered_cases": recovered,
            "recovery_rate_over_population": recovered / len(labels),
            "unnecessary_retries": len(selected) - recovered,
            "missed_recoveries": sum(labels) - recovered,
            "additional_environment_steps": added_steps,
            "recoveries_per_100_additional_steps": (
                100.0 * recovered / added_steps if added_steps else None
            ),
        })
    unique: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for row in rows:
        key = (row["retry_requests"], row["recovered_cases"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def finite(values: Iterable[float]) -> list[float]:
    result = [float(value) for value in values]
    if not result or not all(math.isfinite(value) for value in result):
        raise ValueError("scores must be non-empty finite values")
    return result
