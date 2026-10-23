"""Causally available evidence exchanged by research-agent modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping

from src.trajectory import FORBIDDEN_AGENT_FIELDS


class EvidenceSource(str, Enum):
    FAILED_ROLLOUT = "failed_rollout"
    DIAGNOSTIC_PROBE = "diagnostic_probe"
    VERIFICATION_ROLLOUT = "verification_rollout"


EXTRA_FORBIDDEN_EVIDENCE_FIELDS = frozenset(
    {
        "condition_id",
        "fault_axis",
        "fault_sign",
        "fault_magnitude",
        "injected_bias",
        "injected_bias_axis",
        "injected_bias_sign",
        "injected_bias_magnitude",
        "diagnostic_probe_needed",
        "decision_probe_needed",
        "probe_needed_oracle",
        "mechanism_class_oracle",
        "frozen_threshold",
        "allocation_threshold",
        "threshold",
    }
)

FORBIDDEN_EVIDENCE_FIELDS = FORBIDDEN_AGENT_FIELDS | EXTRA_FORBIDDEN_EVIDENCE_FIELDS


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        return set(value) | set().union(*(_nested_keys(item) for item in value.values()))
    if isinstance(value, (list, tuple)):
        return set().union(*(_nested_keys(item) for item in value))
    return set()


def validate_no_oracle_evidence(value: Any) -> None:
    """Reject direct or nested Oracle-only fields before Agent reasoning."""

    forbidden = FORBIDDEN_EVIDENCE_FIELDS & _nested_keys(value)
    if forbidden:
        raise ValueError(f"evidence contains Oracle-only fields: {sorted(forbidden)}")


@dataclass(frozen=True)
class EvidencePacket:
    """Agent-visible evidence with explicit causal provenance."""

    evidence_id: str
    source: EvidenceSource
    episode_id: int
    step_count: int
    payload: Mapping[str, Any]
    parent_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or self.episode_id <= 0 or self.step_count < 0:
            raise ValueError("evidence requires an ID, positive episode, and non-negative cost")
        validate_no_oracle_evidence(self.payload)
        if any(not item.strip() for item in self.parent_evidence_ids):
            raise ValueError("parent evidence IDs must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
