"""Mechanism hypotheses and append-only revisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any


class HypothesisStatus(str, Enum):
    ACTIVE = "active"
    REJECTED = "rejected"
    VERIFIED = "verified"


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    mechanism: str
    statement: str
    predictions: tuple[str, ...]
    confidence: float
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...] = ()
    revision: int = 1
    status: HypothesisStatus = HypothesisStatus.ACTIVE

    def __post_init__(self) -> None:
        if not all((self.hypothesis_id.strip(), self.mechanism.strip(), self.statement.strip())):
            raise ValueError("hypothesis identity, mechanism, and statement are required")
        if not self.predictions or any(not item.strip() for item in self.predictions):
            raise ValueError("a hypothesis requires falsifiable predictions")
        if not 0.0 <= self.confidence <= 1.0 or self.revision <= 0:
            raise ValueError("confidence must be in [0, 1] and revision must be positive")
        if not self.supporting_evidence_ids:
            raise ValueError("a hypothesis requires supporting evidence provenance")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HypothesisRevision:
    hypothesis_id: str
    from_revision: int
    new_confidence: float
    evidence_summary: str
    added_supporting_evidence_ids: tuple[str, ...] = ()
    added_contradicting_evidence_ids: tuple[str, ...] = ()
    new_status: HypothesisStatus = HypothesisStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip() or self.from_revision <= 0:
            raise ValueError("revision must reference a hypothesis and positive revision")
        if not 0.0 <= self.new_confidence <= 1.0 or not self.evidence_summary.strip():
            raise ValueError("revision requires calibrated confidence and evidence summary")
        if not (self.added_supporting_evidence_ids or self.added_contradicting_evidence_ids):
            raise ValueError("revision must add supporting or contradicting evidence")


def apply_revision(hypothesis: Hypothesis, revision: HypothesisRevision) -> Hypothesis:
    if revision.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError("revision references a different hypothesis")
    if revision.from_revision != hypothesis.revision:
        raise ValueError("revision is stale or skips hypothesis history")
    return replace(
        hypothesis,
        confidence=revision.new_confidence,
        supporting_evidence_ids=hypothesis.supporting_evidence_ids
        + revision.added_supporting_evidence_ids,
        contradicting_evidence_ids=hypothesis.contradicting_evidence_ids
        + revision.added_contradicting_evidence_ids,
        revision=hypothesis.revision + 1,
        status=revision.new_status,
    )
