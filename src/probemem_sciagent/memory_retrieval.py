"""Bounded chronological retrieval for scientific memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from src.probemem.regime_memory import SIGNATURE_FIELDS
from src.probemem_sciagent.experience_memory import ExperienceMemory
from src.probemem_sciagent.hypothesis_memory import HypothesisMemory
from src.probemem_sciagent.principle_memory import PrincipleMemory
from src.probemem_sciagent.schemas import ExperienceRecord, HypothesisRecord, PrincipleRecord


@dataclass(frozen=True)
class ScientificMemorySnapshot:
    created_before_step: int
    principles: tuple[PrincipleRecord, ...]
    supporting_experiences: tuple[ExperienceRecord, ...]
    counterexample_experiences: tuple[ExperienceRecord, ...]
    hypotheses: tuple[HypothesisRecord, ...]

    @property
    def allowed_principle_ids(self) -> set[str]:
        return {row.principle_id for row in self.principles}

    @property
    def allowed_experience_ids(self) -> set[str]:
        return {row.experience_id for row in (*self.supporting_experiences, *self.counterexample_experiences)}

    @property
    def allowed_hypothesis_ids(self) -> set[str]:
        return {row.hypothesis_id for row in self.hypotheses}

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_before_step": self.created_before_step,
            "principles": [row.to_dict() for row in self.principles],
            "supporting_experiences": [row.to_dict() for row in self.supporting_experiences],
            "counterexample_experiences": [row.to_dict() for row in self.counterexample_experiences],
            "hypotheses": [row.to_dict() for row in self.hypotheses],
        }


def retrieve_scientific_memory(
    *, query_signature: Mapping[str, Any], current_condition_codes: Sequence[str],
    created_before_step: int, experiences: ExperienceMemory,
    hypotheses: HypothesisMemory, principles: PrincipleMemory,
    maximum_principles: int = 3, maximum_support: int = 3,
    maximum_counterexamples: int = 3, maximum_hypotheses: int = 3,
) -> ScientificMemorySnapshot:
    if min(maximum_principles, maximum_support, maximum_counterexamples, maximum_hypotheses) <= 0:
        raise ValueError("retrieval limits must be positive")
    conditions = set(current_condition_codes)
    active = [
        row for row in principles.active_before(created_before_step)
        if set(row.applicability_conditions) <= conditions
    ]
    active.sort(key=lambda row: (-row.estimated_success_rate, -row.support_count, -row.updated_at_step, row.principle_id))
    prior_experiences = list(experiences.snapshot_before(created_before_step))
    ranked = _rank_experiences(query_signature, prior_experiences)
    support = tuple(row for row in ranked if row.verification_status == "ACCEPTED")[:maximum_support]
    counter = tuple(row for row in ranked if row.verification_status == "REJECTED")[:maximum_counterexamples]
    prior_hypotheses = [
        row for row in hypotheses.snapshot_before(created_before_step)
        if row.status not in ("RETIRED",) and set(row.applicability_conditions) & conditions
    ]
    prior_hypotheses.sort(key=lambda row: (
        0 if row.status == "UNDER_TEST" else 1,
        -len(set(row.applicability_conditions) & conditions), -row.updated_at_step, row.hypothesis_id,
    ))
    return ScientificMemorySnapshot(
        created_before_step=created_before_step, principles=tuple(active[:maximum_principles]),
        supporting_experiences=support, counterexample_experiences=counter,
        hypotheses=tuple(prior_hypotheses[:maximum_hypotheses]),
    )


def _signature_vector(signature: Mapping[str, Any]) -> np.ndarray:
    features = signature.get("features", signature)
    if set(features) != set(SIGNATURE_FIELDS):
        raise ValueError("experience retrieval requires the frozen eight-field signature")
    return np.asarray([float(features[name]) for name in SIGNATURE_FIELDS], dtype=float)


def _rank_experiences(
    query: Mapping[str, Any], records: Sequence[ExperienceRecord],
) -> tuple[ExperienceRecord, ...]:
    if not records:
        return ()
    matrix = np.asarray([_signature_vector(row.evidence_signature) for row in records], dtype=float)
    scales = np.std(matrix, axis=0)
    scales[scales <= 1e-12] = 1.0
    query_values = _signature_vector(query)
    distance = np.sqrt(np.mean(np.square((matrix - query_values) / scales), axis=1))
    order = sorted(range(len(records)), key=lambda index: (float(distance[index]), records[index].created_at_step, records[index].experience_id))
    return tuple(records[index] for index in order)
