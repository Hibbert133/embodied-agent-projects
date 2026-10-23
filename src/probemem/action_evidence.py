"""Build action-separated evidence packs from chronological outcome memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.probemem.action_memory import (
    EXECUTABLE_ACR_SKILLS,
    OUTCOME_STATUSES,
    ActionOutcomeMemory,
    RetrievedActionOutcome,
    unique_episode_scales,
)
from src.probemem.intervention_utility import InterventionApplicabilitySignature
from src.probemem.models import InterventionSkill
from src.reasoning.evidence import validate_no_oracle_evidence


@dataclass(frozen=True)
class ActionClassEvidence:
    outcome_status: str
    records: tuple[RetrievedActionOutcome, ...]
    weighted_evidence: float

    def __post_init__(self) -> None:
        if self.outcome_status not in OUTCOME_STATUSES:
            raise ValueError("unsupported action evidence outcome class")
        expected = sum(item.weight for item in self.records)
        if abs(expected - self.weighted_evidence) > 1e-12:
            raise ValueError("weighted class evidence does not match retrieved records")

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_status": self.outcome_status,
            "record_ids": [item.record.record_id for item in self.records],
            "source_episode_ids": [item.record.source_episode_id for item in self.records],
            "distances": [item.distance for item in self.records],
            "weights": [item.weight for item in self.records],
            "weighted_evidence": self.weighted_evidence,
        }


@dataclass(frozen=True)
class CandidateActionEvidence:
    intervention_skill: InterventionSkill
    history_count: int
    classes: Mapping[str, ActionClassEvidence]

    def __post_init__(self) -> None:
        if self.intervention_skill not in EXECUTABLE_ACR_SKILLS:
            raise ValueError("candidate evidence requires a registered ACR skill")
        if set(self.classes) != set(OUTCOME_STATUSES) or self.history_count < 0:
            raise ValueError("candidate evidence classes or history count are invalid")

    @property
    def retrieved(self) -> tuple[RetrievedActionOutcome, ...]:
        return tuple(
            item
            for status in OUTCOME_STATUSES
            for item in self.classes[status].records
        )

    def to_dict(self) -> dict[str, Any]:
        denominator = len(self.retrieved)
        return {
            "intervention_skill": self.intervention_skill.value,
            "history_count": self.history_count,
            "retrieved_count": denominator,
            "supporting_records": self.classes["ACCEPTED"].to_dict(),
            "unresolved_records": self.classes["INCONCLUSIVE"].to_dict(),
            "contradicting_records": self.classes["REJECTED"].to_dict(),
            "local_accept_rate": (
                len(self.classes["ACCEPTED"].records) / denominator if denominator else 0.0
            ),
            "contradiction_rate": (
                len(self.classes["REJECTED"].records) / denominator if denominator else 0.0
            ),
        }


@dataclass(frozen=True)
class ActionConditionalEvidencePack:
    schema_version: int
    evidence_id: str
    episode_id: int
    memory_cutoff_episode_id: int
    standardization_episode_ids: tuple[int, ...]
    standardization_scales: tuple[float, ...]
    candidate_actions: Mapping[InterventionSkill, CandidateActionEvidence]

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not self.evidence_id.strip():
            raise ValueError("unsupported action-conditional evidence pack")
        if self.episode_id != self.memory_cutoff_episode_id:
            raise ValueError("evidence pack cutoff must equal the current episode")
        if any(item >= self.episode_id for item in self.standardization_episode_ids):
            raise ValueError("standardization contains current or future episodes")
        if set(self.candidate_actions) != set(EXECUTABLE_ACR_SKILLS):
            raise ValueError("evidence pack must contain both registered actions")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "episode_id": self.episode_id,
            "memory_cutoff_episode_id": self.memory_cutoff_episode_id,
            "standardization_episode_ids": list(self.standardization_episode_ids),
            "standardization_scales": list(self.standardization_scales),
            "candidate_actions": {
                skill.value: self.candidate_actions[skill].to_dict()
                for skill in EXECUTABLE_ACR_SKILLS
            },
        }


def build_action_conditional_evidence_pack(
    memory: ActionOutcomeMemory,
    query: InterventionApplicabilitySignature,
    *,
    neighbors_per_class: int = 5,
    epsilon: float = 1e-12,
) -> ActionConditionalEvidencePack:
    prior = memory.prior_records(query.episode_id)
    scales = unique_episode_scales(prior, epsilon=epsilon)
    episode_ids = tuple(sorted({item.source_episode_id for item in prior}))
    candidates = {}
    for skill in EXECUTABLE_ACR_SKILLS:
        classes = {}
        for status in OUTCOME_STATUSES:
            records = memory.retrieve_action_outcomes(
                query,
                skill,
                query.episode_id,
                outcome_status=status,
                limit=neighbors_per_class,
                scales=scales,
            )
            classes[status] = ActionClassEvidence(
                outcome_status=status,
                records=records,
                weighted_evidence=sum(item.weight for item in records),
            )
        candidates[skill] = CandidateActionEvidence(
            intervention_skill=skill,
            history_count=sum(item.intervention_skill is skill for item in prior),
            classes=classes,
        )
    return ActionConditionalEvidencePack(
        schema_version=1,
        evidence_id=query.evidence_id,
        episode_id=query.episode_id,
        memory_cutoff_episode_id=query.episode_id,
        standardization_episode_ids=episode_ids,
        standardization_scales=scales,
        candidate_actions=candidates,
    )
