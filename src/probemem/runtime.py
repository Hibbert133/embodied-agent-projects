"""Attempt-level state machine and hard interaction-budget invariants."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class ProbeMemState(str, Enum):
    INITIAL_ROLLOUT = "INITIAL_ROLLOUT"
    BUILD_EVIDENCE = "BUILD_EVIDENCE"
    RETRIEVE_MEMORY = "RETRIEVE_EMPTY_V2_MEMORY_SNAPSHOT"
    LLM_DECISION = "LLM_DECISION"
    OPTIONAL_PROBE = "OPTIONAL_PROBE"
    SELECT_INTERVENTION = "SELECT_BOUNDED_SKILL"
    FRESH_VERIFICATION = "FRESH_VERIFICATION"
    AUDIT_WRITE = "IMMUTABLE_AUDIT_WRITE"
    COMPLETE = "COMPLETE"


_ALLOWED_TRANSITIONS = {
    ProbeMemState.INITIAL_ROLLOUT: {ProbeMemState.BUILD_EVIDENCE},
    ProbeMemState.BUILD_EVIDENCE: {ProbeMemState.RETRIEVE_MEMORY},
    ProbeMemState.RETRIEVE_MEMORY: {ProbeMemState.LLM_DECISION},
    ProbeMemState.LLM_DECISION: {
        ProbeMemState.OPTIONAL_PROBE,
        ProbeMemState.SELECT_INTERVENTION,
        ProbeMemState.AUDIT_WRITE,
    },
    ProbeMemState.OPTIONAL_PROBE: {ProbeMemState.LLM_DECISION},
    ProbeMemState.SELECT_INTERVENTION: {
        ProbeMemState.FRESH_VERIFICATION,
        ProbeMemState.AUDIT_WRITE,
    },
    ProbeMemState.FRESH_VERIFICATION: {ProbeMemState.AUDIT_WRITE},
    ProbeMemState.AUDIT_WRITE: {ProbeMemState.COMPLETE},
    ProbeMemState.COMPLETE: set(),
}


@dataclass(frozen=True)
class CaseBudget:
    total_steps: int = 1064
    initial_max_steps: int = 500
    probe_max_steps: int = 64
    verification_max_steps: int = 500
    consumed_initial_steps: int = 0
    consumed_probe_steps: int = 0
    consumed_verification_steps: int = 0

    def __post_init__(self) -> None:
        if min(self.total_steps, self.initial_max_steps, self.probe_max_steps, self.verification_max_steps) <= 0:
            raise ValueError("all ProbeMem budgets must be positive")
        if self.total_steps != self.initial_max_steps + self.probe_max_steps + self.verification_max_steps:
            raise ValueError("total budget must reserve initial, probe, and verification maxima")
        if not 0 <= self.consumed_initial_steps <= self.initial_max_steps:
            raise ValueError("initial rollout exceeded its budget")
        if not 0 <= self.consumed_probe_steps <= self.probe_max_steps:
            raise ValueError("diagnostic probe exceeded its budget")
        if not 0 <= self.consumed_verification_steps <= self.verification_max_steps:
            raise ValueError("fresh verification exceeded its budget")
        if self.consumed_steps > self.total_steps:
            raise ValueError("total case interaction budget exceeded")

    @property
    def consumed_steps(self) -> int:
        return self.consumed_initial_steps + self.consumed_probe_steps + self.consumed_verification_steps

    @property
    def remaining_steps(self) -> int:
        return self.total_steps - self.consumed_steps

    def can_request_probe(self) -> bool:
        return (
            self.consumed_probe_steps == 0
            and self.remaining_steps >= self.probe_max_steps + self.verification_max_steps
        )

    def with_initial(self, steps: int) -> "CaseBudget":
        return replace(self, consumed_initial_steps=steps)

    def with_probe(self, steps: int) -> "CaseBudget":
        if self.consumed_probe_steps:
            raise ValueError("first-version protocol permits at most one diagnostic probe")
        if not self.can_request_probe():
            raise ValueError("probe would violate reserved fresh-verification budget")
        return replace(self, consumed_probe_steps=steps)

    def with_verification(self, steps: int) -> "CaseBudget":
        if self.consumed_verification_steps:
            raise ValueError("first-version protocol permits at most one fresh verification")
        if self.remaining_steps < steps:
            raise ValueError("fresh verification would exceed remaining case budget")
        return replace(self, consumed_verification_steps=steps)


@dataclass
class ProbeMemStateMachine:
    state: ProbeMemState = ProbeMemState.INITIAL_ROLLOUT
    transition_count: int = 0

    def advance(self, target: ProbeMemState) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"invalid ProbeMem transition: {self.state.value} -> {target.value}")
        self.state = target
        self.transition_count += 1
