"""Chronological raw and accepted-only episodic retrieval for ProbeMem Phase C."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from src.probemem.models import InterventionSkill, MemorySnapshot
from src.reasoning.evidence import validate_no_oracle_evidence


EPISODIC_MEMORY_SCHEMA_VERSION = 1
SIGNATURE_FEATURES = (
    "progress_to_goal",
    "final_object_goal_distance",
    "temporal_uncertainty",
    "phase_inconsistency",
    "estimated_drift_x",
    "estimated_drift_y",
    "normalized_residual_norm",
)


@dataclass(frozen=True)
class EvidenceSignature:
    schema_version: int
    evidence_id: str
    episode_id: int
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.schema_version != EPISODIC_MEMORY_SCHEMA_VERSION:
            raise ValueError("unsupported episodic signature schema version")
        if not self.evidence_id.strip() or self.episode_id <= 0:
            raise ValueError("evidence signature requires causal provenance")
        if len(self.values) != len(SIGNATURE_FEATURES) or not np.all(np.isfinite(self.values)):
            raise ValueError("evidence signature requires all finite registered features")

    @classmethod
    def from_structured_evidence(cls, state: Mapping[str, Any]) -> "EvidenceSignature":
        validate_no_oracle_evidence(state)
        task = state.get("task_state")
        temporal = state.get("temporal_response")
        phase = state.get("phase_response")
        if not all(isinstance(item, Mapping) for item in (task, temporal, phase)):
            raise ValueError("signature requires task, temporal, and phase evidence")
        drift = tuple(float(item) for item in temporal["estimated_drift_xy"])
        residual = np.asarray(temporal["normalized_residual_xy"], dtype=float)
        if len(drift) != 2 or residual.shape != (2,):
            raise ValueError("signature requires two-dimensional drift and residual")
        values = (
            float(task["progress_to_goal"]),
            float(task["final_object_goal_distance"]),
            float(temporal["uncertainty"]),
            float(phase["phase_inconsistency"]),
            drift[0],
            drift[1],
            float(np.linalg.norm(residual)),
        )
        return cls(
            schema_version=EPISODIC_MEMORY_SCHEMA_VERSION,
            evidence_id=str(state["evidence_id"]),
            episode_id=int(state["episode_id"]),
            values=values,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "episode_id": self.episode_id,
            "features": dict(zip(SIGNATURE_FEATURES, self.values)),
        }


@dataclass(frozen=True)
class RecoveryExperience:
    schema_version: int
    record_id: str
    source_episode_id: int
    source_manifest_id: str
    signature: EvidenceSignature
    selected_skill: InterventionSkill
    predicted_verification_status: str
    observed_verification_status: str
    verification_success: bool
    interaction_cost: int

    def __post_init__(self) -> None:
        if self.schema_version != EPISODIC_MEMORY_SCHEMA_VERSION:
            raise ValueError("unsupported recovery experience schema version")
        if not self.record_id.strip() or not self.source_manifest_id.strip():
            raise ValueError("recovery experience requires immutable provenance")
        if self.source_episode_id != self.signature.episode_id:
            raise ValueError("experience and evidence signature episode IDs differ")
        allowed = {"ACCEPTED", "INCONCLUSIVE", "REJECTED"}
        if self.predicted_verification_status not in allowed or self.observed_verification_status not in allowed:
            raise ValueError("experience verification statuses must use registered enums")
        if self.selected_skill is InterventionSkill.ABSTAIN or self.interaction_cost <= 0:
            raise ValueError("experience requires an executed skill and positive cost")
        if self.verification_success != (self.observed_verification_status == "ACCEPTED"):
            raise ValueError("verification success must match ACCEPTED status")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "source_episode_id": self.source_episode_id,
            "source_manifest_id": self.source_manifest_id,
            "signature": self.signature.to_dict(),
            "selected_skill": self.selected_skill.value,
            "predicted_verification_status": self.predicted_verification_status,
            "observed_verification_status": self.observed_verification_status,
            "verification_success": self.verification_success,
            "interaction_cost": self.interaction_cost,
        }


@dataclass(frozen=True)
class VerifiedRecoveryEpisode:
    experience: RecoveryExperience

    def __post_init__(self) -> None:
        if self.experience.observed_verification_status != "ACCEPTED":
            raise ValueError("only freshly ACCEPTED experience may enter verified memory")

    @property
    def episode_id(self) -> int:
        return self.experience.source_episode_id

    @property
    def record_id(self) -> str:
        return self.experience.record_id

    def to_dict(self) -> dict[str, Any]:
        return self.experience.to_dict()


@dataclass(frozen=True)
class RetrievedEpisode:
    record_id: str
    source_episode_id: int
    distance: float
    selected_skill: InterventionSkill
    observed_verification_status: str


def signature_distance(
    left: EvidenceSignature,
    right: EvidenceSignature,
    *,
    scales: Sequence[float],
) -> float:
    scale = np.asarray(scales, dtype=float)
    if scale.shape != (len(SIGNATURE_FEATURES),) or np.any(scale <= 0) or not np.all(np.isfinite(scale)):
        raise ValueError("signature distance requires positive finite registered scales")
    difference = (np.asarray(left.values) - np.asarray(right.values)) / scale
    return float(np.linalg.norm(difference))


class ChronologicalEpisodeMemory:
    """Layer-0 audit plus Layer-1 accepted-only actionable episodes."""

    def __init__(self, *, scales: Sequence[float]) -> None:
        self.scales = tuple(float(item) for item in scales)
        signature_distance(
            EvidenceSignature(1, "validation_left", 1, (0.0,) * len(SIGNATURE_FEATURES)),
            EvidenceSignature(1, "validation_right", 1, (0.0,) * len(SIGNATURE_FEATURES)),
            scales=self.scales,
        )
        self._audit: list[RecoveryExperience] = []
        self._verified: list[VerifiedRecoveryEpisode] = []

    def record(self, experience: RecoveryExperience) -> None:
        if any(item.record_id == experience.record_id for item in self._audit):
            raise ValueError("experience record IDs must be unique")
        if self._audit and experience.source_episode_id <= self._audit[-1].source_episode_id:
            raise ValueError("experience audit must be appended in strict episode order")
        self._audit.append(experience)
        if experience.observed_verification_status == "ACCEPTED":
            self._verified.append(VerifiedRecoveryEpisode(experience))

    def snapshot_before(self, episode_id: int) -> MemorySnapshot:
        if episode_id <= 0:
            raise ValueError("snapshot target episode must be positive")
        eligible = tuple(item for item in self._verified if item.episode_id < episode_id)
        return MemorySnapshot(
            schema_version=1,
            snapshot_id=f"verified_memory_before_episode_{episode_id:04d}",
            created_before_episode_id=episode_id,
            verified_episode_ids=tuple(item.record_id for item in eligible),
        )

    def retrieve_verified(
        self, query: EvidenceSignature, *, current_episode_id: int, limit: int
    ) -> tuple[RetrievedEpisode, ...]:
        if limit <= 0:
            raise ValueError("retrieval limit must be positive")
        eligible = [item for item in self._verified if item.episode_id < current_episode_id]
        ranked = sorted(
            eligible,
            key=lambda item: (
                signature_distance(query, item.experience.signature, scales=self.scales),
                item.episode_id,
                item.record_id,
            ),
        )[:limit]
        return tuple(
            RetrievedEpisode(
                record_id=item.record_id,
                source_episode_id=item.episode_id,
                distance=signature_distance(query, item.experience.signature, scales=self.scales),
                selected_skill=item.experience.selected_skill,
                observed_verification_status=item.experience.observed_verification_status,
            )
            for item in ranked
        )

    def retrieve_raw_development_only(
        self,
        query: EvidenceSignature,
        *,
        current_episode_id: int,
        limit: int,
        development_only: bool,
    ) -> tuple[RetrievedEpisode, ...]:
        if not development_only:
            raise ValueError("raw episodic retrieval is a development-only ablation")
        if limit <= 0:
            raise ValueError("retrieval limit must be positive")
        eligible = [item for item in self._audit if item.source_episode_id < current_episode_id]
        ranked = sorted(
            eligible,
            key=lambda item: (
                signature_distance(query, item.signature, scales=self.scales),
                item.source_episode_id,
                item.record_id,
            ),
        )[:limit]
        return tuple(
            RetrievedEpisode(
                record_id=item.record_id,
                source_episode_id=item.source_episode_id,
                distance=signature_distance(query, item.signature, scales=self.scales),
                selected_skill=item.selected_skill,
                observed_verification_status=item.observed_verification_status,
            )
            for item in ranked
        )

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        _write_jsonl(directory / "interaction_audit.jsonl", [item.to_dict() for item in self._audit])
        _write_jsonl(directory / "verified_episodes.jsonl", [item.to_dict() for item in self._verified])


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)
