"""Frozen status-based utility classification for an executed micro-probe."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.probemem.compact_evidence import REGISTERED_SKILLS


STATUS_RANK = {"REJECTED": 0, "INCONCLUSIVE": 1, "ACCEPTED": 2}
PROBE_UTILITY_LABELS = ("HELPFUL_PROBE", "HARMFUL_PROBE", "NO_DECISION_BENEFIT", "NOT_EVALUABLE")


@dataclass(frozen=True)
class ProbeUtilityResult:
    pre_probe_skill: str | None
    post_probe_skill: str | None
    pre_probe_status: str | None
    post_probe_status: str | None
    action_changed: bool
    label: str


def classify_probe_utility(
    *, pre_probe_skill: str | None, post_probe_skill: str | None,
    candidate_statuses: Mapping[str, str],
) -> ProbeUtilityResult:
    if pre_probe_skill not in REGISTERED_SKILLS or post_probe_skill not in REGISTERED_SKILLS:
        return ProbeUtilityResult(pre_probe_skill, post_probe_skill, None, None, False, "NOT_EVALUABLE")
    if set(candidate_statuses) != set(REGISTERED_SKILLS):
        raise ValueError("both registered candidate statuses are required")
    if any(status not in STATUS_RANK for status in candidate_statuses.values()):
        raise ValueError("invalid verification status")
    pre_status = candidate_statuses[pre_probe_skill]
    post_status = candidate_statuses[post_probe_skill]
    changed = pre_probe_skill != post_probe_skill
    if not changed or STATUS_RANK[pre_status] == STATUS_RANK[post_status]:
        label = "NO_DECISION_BENEFIT"
    elif STATUS_RANK[post_status] > STATUS_RANK[pre_status]:
        label = "HELPFUL_PROBE"
    else:
        label = "HARMFUL_PROBE"
    return ProbeUtilityResult(pre_probe_skill, post_probe_skill, pre_status, post_status, changed, label)


def total_online_steps(*, initial_steps: int, mandatory_probe_steps: int, micro_probe_steps: int) -> int:
    values = (initial_steps, mandatory_probe_steps, micro_probe_steps)
    if any(not isinstance(value, int) or value < 0 for value in values):
        raise ValueError("interaction steps must be non-negative integers")
    return sum(values)
