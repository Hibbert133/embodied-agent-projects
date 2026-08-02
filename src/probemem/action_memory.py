"""Chronological action-outcome records for ProbeMem-ACR development."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping, Sequence

import numpy as np

from src.probemem.intervention_utility import (
    INTERVENTION_APPLICABILITY_FEATURES,
    InterventionApplicabilitySignature,
)
from src.probemem.models import InterventionSkill
from src.reasoning.evidence import validate_no_oracle_evidence


ACTION_OUTCOME_SCHEMA_VERSION = 1
OUTCOME_STATUSES = ("ACCEPTED", "INCONCLUSIVE", "REJECTED")
EXECUTABLE_ACR_SKILLS = (
    InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
    InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY,
)


class ActionRecordOrigin(str, Enum):
    ONLINE_SELECTED = "ONLINE_SELECTED"
    DEVELOPMENT_COUNTERFACTUAL = "DEVELOPMENT_COUNTERFACTUAL"


@dataclass(frozen=True)
class ActionOutcomeRecord:
    schema_version: int
    record_id: str
    source_episode_id: int
    available_from_episode_id: int
    source_run_id: str
    source_manifest_id: str
    source_git_commit: str
    evidence_signature: InterventionApplicabilitySignature
    intervention_skill: InterventionSkill
    predicted_status: str | None
    predicted_progress: float | None
    observed_status: str
    observed_progress: float
    final_object_goal_distance: float
    verification_steps: int
    interaction_cost: int
    probe_used: bool
    record_origin: ActionRecordOrigin
    operational_retrieval_eligible: bool

    def __post_init__(self) -> None:
        if self.schema_version != ACTION_OUTCOME_SCHEMA_VERSION:
            raise ValueError("unsupported action-outcome schema version")
        if not all(
            value.strip()
            for value in (
                self.record_id,
                self.source_run_id,
                self.source_manifest_id,
                self.source_git_commit,
            )
        ):
            raise ValueError("action-outcome record requires complete provenance")
        if self.source_episode_id != self.evidence_signature.episode_id:
            raise ValueError("record and evidence episode provenance differ")
        if self.available_from_episode_id != self.source_episode_id + 1:
            raise ValueError("record may become available only after its source episode")
        if self.intervention_skill not in EXECUTABLE_ACR_SKILLS:
            raise ValueError("action-outcome record requires a registered ACR skill")
        if (self.predicted_status is None) != (self.predicted_progress is None):
            raise ValueError("predicted status and progress must both be present or absent")
        if self.predicted_status is not None and self.predicted_status not in OUTCOME_STATUSES:
            raise ValueError("unsupported predicted outcome status")
        if self.observed_status not in OUTCOME_STATUSES:
            raise ValueError("unsupported observed outcome status")
        numeric = (
            self.observed_progress,
            self.final_object_goal_distance,
        )
        if self.predicted_progress is not None:
            numeric += (self.predicted_progress,)
        if not all(math.isfinite(item) for item in numeric):
            raise ValueError("action-outcome metrics must be finite")
        if self.final_object_goal_distance < 0 or min(
            self.verification_steps, self.interaction_cost
        ) <= 0:
            raise ValueError("action-outcome costs and distance are invalid")
        if (
            self.record_origin is ActionRecordOrigin.DEVELOPMENT_COUNTERFACTUAL
            and self.operational_retrieval_eligible
        ):
            raise ValueError("development counterfactuals cannot enter operational memory")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "source_episode_id": self.source_episode_id,
            "available_from_episode_id": self.available_from_episode_id,
            "source_run_id": self.source_run_id,
            "source_manifest_id": self.source_manifest_id,
            "source_git_commit": self.source_git_commit,
            "evidence_signature": self.evidence_signature.to_dict(),
            "intervention_skill": self.intervention_skill.value,
            "predicted_status": self.predicted_status,
            "predicted_progress": self.predicted_progress,
            "observed_status": self.observed_status,
            "observed_progress": self.observed_progress,
            "final_object_goal_distance": self.final_object_goal_distance,
            "verification_steps": self.verification_steps,
            "interaction_cost": self.interaction_cost,
            "probe_used": self.probe_used,
            "record_origin": self.record_origin.value,
            "operational_retrieval_eligible": self.operational_retrieval_eligible,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ActionOutcomeRecord":
        signature_payload = payload["evidence_signature"]
        features = signature_payload["features"]
        return cls(
            schema_version=int(payload["schema_version"]),
            record_id=str(payload["record_id"]),
            source_episode_id=int(payload["source_episode_id"]),
            available_from_episode_id=int(payload["available_from_episode_id"]),
            source_run_id=str(payload["source_run_id"]),
            source_manifest_id=str(payload["source_manifest_id"]),
            source_git_commit=str(payload["source_git_commit"]),
            evidence_signature=InterventionApplicabilitySignature(
                schema_version=int(signature_payload["schema_version"]),
                evidence_id=str(signature_payload["evidence_id"]),
                episode_id=int(signature_payload["episode_id"]),
                values=tuple(float(features[name]) for name in INTERVENTION_APPLICABILITY_FEATURES),
            ),
            intervention_skill=InterventionSkill(str(payload["intervention_skill"])),
            predicted_status=(
                None if payload["predicted_status"] is None else str(payload["predicted_status"])
            ),
            predicted_progress=(
                None if payload["predicted_progress"] is None else float(payload["predicted_progress"])
            ),
            observed_status=str(payload["observed_status"]),
            observed_progress=float(payload["observed_progress"]),
            final_object_goal_distance=float(payload["final_object_goal_distance"]),
            verification_steps=int(payload["verification_steps"]),
            interaction_cost=int(payload["interaction_cost"]),
            probe_used=bool(payload["probe_used"]),
            record_origin=ActionRecordOrigin(str(payload["record_origin"])),
            operational_retrieval_eligible=bool(payload["operational_retrieval_eligible"]),
        )


@dataclass(frozen=True)
class RetrievedActionOutcome:
    record: ActionOutcomeRecord
    distance: float
    weight: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.distance) or self.distance < 0:
            raise ValueError("retrieval distance must be finite and non-negative")
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("retrieval weight must be finite and positive")


def unique_episode_scales(
    records: Sequence[ActionOutcomeRecord], *, epsilon: float = 1e-12
) -> tuple[float, ...]:
    if epsilon <= 0:
        raise ValueError("standardization epsilon must be positive")
    by_episode: dict[int, tuple[float, ...]] = {}
    for record in records:
        existing = by_episode.setdefault(
            record.source_episode_id, record.evidence_signature.values
        )
        if existing != record.evidence_signature.values:
            raise ValueError("one episode cannot contain different evidence signatures")
    if not by_episode:
        return (1.0,) * len(INTERVENTION_APPLICABILITY_FEATURES)
    matrix = np.asarray(list(by_episode.values()), dtype=float)
    scales = np.std(matrix, axis=0)
    scales[scales <= epsilon] = 1.0
    return tuple(float(item) for item in scales)


def standardized_rms_distance(
    left: InterventionApplicabilitySignature,
    right: InterventionApplicabilitySignature,
    scales: Sequence[float],
) -> float:
    scale = np.asarray(scales, dtype=float)
    if scale.shape != (len(INTERVENTION_APPLICABILITY_FEATURES),):
        raise ValueError("distance scales do not match the frozen feature order")
    if np.any(scale <= 0) or not np.all(np.isfinite(scale)):
        raise ValueError("distance scales must be finite and positive")
    difference = (np.asarray(left.values) - np.asarray(right.values)) / scale
    return float(np.sqrt(np.mean(np.square(difference))))


class ActionOutcomeMemory:
    """Append-only development audit with strict episode-time retrieval."""

    def __init__(self) -> None:
        self._records: list[ActionOutcomeRecord] = []

    @property
    def records(self) -> tuple[ActionOutcomeRecord, ...]:
        return tuple(self._records)

    def record(self, record: ActionOutcomeRecord) -> None:
        if any(item.record_id == record.record_id for item in self._records):
            raise ValueError("action-outcome record IDs must be unique")
        if any(
            item.source_episode_id == record.source_episode_id
            and item.intervention_skill is record.intervention_skill
            for item in self._records
        ):
            raise ValueError("an episode may contain only one record per action")
        if self._records and record.source_episode_id < self._records[-1].source_episode_id:
            raise ValueError("action-outcome memory must be appended in episode order")
        self._records.append(record)

    def prior_records(self, created_before_episode_id: int) -> tuple[ActionOutcomeRecord, ...]:
        if created_before_episode_id <= 0:
            raise ValueError("memory cutoff must be positive")
        return tuple(
            item
            for item in self._records
            if item.available_from_episode_id <= created_before_episode_id
            and item.source_episode_id < created_before_episode_id
        )

    def retrieve_action_outcomes(
        self,
        query: InterventionApplicabilitySignature,
        intervention_skill: InterventionSkill,
        created_before_episode_id: int,
        *,
        outcome_status: str,
        limit: int,
        scales: Sequence[float],
    ) -> tuple[RetrievedActionOutcome, ...]:
        if query.episode_id != created_before_episode_id:
            raise ValueError("query episode must equal the chronological cutoff")
        if intervention_skill not in EXECUTABLE_ACR_SKILLS:
            raise ValueError("retrieval requires a registered ACR skill")
        if outcome_status not in OUTCOME_STATUSES or limit <= 0:
            raise ValueError("retrieval class or limit is invalid")
        eligible = [
            item
            for item in self.prior_records(created_before_episode_id)
            if item.intervention_skill is intervention_skill
            and item.observed_status == outcome_status
        ]
        ranked = sorted(
            eligible,
            key=lambda item: (
                standardized_rms_distance(query, item.evidence_signature, scales),
                item.source_episode_id,
                item.record_id,
            ),
        )[:limit]
        return tuple(
            RetrievedActionOutcome(
                record=item,
                distance=(distance := standardized_rms_distance(query, item.evidence_signature, scales)),
                weight=1.0 / (1.0 + distance),
            )
            for item in ranked
        )
