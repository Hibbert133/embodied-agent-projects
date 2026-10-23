"""Research-agent evaluation records independent from task reward."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchMetrics:
    diagnostic_accuracy: float | None
    evidence_environment_steps: int
    hypothesis_confidence: float
    verification_accepted: bool
    rollout_improvement: float
    api_calls: int = 0

    def __post_init__(self) -> None:
        if self.diagnostic_accuracy is not None and not 0.0 <= self.diagnostic_accuracy <= 1.0:
            raise ValueError("diagnostic accuracy must be absent or in [0, 1]")
        if self.evidence_environment_steps < 0 or self.api_calls < 0:
            raise ValueError("interaction and API costs must be non-negative")
        if not 0.0 <= self.hypothesis_confidence <= 1.0:
            raise ValueError("hypothesis confidence must be in [0, 1]")
