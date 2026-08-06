"""Registered micro-probes and deterministic budget admission."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from src.probemem_sciagent.schemas import PROBE_TYPES, SciAgentDecision
from src.rollout import run_episode


PROBE_MAXIMUM_STEPS = {
    "COMPENSATION_RESPONSE_PROBE": 64,
    "RETRY_REPEATABILITY_PROBE": 192,
}


@dataclass(frozen=True)
class ProbeBudget:
    remaining_probe_steps: int
    reserved_verification_steps: int = 500

    def authorize(self, probe_type: str) -> int:
        if probe_type not in PROBE_MAXIMUM_STEPS:
            raise ValueError("unregistered probe")
        required = PROBE_MAXIMUM_STEPS[probe_type]
        if self.remaining_probe_steps < required:
            raise ValueError("insufficient probe budget")
        return required


def allow_probe(decision: SciAgentDecision, budget: ProbeBudget) -> bool:
    if decision.decision_mode != "RUN_MICRO_PROBE":
        return False
    if decision.selected_probe_type not in PROBE_TYPES or not decision.uncertainty_reason.strip():
        return False
    try:
        budget.authorize(decision.selected_probe_type)
    except ValueError:
        return False
    return True


def run_prefix_records(
    *, env_factory: Callable[[], Any], policy: Any, seed: int, max_steps: int,
    perturbation: Any, perturbation_seed: int,
) -> tuple[dict[str, Any], ...]:
    """Run a reset-matched Agent-visible prefix and return only schema-v2 rows."""
    with tempfile.TemporaryDirectory(prefix="sciagent_probe_") as directory:
        path = Path(directory) / "agent.jsonl"
        env = env_factory()
        try:
            run_episode(
                env, policy, seed=seed, max_steps=max_steps,
                perturbation=perturbation, perturbation_seed=perturbation_seed,
                agent_trajectory_path=path,
            )
        finally:
            env.close()
        return tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
