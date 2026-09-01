"""Frozen helpers for the ProbeMem additional-experiments development study.

The module is deliberately host-only and deterministic.  It provides method-
owned chronological memory, leakage-safe pre-acquisition retrieval, and the
registered verifier accounting used by the experiment runner and analyzer.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


STATUS_RANK = {"REJECTED": 0, "INCONCLUSIVE": 1, "ACCEPTED": 2}
REGISTERED_SKILLS = ("BOUNDED_PLANAR_COMPENSATION", "INDEPENDENT_STOCHASTIC_RETRY")


@dataclass(frozen=True)
class ExperimentMemoryRecord:
    record_id: str
    owner_method: str
    source_episode_id: int
    available_from_episode_id: int
    signature: tuple[float, ...]
    selected_skill: str
    observed_status: str
    outcome_completed_sequence: int

    def __post_init__(self) -> None:
        if not self.record_id or not self.owner_method:
            raise ValueError("memory record requires identity and owner")
        if self.available_from_episode_id != self.source_episode_id + 1:
            raise ValueError("memory availability must begin after the source episode")
        if len(self.signature) != 7 or not all(math.isfinite(value) for value in self.signature):
            raise ValueError("memory record requires the frozen seven-field signature")
        if self.selected_skill not in REGISTERED_SKILLS or self.observed_status not in STATUS_RANK:
            raise ValueError("memory record has an invalid skill or outcome")
        if self.outcome_completed_sequence <= 0:
            raise ValueError("memory record requires a positive completion sequence")


@dataclass(frozen=True)
class RetrievedMemoryItem:
    record_id: str
    owner_method: str
    source_episode_id: int
    available_from_episode_id: int
    distance: float
    similarity: float
    selected_skill: str
    observed_status: str
    outcome_completed_sequence: int


class MethodChronologicalMemory:
    """Strict per-method memory with accepted-only actionable retrieval."""

    def __init__(self, owner_method: str, *, scales: Sequence[float]) -> None:
        if not owner_method:
            raise ValueError("memory owner is required")
        self.owner_method = owner_method
        self.scales = tuple(float(value) for value in scales)
        if len(self.scales) != 7 or any(value <= 0 or not math.isfinite(value) for value in self.scales):
            raise ValueError("memory scales must be seven positive finite values")
        self._records: list[ExperimentMemoryRecord] = []

    @property
    def records(self) -> tuple[ExperimentMemoryRecord, ...]:
        return tuple(self._records)

    def append(self, record: ExperimentMemoryRecord) -> None:
        if record.owner_method != self.owner_method:
            raise ValueError("cross-method memory write")
        if self._records and record.source_episode_id <= self._records[-1].source_episode_id:
            raise ValueError("memory writes must be strictly chronological per method")
        if any(item.record_id == record.record_id for item in self._records):
            raise ValueError("duplicate memory record ID")
        self._records.append(record)

    def retrieve(
        self, query: Sequence[float], *, current_episode_id: int,
        decision_sequence: int, limit: int,
    ) -> tuple[RetrievedMemoryItem, ...]:
        values = tuple(float(value) for value in query)
        if len(values) != 7 or not all(math.isfinite(value) for value in values):
            raise ValueError("retrieval query must be the pre-acquisition seven-field signature")
        if current_episode_id <= 0 or decision_sequence <= 0 or limit <= 0:
            raise ValueError("retrieval provenance and limit must be positive")
        eligible = []
        for record in self._records:
            if record.owner_method != self.owner_method:
                raise ValueError("cross-method record present in owner timeline")
            if record.source_episode_id >= current_episode_id:
                continue
            if record.available_from_episode_id > current_episode_id:
                continue
            if record.outcome_completed_sequence >= decision_sequence:
                continue
            if record.observed_status != "ACCEPTED":
                continue
            distance = math.sqrt(sum(
                ((left - right) / scale) ** 2
                for left, right, scale in zip(values, record.signature, self.scales)
            ))
            eligible.append((distance, record.source_episode_id, record.record_id, record))
        eligible.sort(key=lambda item: item[:3])
        return tuple(
            RetrievedMemoryItem(
                record_id=record.record_id,
                owner_method=record.owner_method,
                source_episode_id=record.source_episode_id,
                available_from_episode_id=record.available_from_episode_id,
                distance=distance,
                similarity=1.0 / (1.0 + distance),
                selected_skill=record.selected_skill,
                observed_status=record.observed_status,
                outcome_completed_sequence=record.outcome_completed_sequence,
            )
            for distance, _, _, record in eligible[:limit]
        )


def select_from_retrieval(
    items: Sequence[RetrievedMemoryItem], *, fallback_skill: str,
) -> tuple[str, bool]:
    if fallback_skill not in REGISTERED_SKILLS:
        raise ValueError("fallback must be a registered skill")
    if not items:
        return fallback_skill, False
    weights = {skill: 0.0 for skill in REGISTERED_SKILLS}
    for item in items:
        if item.selected_skill not in weights or item.observed_status != "ACCEPTED":
            raise ValueError("actionable retrieval contains an invalid record")
        weights[item.selected_skill] += item.similarity
    ordered = sorted(weights, key=lambda skill: (-weights[skill], skill))
    if weights[ordered[0]] == weights[ordered[1]]:
        return fallback_skill, False
    return ordered[0], ordered[0] != fallback_skill


@dataclass(frozen=True)
class VerifierResult:
    invoked: bool
    proposal_skill: str
    selected_skill: str
    proposal_probability: float | None
    alternative_probability: float | None
    reason: str


def deterministic_verifier(
    *, proposal_skill: str, prior_records: Iterable[ExperimentMemoryRecord],
    current_episode_id: int, invoked: bool, probability_margin_minimum: float,
    coverage_minimum: int, confidence_minimum: float,
) -> VerifierResult:
    if proposal_skill not in REGISTERED_SKILLS:
        raise ValueError("verifier proposal is not registered")
    alternative = next(skill for skill in REGISTERED_SKILLS if skill != proposal_skill)
    records = [
        record for record in prior_records
        if record.source_episode_id < current_episode_id
        and record.available_from_episode_id <= current_episode_id
    ]
    if not invoked:
        return VerifierResult(False, proposal_skill, proposal_skill, None, None, "NOT_INVOKED")
    probabilities: dict[str, float] = {}
    coverage: dict[str, int] = {}
    for skill in REGISTERED_SKILLS:
        selected = [record for record in records if record.selected_skill == skill]
        accepted = sum(record.observed_status == "ACCEPTED" for record in selected)
        inconclusive = sum(record.observed_status == "INCONCLUSIVE" for record in selected)
        rejected = sum(record.observed_status == "REJECTED" for record in selected)
        alpha = 1.0 + accepted + 0.5 * inconclusive
        beta = 1.0 + rejected + 0.5 * inconclusive
        probabilities[skill] = alpha / (alpha + beta)
        coverage[skill] = len(selected)
    proposal_probability = probabilities[proposal_skill]
    alternative_probability = probabilities[alternative]
    override = (
        coverage[alternative] >= coverage_minimum
        and alternative_probability >= confidence_minimum
        and alternative_probability - proposal_probability >= probability_margin_minimum
    )
    return VerifierResult(
        True, proposal_skill, alternative if override else proposal_skill,
        proposal_probability, alternative_probability,
        "OVERRIDE" if override else "GUARD_RETAINED_PROPOSAL",
    )


def transfer_label(*, no_memory_skill: str, memory_skill: str,
                   no_memory_status: str, memory_status: str,
                   retrieval_count: int) -> str:
    if retrieval_count == 0:
        return "NO_RETRIEVAL"
    if no_memory_skill == memory_skill:
        return "NEUTRAL_TRANSFER"
    delta = STATUS_RANK[memory_status] - STATUS_RANK[no_memory_status]
    return "USEFUL_TRANSFER" if delta > 0 else "HARMFUL_TRANSFER" if delta < 0 else "NEUTRAL_TRANSFER"


def verifier_intervention_outcome(*, proposal_skill: str | None, selected_skill: str | None,
                                  proposal_status: str | None, selected_status: str | None) -> str:
    if proposal_skill not in REGISTERED_SKILLS or selected_skill not in REGISTERED_SKILLS:
        return "INDETERMINATE"
    if proposal_status not in STATUS_RANK or selected_status not in STATUS_RANK:
        return "INDETERMINATE"
    if proposal_skill == selected_skill:
        return "CORRECT_ACCEPTANCE" if proposal_status == "ACCEPTED" else "FALSE_ACCEPTANCE"
    if proposal_status != "ACCEPTED" and selected_status == "ACCEPTED":
        return "CORRECT_REJECTION"
    if proposal_status == "ACCEPTED" and selected_status != "ACCEPTED":
        return "FALSE_REJECTION"
    return "NO_NET_EFFECT"
