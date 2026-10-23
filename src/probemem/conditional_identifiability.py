"""State-stratified ranking metrics for independent retry outcomes."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence
from typing import Any


def conditional_pairwise_auc(
    groups: Sequence[int], labels: Sequence[bool], scores: Sequence[float],
) -> tuple[float | None, int, int]:
    """Return within-group tie-aware AUC, informative groups, and pair count."""
    if not groups or len(groups) != len(labels) or len(groups) != len(scores):
        raise ValueError("groups, labels, and scores must be equal-length and non-empty")
    rows: dict[int, list[tuple[bool, float]]] = defaultdict(list)
    for group, label, score in zip(groups, labels, scores):
        rows[int(group)].append((bool(label), float(score)))
    wins = 0.0
    pairs = 0
    informative = 0
    for values in rows.values():
        positive = [score for label, score in values if label]
        negative = [score for label, score in values if not label]
        if not positive or not negative:
            continue
        informative += 1
        for pos in positive:
            for neg in negative:
                wins += 1.0 if pos > neg else 0.5 if pos == neg else 0.0
                pairs += 1
    return (wins / pairs if pairs else None), informative, pairs


def within_group_permutation_test(
    groups: Sequence[int], labels: Sequence[bool], scores: Sequence[float],
    *, seed: int, resamples: int,
) -> dict[str, Any]:
    """Test greater-than-null conditional AUC by shuffling labels within group."""
    if resamples <= 0:
        raise ValueError("resamples must be positive")
    observed, informative, pairs = conditional_pairwise_auc(groups, labels, scores)
    if observed is None:
        return {"observed_auc": None, "informative_groups": informative, "within_group_pairs": pairs, "p_value_greater": None}
    indices: dict[int, list[int]] = defaultdict(list)
    for index, group in enumerate(groups):
        indices[int(group)].append(index)
    rng = random.Random(seed)
    exceed = 0
    for _ in range(resamples):
        permuted = list(labels)
        for group_indices in indices.values():
            values = [permuted[index] for index in group_indices]
            rng.shuffle(values)
            for index, value in zip(group_indices, values):
                permuted[index] = value
        value, _, _ = conditional_pairwise_auc(groups, permuted, scores)
        if value is not None and value >= observed:
            exceed += 1
    return {
        "observed_auc": observed,
        "informative_groups": informative,
        "within_group_pairs": pairs,
        "p_value_greater": (exceed + 1) / (resamples + 1),
    }
