"""Information-integrity and chronology audit helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from src.reasoning.evidence import validate_no_oracle_evidence


INTEGRITY_KEYS = (
    "chronology_violations", "oracle_leakage", "future_memory_access",
    "counterfactual_memory_writes", "invalid_principle_ids",
    "invalid_skill_execution", "probe_budget_violations",
)


@dataclass
class SciAgentAudit:
    counts: dict[str, int] = field(default_factory=lambda: {key: 0 for key in INTEGRITY_KEYS})
    events: list[dict[str, Any]] = field(default_factory=list)
    _sequence: int = 0

    def event(self, episode_id: str, event: str, **details: Any) -> dict[str, Any]:
        self._sequence += 1
        row = {"sequence": self._sequence, "episode_id": episode_id, "event": event, **details}
        self.events.append(row)
        return row

    def violation(self, key: str, episode_id: str, detail: str) -> None:
        if key not in self.counts:
            raise KeyError(key)
        self.counts[key] += 1
        self.event(episode_id, "INTEGRITY_VIOLATION", violation_type=key, detail=detail)

    def validate_payload(self, payload: Mapping[str, Any], episode_id: str) -> None:
        try:
            validate_no_oracle_evidence(payload)
        except ValueError as exc:
            self.violation("oracle_leakage", episode_id, str(exc))
            raise

    def assert_clean(self) -> None:
        nonzero = {key: value for key, value in self.counts.items() if value}
        if nonzero:
            raise RuntimeError(f"SciAgent integrity gate failed: {nonzero}")
