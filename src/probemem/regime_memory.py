"""Chronological, action-conditioned regime memory for ProbeMem-Online."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from src.probemem.models import InterventionSkill
from src.reasoning.evidence import validate_no_oracle_evidence


REGIME_MEMORY_SCHEMA_VERSION = 1
OUTCOMES = ("ACCEPTED", "INCONCLUSIVE", "REJECTED")
ACTION_SKILLS = (
    InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
    InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY,
)
SIGNATURE_FIELDS = (
    "estimated_drift_x",
    "estimated_drift_y",
    "estimated_drift_norm",
    "estimated_bias_std_norm",
    "repeat_response_consistency",
    "phase_inconsistency",
    "progress_to_goal",
    "final_object_goal_distance",
)


@dataclass(frozen=True)
class ProbeRegimeSignature:
    schema_version: int
    evidence_id: str
    episode_id: int
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.schema_version != REGIME_MEMORY_SCHEMA_VERSION or not self.evidence_id.strip() or self.episode_id <= 0:
            raise ValueError("invalid probe regime signature provenance")
        if len(self.values) != len(SIGNATURE_FIELDS) or not all(math.isfinite(value) for value in self.values):
            raise ValueError("probe regime signature requires all finite registered features")
        validate_no_oracle_evidence(self.to_dict())

    @classmethod
    def from_agent_evidence(cls, evidence: Mapping[str, Any]) -> "ProbeRegimeSignature":
        validate_no_oracle_evidence(evidence)
        initial = evidence["initial_evidence"]
        probe = evidence["registered_probe_evidence"]
        consistency = probe["consistency"]
        drift = np.asarray(
            [row["inference"]["estimated_drift_per_step"] for row in probe["repetitions"]],
            dtype=float,
        ).mean(axis=0)
        if drift.shape != (2,):
            raise ValueError("registered probe drift must be planar")
        relative_std = float(consistency["relative_bias_std"])
        repeat_consistency = 1.0 / (1.0 + max(0.0, relative_std))
        phase = initial.get("phase_conditioned_response", {})
        return cls(
            schema_version=REGIME_MEMORY_SCHEMA_VERSION,
            evidence_id=str(evidence["evidence_id"]),
            episode_id=int(evidence["episode_id"]),
            values=(
                float(drift[0]), float(drift[1]), float(np.linalg.norm(drift)),
                float(consistency["estimated_bias_std_norm"]), repeat_consistency,
                float(phase.get("phase_inconsistency", initial.get("phase_inconsistency", 0.0))),
                float(initial["task_state"]["progress_to_goal"]),
                float(initial["task_state"]["final_object_goal_distance"]),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "episode_id": self.episode_id,
            "features": dict(zip(SIGNATURE_FIELDS, self.values)),
        }


@dataclass(frozen=True)
class RegimeActionExperience:
    schema_version: int
    record_id: str
    episode_id: int
    available_from_episode_id: int
    probe_signature: ProbeRegimeSignature
    selected_skill: InterventionSkill
    predicted_status: str | None
    predicted_accept_probability: float | None
    observed_status: str
    observed_progress: float
    observed_final_distance: float
    interaction_cost: int
    source_run_id: str
    source_manifest_id: str
    record_origin: str

    def __post_init__(self) -> None:
        if self.schema_version != REGIME_MEMORY_SCHEMA_VERSION:
            raise ValueError("unsupported regime experience schema")
        if not all(value.strip() for value in (self.record_id, self.source_run_id, self.source_manifest_id, self.record_origin)):
            raise ValueError("regime experience requires full provenance")
        if self.episode_id != self.probe_signature.episode_id or self.available_from_episode_id != self.episode_id + 1:
            raise ValueError("regime experience has invalid chronological provenance")
        if self.selected_skill not in ACTION_SKILLS or self.observed_status not in OUTCOMES:
            raise ValueError("regime experience requires a registered skill and outcome")
        if self.predicted_status is not None and self.predicted_status not in OUTCOMES:
            raise ValueError("unsupported predicted status")
        if self.predicted_accept_probability is not None and not 0.0 <= self.predicted_accept_probability <= 1.0:
            raise ValueError("predicted accept probability must be in [0, 1]")
        if self.predicted_status is None and self.predicted_accept_probability is not None:
            raise ValueError("probability requires a predicted status")
        if not math.isfinite(self.observed_progress) or not math.isfinite(self.observed_final_distance):
            raise ValueError("observed metrics must be finite")
        if self.observed_final_distance < 0 or self.interaction_cost <= 0:
            raise ValueError("observed distance and interaction cost are invalid")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["probe_signature"] = self.probe_signature.to_dict()
        value["selected_skill"] = self.selected_skill.value
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegimeActionExperience":
        required = {
            "schema_version", "record_id", "episode_id", "available_from_episode_id",
            "probe_signature", "selected_skill", "predicted_status",
            "predicted_accept_probability", "observed_status", "observed_progress",
            "observed_final_distance", "interaction_cost", "source_run_id",
            "source_manifest_id", "record_origin",
        }
        if set(value) != required:
            raise ValueError("regime action experience has unexpected or missing fields")
        signature = value["probe_signature"]
        features = signature["features"]
        return cls(
            schema_version=int(value["schema_version"]), record_id=str(value["record_id"]),
            episode_id=int(value["episode_id"]), available_from_episode_id=int(value["available_from_episode_id"]),
            probe_signature=ProbeRegimeSignature(
                int(signature["schema_version"]), str(signature["evidence_id"]), int(signature["episode_id"]),
                tuple(float(features[name]) for name in SIGNATURE_FIELDS),
            ),
            selected_skill=InterventionSkill(str(value["selected_skill"])),
            predicted_status=None if value["predicted_status"] is None else str(value["predicted_status"]),
            predicted_accept_probability=None if value["predicted_accept_probability"] is None else float(value["predicted_accept_probability"]),
            observed_status=str(value["observed_status"]), observed_progress=float(value["observed_progress"]),
            observed_final_distance=float(value["observed_final_distance"]), interaction_cost=int(value["interaction_cost"]),
            source_run_id=str(value["source_run_id"]), source_manifest_id=str(value["source_manifest_id"]),
            record_origin=str(value["record_origin"]),
        )


@dataclass(frozen=True)
class ActionHistorySummary:
    skill: InterventionSkill
    history_count: int
    retrieved_record_ids: tuple[str, ...]
    support_count: int
    unresolved_count: int
    contradiction_count: int
    accepted_probability: float
    mean_progress: float | None
    coverage_score: float
    representative_verified_episode_ids: tuple[int, ...]
    recent_contradiction_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["skill"] = self.skill.value
        return value


class RegimeActionMemory:
    """Append-only selected-action audit with strict chronological retrieval."""

    def __init__(self, records: Sequence[RegimeActionExperience] = ()) -> None:
        self._records: list[RegimeActionExperience] = []
        for record in records:
            self.append_after_verification(record)

    @property
    def records(self) -> tuple[RegimeActionExperience, ...]:
        return tuple(self._records)

    @property
    def verified_examples(self) -> tuple[RegimeActionExperience, ...]:
        return tuple(record for record in self._records if record.observed_status == "ACCEPTED")

    def append_after_verification(self, record: RegimeActionExperience) -> None:
        if any(existing.record_id == record.record_id for existing in self._records):
            raise ValueError("memory record IDs must be unique")
        if any(existing.episode_id == record.episode_id for existing in self._records):
            raise ValueError("operational memory stores only one selected action per episode")
        if self._records and record.episode_id <= self._records[-1].episode_id:
            raise ValueError("memory must be appended in strict episode order")
        self._records.append(record)

    def prior(self, created_before_episode_id: int, skill: InterventionSkill | None = None) -> tuple[RegimeActionExperience, ...]:
        if created_before_episode_id <= 0:
            raise ValueError("chronological cutoff must be positive")
        return tuple(
            record for record in self._records
            if record.available_from_episode_id <= created_before_episode_id
            and record.episode_id < created_before_episode_id
            and (skill is None or record.selected_skill is skill)
        )

    def retrieve_action_history(
        self, query: ProbeRegimeSignature, skill: InterventionSkill,
        *, created_before_episode_id: int, top_k: int = 10, recent_count: int = 10,
    ) -> tuple[ActionHistorySummary, ActionHistorySummary]:
        if query.episode_id != created_before_episode_id or skill not in ACTION_SKILLS:
            raise ValueError("query provenance or action is invalid")
        if top_k <= 0 or recent_count <= 0:
            raise ValueError("history limits must be positive")
        all_prior = self.prior(created_before_episode_id)
        action_prior = self.prior(created_before_episode_id, skill)
        scales = _unique_episode_scales(all_prior)
        ranked = sorted(action_prior, key=lambda record: (_distance(query, record.probe_signature, scales), record.episode_id))[:top_k]
        recent = tuple(action_prior[-recent_count:])
        return (
            _summarize(skill, action_prior, ranked, query, scales),
            _summarize(skill, action_prior, recent, query, scales),
        )


def _unique_episode_scales(records: Sequence[RegimeActionExperience]) -> np.ndarray:
    if not records:
        return np.ones(len(SIGNATURE_FIELDS), dtype=float)
    matrix = np.asarray([record.probe_signature.values for record in records], dtype=float)
    scales = np.std(matrix, axis=0)
    scales[scales <= 1e-12] = 1.0
    return scales


def regime_distance_scales(records: Sequence[RegimeActionExperience]) -> np.ndarray:
    """Expose the frozen v1 scale calculation for verifier successors."""

    return _unique_episode_scales(records).copy()


def _distance(left: ProbeRegimeSignature, right: ProbeRegimeSignature, scales: np.ndarray) -> float:
    difference = (np.asarray(left.values) - np.asarray(right.values)) / scales
    return float(np.sqrt(np.mean(np.square(difference))))


def normalized_regime_distance(
    left: ProbeRegimeSignature, right: ProbeRegimeSignature, scales: np.ndarray,
) -> float:
    """Expose the frozen v1 standardized RMS distance without changing it."""

    return _distance(left, right, np.asarray(scales, dtype=float))


def _summarize(
    skill: InterventionSkill, history: Sequence[RegimeActionExperience], selected: Sequence[RegimeActionExperience],
    query: ProbeRegimeSignature, scales: np.ndarray,
) -> ActionHistorySummary:
    weights = [1.0 / (1.0 + _distance(query, record.probe_signature, scales)) for record in selected]
    total = sum(weights)
    support = sum(record.observed_status == "ACCEPTED" for record in selected)
    unresolved = sum(record.observed_status == "INCONCLUSIVE" for record in selected)
    contradicted = sum(record.observed_status == "REJECTED" for record in selected)
    accepted_probability = 0.0 if total == 0 else sum(weight for weight, record in zip(weights, selected) if record.observed_status == "ACCEPTED") / total
    mean_progress = None if total == 0 else sum(weight * record.observed_progress for weight, record in zip(weights, selected)) / total
    nearest = None if not selected else min(_distance(query, record.probe_signature, scales) for record in selected)
    return ActionHistorySummary(
        skill=skill, history_count=len(history), retrieved_record_ids=tuple(record.record_id for record in selected),
        support_count=support, unresolved_count=unresolved, contradiction_count=contradicted,
        accepted_probability=accepted_probability, mean_progress=mean_progress,
        coverage_score=0.0 if nearest is None else 1.0 / (1.0 + nearest),
        representative_verified_episode_ids=tuple(record.episode_id for record in selected if record.observed_status == "ACCEPTED"),
        recent_contradiction_ids=tuple(record.record_id for record in selected if record.observed_status == "REJECTED"),
    )
