from src.probemem.models import InterventionSkill
from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionExperience, RegimeActionMemory
from src.probemem_verifier.candidate_verifier import CandidateMemorySummary


COMP = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


def signature(episode: int = 21, offset: float = 0.0) -> ProbeRegimeSignature:
    return ProbeRegimeSignature(1, f"evidence-{episode}", episode, (offset,) * 8)


def record(episode: int, skill: str, status: str, offset: float = 0.0) -> RegimeActionExperience:
    return RegimeActionExperience(
        1, f"record-{episode}-{skill}", episode, episode + 1,
        signature(episode, offset), InterventionSkill(skill), None, None, status,
        0.1, 0.2, 10, "run", "manifest", "SELECTED_ACTION_ONLY",
    )


def memory(records: list[RegimeActionExperience] | None = None) -> RegimeActionMemory:
    return RegimeActionMemory(records or [])


def summary(
    skill: str, *, accepted: int, inconclusive: int, rejected: int,
    recent_accepted: int | None = None, recent_inconclusive: int | None = None,
    recent_rejected: int | None = None,
) -> CandidateMemorySummary:
    total = accepted + inconclusive + rejected
    ra = accepted if recent_accepted is None else recent_accepted
    ri = inconclusive if recent_inconclusive is None else recent_inconclusive
    rr = rejected if recent_rejected is None else recent_rejected
    ids = tuple(f"{skill}-id-{index}" for index in range(total))
    success = ids[:accepted]
    failure = ids[accepted + inconclusive:]
    return CandidateMemorySummary(
        skill, accepted, inconclusive, rejected, ra, ri, rr,
        0.0 if total == 0 else accepted / total,
        0.0 if ra + ri + rr == 0 else ra / (ra + ri + rr),
        0.0 if total == 0 else 0.8, total, ids, ids,
        success, failure,
    )
