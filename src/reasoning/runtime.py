"""Monotonic timing for attempt-level Agent decisions, excluding rollouts."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from statistics import median
from time import perf_counter_ns
from typing import Any, Callable, Iterator, Sequence


RUNTIME_STAGES = (
    "evidence_state_build_ms",
    "evidence_decision_ms",
    "belief_update_ms",
    "intervention_selection_ms",
    "memory_retrieval_ms",
)


@dataclass(frozen=True)
class AgentDecisionRuntime:
    evidence_state_build_ms: float | None = None
    evidence_decision_ms: float | None = None
    belief_update_ms: float | None = None
    intervention_selection_ms: float | None = None
    memory_retrieval_ms: float | None = None
    total_agent_decision_ms: float = 0.0
    warmup: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionRuntimeRecorder:
    """Record each deterministic decision stage once with a monotonic clock."""

    def __init__(
        self,
        *,
        warmup: bool = False,
        clock_ns: Callable[[], int] = perf_counter_ns,
    ) -> None:
        self._warmup = warmup
        self._clock_ns = clock_ns
        self._durations: dict[str, float] = {}

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        if stage not in RUNTIME_STAGES:
            raise ValueError(f"unknown Agent decision runtime stage: {stage}")
        if stage in self._durations:
            raise ValueError(f"Agent decision runtime stage already recorded: {stage}")
        start = self._clock_ns()
        yield
        elapsed = self._clock_ns() - start
        if elapsed < 0:
            raise ValueError("monotonic Agent clock moved backwards")
        self._durations[stage] = elapsed / 1_000_000.0

    def snapshot(self) -> AgentDecisionRuntime:
        values = {stage: self._durations.get(stage) for stage in RUNTIME_STAGES}
        return AgentDecisionRuntime(
            **values,
            total_agent_decision_ms=sum(self._durations.values()),
            warmup=self._warmup,
        )


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_decision_runtimes(
    samples: Sequence[AgentDecisionRuntime],
) -> dict[str, dict[str, float | int]]:
    """Report median, p90, and max after excluding warm-up samples."""

    official = [sample for sample in samples if not sample.warmup]
    summary: dict[str, dict[str, float | int]] = {}
    for stage in (*RUNTIME_STAGES, "total_agent_decision_ms"):
        values = [
            float(value)
            for sample in official
            for value in [getattr(sample, stage)]
            if value is not None
        ]
        if not values:
            continue
        summary[stage] = {
            "count": len(values),
            "median_ms": median(values),
            "p90_ms": _percentile(values, 0.9),
            "max_ms": max(values),
        }
    return summary
