"""Action-separated memory summaries and deterministic Bayesian verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from src.probemem.regime_memory import ACTION_SKILLS, ProbeRegimeSignature, RegimeActionMemory
from src.reasoning.evidence import validate_no_oracle_evidence
from src.probemem_verifier.schemas import CandidateVerification


@dataclass(frozen=True)
class CandidateMemorySummary:
    skill: str
    support_count: int
    unresolved_count: int
    contradiction_count: int
    recent_support_count: int
    recent_unresolved_count: int
    recent_contradiction_count: int
    global_accept_rate: float
    recent_accept_rate: float
    coverage: float
    coverage_count: int
    global_record_ids: tuple[str, ...]
    recent_record_ids: tuple[str, ...]
    representative_successes: tuple[str, ...]
    representative_failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for name in (
            "global_record_ids", "recent_record_ids", "representative_successes",
            "representative_failures",
        ):
            value[name] = list(value[name])
        validate_no_oracle_evidence(value)
        return value


@dataclass(frozen=True)
class AdmissionMemorySignals:
    memory_conflict: bool
    memory_coverage: float
    recent_contradiction: bool
    global_preference: str | None
    recent_preference: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_candidate_memory_summaries(
    memory: RegimeActionMemory,
    query: ProbeRegimeSignature,
    *,
    episode_id: int,
    top_k: int = 10,
    recent_count: int = 10,
) -> dict[str, CandidateMemorySummary]:
    """Build separate, prior-only summaries for both registered skills."""

    if query.episode_id != episode_id:
        raise ValueError("query episode and chronological cutoff differ")
    prior_by_id = {record.record_id: record for record in memory.prior(episode_id)}
    result: dict[str, CandidateMemorySummary] = {}
    for skill in ACTION_SKILLS:
        global_summary, recent_summary = memory.retrieve_action_history(
            query, skill, created_before_episode_id=episode_id,
            top_k=top_k, recent_count=recent_count,
        )
        global_ids = tuple(global_summary.retrieved_record_ids)
        recent_ids = tuple(recent_summary.retrieved_record_ids)
        if not set(global_ids + recent_ids) <= set(prior_by_id):
            raise ValueError("memory summary cites current, future, or unknown records")
        successes = tuple(record_id for record_id in global_ids if prior_by_id[record_id].observed_status == "ACCEPTED")
        failures = tuple(record_id for record_id in global_ids if prior_by_id[record_id].observed_status == "REJECTED")
        result[skill.value] = CandidateMemorySummary(
            skill=skill.value,
            support_count=global_summary.support_count,
            unresolved_count=global_summary.unresolved_count,
            contradiction_count=global_summary.contradiction_count,
            recent_support_count=recent_summary.support_count,
            recent_unresolved_count=recent_summary.unresolved_count,
            recent_contradiction_count=recent_summary.contradiction_count,
            global_accept_rate=float(global_summary.accepted_probability),
            recent_accept_rate=float(recent_summary.accepted_probability),
            coverage=float(global_summary.coverage_score),
            coverage_count=len(global_ids),
            global_record_ids=global_ids,
            recent_record_ids=recent_ids,
            representative_successes=successes,
            representative_failures=failures,
        )
    payload = {skill: summary.to_dict() for skill, summary in result.items()}
    validate_no_oracle_evidence(payload)
    return result


def inspect_admission_memory(summaries: Mapping[str, CandidateMemorySummary]) -> AdmissionMemorySignals:
    if set(summaries) != {skill.value for skill in ACTION_SKILLS}:
        raise ValueError("admission requires both registered action summaries")
    ordered = [summaries[skill.value] for skill in ACTION_SKILLS]
    global_preference = _preference(ordered, scope="global")
    recent_preference = _preference(ordered, scope="recent")
    conflict = (
        global_preference is not None and recent_preference is not None
        and global_preference != recent_preference
    )
    # "Recent same-class contradiction" is deliberately conservative: the
    # single nearest action-conditioned record must also belong to the recent
    # window and be rejected. A broad any-overlap rule would admit nearly every
    # case once memory contains a single old rejection.
    recent_similar_rejected = any(
        bool(summary.global_record_ids)
        and summary.global_record_ids[0] in set(summary.recent_record_ids)
        and summary.global_record_ids[0] in set(summary.representative_failures)
        for summary in ordered
    )
    return AdmissionMemorySignals(
        memory_conflict=conflict,
        memory_coverage=min(summary.coverage for summary in ordered),
        recent_contradiction=recent_similar_rejected,
        global_preference=global_preference,
        recent_preference=recent_preference,
    )


class DeterministicBayesianVerifier:
    """Beta(1,1) verifier with registered fractional inconclusive evidence."""

    def __init__(self, *, accepted_status_threshold: float = 0.70,
                 rejected_status_threshold: float = 0.30) -> None:
        if not 0 <= rejected_status_threshold < accepted_status_threshold <= 1:
            raise ValueError("candidate status thresholds are invalid")
        self.accepted_status_threshold = accepted_status_threshold
        self.rejected_status_threshold = rejected_status_threshold

    def verify(self, summary: CandidateMemorySummary) -> CandidateVerification:
        alpha = 1.0 + summary.support_count + 0.5 * summary.unresolved_count
        beta = 1.0 + summary.contradiction_count + 0.5 * summary.unresolved_count
        probability = alpha / (alpha + beta)
        status = (
            "ACCEPTED" if probability >= self.accepted_status_threshold
            else "REJECTED" if probability <= self.rejected_status_threshold
            else "INCONCLUSIVE"
        )
        return CandidateVerification(
            skill=summary.skill,
            predicted_accept_probability=probability,
            predicted_status=status,
            confidence=probability,
            memory_applicable=summary.coverage_count > 0,
            coverage_count=summary.coverage_count,
            supporting_record_ids=summary.representative_successes,
            contradicting_record_ids=summary.representative_failures,
        )

    def verify_both(
        self, summaries: Mapping[str, CandidateMemorySummary],
    ) -> dict[str, CandidateVerification]:
        if set(summaries) != {skill.value for skill in ACTION_SKILLS}:
            raise ValueError("verifier requires both registered actions")
        return {skill: self.verify(summaries[skill]) for skill in summaries}


def validate_glm_candidate_mapping(
    value: Mapping[str, Any], *, allowed_memory_ids: set[str],
) -> dict[str, CandidateVerification]:
    """Validate optional verifier-only GLM output without accepting an action recommendation."""

    required = {skill.value for skill in ACTION_SKILLS}
    if set(value) != required:
        raise ValueError("GLM verifier must evaluate both registered skills")
    result: dict[str, CandidateVerification] = {}
    for skill in required:
        row = value[skill]
        if not isinstance(row, Mapping):
            raise ValueError("GLM candidate verification must be an object")
        expected_fields = {
            "predicted_accept_probability", "predicted_status", "confidence",
            "memory_applicable", "coverage_count", "supporting_record_ids",
            "contradicting_record_ids",
        }
        if set(row) != expected_fields or type(row["memory_applicable"]) is not bool:
            raise ValueError("GLM candidate verification has unexpected fields or flag types")
        candidate = CandidateVerification(
            skill=skill,
            predicted_accept_probability=float(row["predicted_accept_probability"]),
            predicted_status=str(row["predicted_status"]),
            confidence=float(row["confidence"]),
            memory_applicable=row["memory_applicable"],
            coverage_count=int(row["coverage_count"]),
            supporting_record_ids=tuple(str(item) for item in row["supporting_record_ids"]),
            contradicting_record_ids=tuple(str(item) for item in row["contradicting_record_ids"]),
        )
        if not set(candidate.supporting_record_ids + candidate.contradicting_record_ids) <= allowed_memory_ids:
            raise ValueError("GLM verifier cites current, future, or unknown memory")
        result[skill] = candidate
    validate_no_oracle_evidence({skill: candidate.to_dict() for skill, candidate in result.items()})
    return result


def _preference(summaries: list[CandidateMemorySummary], *, scope: str) -> str | None:
    values = [
        _posterior(
            summary.support_count if scope == "global" else summary.recent_support_count,
            summary.unresolved_count if scope == "global" else summary.recent_unresolved_count,
            summary.contradiction_count if scope == "global" else summary.recent_contradiction_count,
        )
        for summary in summaries
    ]
    if values[0] == values[1]:
        return None
    return summaries[0].skill if values[0] > values[1] else summaries[1].skill
def _posterior(accepted: int, inconclusive: int, rejected: int) -> float:
    alpha = 1.0 + accepted + 0.5 * inconclusive
    beta = 1.0 + rejected + 0.5 * inconclusive
    return alpha / (alpha + beta)
