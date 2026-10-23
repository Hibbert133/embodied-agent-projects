"""Leakage-safe structured evidence derived from schema-v2 Agent transitions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from src.diagnosis import (
    estimate_passive_planar_drift,
    estimate_phase_conditioned_response,
)
from src.reasoning.evidence import (
    EvidencePacket,
    EvidenceSource,
    validate_no_oracle_evidence,
)
from src.task_metrics import compute_push_step_metrics, summarize_push_episode
from src.trajectory import build_agent_view


STRUCTURED_EVIDENCE_SCHEMA_VERSION = 1
MAXIMUM_ATTEMPT_ID_V1 = 2


@dataclass(frozen=True)
class TaskStateEvidence:
    final_object_goal_distance: float
    minimum_gripper_object_distance: float
    object_displacement: float
    progress_to_goal: float


@dataclass(frozen=True)
class TemporalResponseEvidence:
    response_gain_xy: tuple[float, float]
    estimated_drift_xy: tuple[float, float]
    normalized_residual_xy: tuple[float, float]
    action_excitation_xy: tuple[float, float]
    uncertainty: float
    sample_count: int


@dataclass(frozen=True)
class PhaseResponseEvidence:
    phase_inconsistency: float
    eligible_sample_fraction: float
    sample_counts: Mapping[str, int]
    normalized_residual_norms: Mapping[str, float | None]


@dataclass(frozen=True)
class StructuredEvidenceState:
    """Attempt-level state available to deterministic and online reasoning."""

    schema_version: int
    evidence_id: str
    source: EvidenceSource
    episode_id: int
    attempt_id: int
    seed: int
    decision_required: bool
    environment_step_cost: int
    parent_evidence_ids: tuple[str, ...]
    task_state: TaskStateEvidence
    temporal_response: TemporalResponseEvidence
    phase_response: PhaseResponseEvidence
    historical_verified_case_count: int
    missing_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != STRUCTURED_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported StructuredEvidenceState schema version")
        if not self.evidence_id.strip() or self.episode_id <= 0:
            raise ValueError("structured evidence requires identity and episode provenance")
        if not 0 <= self.attempt_id <= MAXIMUM_ATTEMPT_ID_V1:
            raise ValueError("attempt_id is outside the frozen v1 attempt range")
        if self.environment_step_cost <= 0 or self.historical_verified_case_count < 0:
            raise ValueError("evidence cost must be positive and history count non-negative")
        if any(not item.strip() for item in self.parent_evidence_ids):
            raise ValueError("parent evidence IDs must be non-empty")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_evidence_packet(self) -> EvidencePacket:
        payload = self.to_dict()
        for field in (
            "evidence_id",
            "source",
            "episode_id",
            "seed",
            "environment_step_cost",
            "parent_evidence_ids",
        ):
            payload.pop(field)
        return EvidencePacket(
            evidence_id=self.evidence_id,
            source=self.source,
            episode_id=self.episode_id,
            step_count=self.environment_step_cost,
            payload=payload,
            parent_evidence_ids=self.parent_evidence_ids,
        )


def build_structured_evidence_state(
    transitions: Sequence[Mapping[str, Any]],
    *,
    evidence_id: str,
    source: EvidenceSource = EvidenceSource.FAILED_ROLLOUT,
    attempt_id: int = 0,
    parent_evidence_ids: tuple[str, ...] = (),
    historical_verified_case_count: int = 0,
    minimum_phase_samples: int = 8,
    contact_distance: float = 0.08,
    near_goal_distance: float = 0.08,
) -> StructuredEvidenceState:
    """Build v1 state from Agent rows and reject Oracle-enriched input."""

    if not transitions:
        raise ValueError("structured evidence requires at least one transition")
    for transition in transitions:
        validate_no_oracle_evidence(transition)
    rows = [build_agent_view(transition) for transition in transitions]
    episode_ids = {int(row["episode_id"]) for row in rows}
    seeds = {int(row["seed"]) for row in rows}
    if len(episode_ids) != 1 or len(seeds) != 1:
        raise ValueError("structured evidence transitions must share episode and seed")

    temporal = estimate_passive_planar_drift(rows)
    phase = estimate_phase_conditioned_response(
        rows,
        minimum_phase_samples=minimum_phase_samples,
        contact_distance=contact_distance,
        near_goal_distance=near_goal_distance,
    )
    initial_observation = rows[0]["observation"]
    step_metrics = [
        compute_push_step_metrics(row["next_observation"], initial_observation)
        for row in rows
    ]
    episode_metrics = summarize_push_episode(step_metrics)
    phase_estimates = {item.phase: item for item in phase.phase_estimates}
    residuals = {
        name: (
            phase_estimates[name].normalized_residual_norm
            if name in phase_estimates
            else None
        )
        for name in ("approach", "push", "near_goal")
    }
    missing = [
        f"phase_response:{name}"
        for name, residual in residuals.items()
        if residual is None
    ]
    if source is EvidenceSource.FAILED_ROLLOUT:
        missing.append("repeat_consistency")

    return StructuredEvidenceState(
        schema_version=STRUCTURED_EVIDENCE_SCHEMA_VERSION,
        evidence_id=evidence_id,
        source=source,
        episode_id=episode_ids.pop(),
        attempt_id=attempt_id,
        seed=seeds.pop(),
        decision_required=not any(bool(row["success"]) for row in rows),
        environment_step_cost=len(rows),
        parent_evidence_ids=parent_evidence_ids,
        task_state=TaskStateEvidence(
            final_object_goal_distance=episode_metrics.final_object_goal_distance,
            minimum_gripper_object_distance=episode_metrics.minimum_gripper_object_distance,
            object_displacement=episode_metrics.object_displacement,
            progress_to_goal=episode_metrics.progress_to_goal,
        ),
        temporal_response=TemporalResponseEvidence(
            response_gain_xy=temporal.axis_response_gain,
            estimated_drift_xy=temporal.estimated_drift_per_step,
            normalized_residual_xy=temporal.normalized_residual,
            action_excitation_xy=temporal.action_excitation,
            uncertainty=temporal.uncertainty,
            sample_count=temporal.sample_count,
        ),
        phase_response=PhaseResponseEvidence(
            phase_inconsistency=phase.phase_inconsistency,
            eligible_sample_fraction=phase.eligible_sample_fraction,
            sample_counts=dict(phase.phase_sample_counts),
            normalized_residual_norms=residuals,
        ),
        historical_verified_case_count=historical_verified_case_count,
        missing_evidence=tuple(missing),
    )
