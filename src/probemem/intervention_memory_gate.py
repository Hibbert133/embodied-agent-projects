"""Coverage-aware, fail-closed retrieval over verified intervention episodes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

import numpy as np

from src.probemem.intervention_memory import VerifiedInterventionEpisode
from src.probemem.intervention_utility import InterventionApplicabilitySignature
from src.probemem.models import InterventionSkill


class MemoryApplicabilityAction(str, Enum):
    USE_VERIFIED_EPISODE = "USE_VERIFIED_EPISODE"
    ABSTAIN = "ABSTAIN"


@dataclass(frozen=True)
class MemoryApplicabilityDecision:
    action: MemoryApplicabilityAction
    reason: str
    selected_skill: InterventionSkill | None
    nearest_distance: float | None
    coverage_radius: float
    retrieved_record_ids: tuple[str, ...]


class CoverageAwareInterventionMemory:
    """Use memory only inside historical coverage with unanimous local support."""

    def __init__(
        self,
        records: Sequence[VerifiedInterventionEpisode],
        *,
        neighbor_count: int = 3,
        coverage_quantile: float = 0.9,
        reserved_verification_steps: int = 500,
        development_protocol_authorized: bool = False,
    ) -> None:
        if not development_protocol_authorized:
            raise ValueError("intervention memory retrieval requires frozen protocol")
        if len(records) <= neighbor_count or neighbor_count <= 0:
            raise ValueError("intervention memory requires more records than neighbors")
        if not 0.0 < coverage_quantile <= 1.0:
            raise ValueError("coverage quantile must be in (0, 1]")
        if reserved_verification_steps <= 0:
            raise ValueError("verification reservation must be positive")
        if len({record.record_id for record in records}) != len(records):
            raise ValueError("verified memory record IDs must be unique")
        self.records = tuple(records)
        self.neighbor_count = neighbor_count
        self.coverage_quantile = coverage_quantile
        self.reserved_verification_steps = reserved_verification_steps
        matrix = np.asarray(
            [record.applicability_signature.values for record in records], dtype=float
        )
        self.means = tuple(float(value) for value in np.mean(matrix, axis=0))
        scales = np.std(matrix, axis=0)
        scales[scales <= 1e-12] = 1.0
        self.scales = tuple(float(value) for value in scales)
        leave_one_out = []
        for index, record in enumerate(records):
            leave_one_out.append(
                min(
                    self._distance(
                        record.applicability_signature,
                        candidate.applicability_signature,
                    )
                    for candidate_index, candidate in enumerate(records)
                    if candidate_index != index
                )
            )
        ordered = sorted(leave_one_out)
        quantile_index = max(0, math.ceil(coverage_quantile * len(ordered)) - 1)
        self.coverage_radius = float(ordered[quantile_index])

    def _distance(
        self,
        left: InterventionApplicabilitySignature,
        right: InterventionApplicabilitySignature,
    ) -> float:
        difference = (
            np.asarray(left.values, dtype=float) - np.asarray(right.values, dtype=float)
        ) / np.asarray(self.scales, dtype=float)
        return float(np.sqrt(np.mean(np.square(difference))))

    def decide(
        self,
        query: InterventionApplicabilitySignature,
        *,
        remaining_budget_steps: int,
    ) -> MemoryApplicabilityDecision:
        if remaining_budget_steps < self.reserved_verification_steps:
            return MemoryApplicabilityDecision(
                MemoryApplicabilityAction.ABSTAIN,
                "INSUFFICIENT_VERIFICATION_BUDGET",
                None,
                None,
                self.coverage_radius,
                (),
            )
        ranked = sorted(
            self.records,
            key=lambda record: (
                self._distance(query, record.applicability_signature),
                record.source_episode_id,
                record.record_id,
            ),
        )[: self.neighbor_count]
        nearest_distance = self._distance(query, ranked[0].applicability_signature)
        record_ids = tuple(record.record_id for record in ranked)
        if nearest_distance > self.coverage_radius:
            return MemoryApplicabilityDecision(
                MemoryApplicabilityAction.ABSTAIN,
                "OUTSIDE_VERIFIED_COVERAGE",
                None,
                nearest_distance,
                self.coverage_radius,
                record_ids,
            )
        skills = {record.selected_skill for record in ranked}
        if len(skills) != 1:
            return MemoryApplicabilityDecision(
                MemoryApplicabilityAction.ABSTAIN,
                "CONFLICTING_VERIFIED_EPISODES",
                None,
                nearest_distance,
                self.coverage_radius,
                record_ids,
            )
        return MemoryApplicabilityDecision(
            MemoryApplicabilityAction.USE_VERIFIED_EPISODE,
            "WITHIN_COVERAGE_WITH_UNANIMOUS_SUPPORT",
            next(iter(skills)),
            nearest_distance,
            self.coverage_radius,
            record_ids,
        )
