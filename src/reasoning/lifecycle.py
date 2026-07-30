"""Strict state machine for one post-failure research cycle."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class ResearchCycleState(str, Enum):
    ROLLOUT_FAILED = "rollout_failed"
    UNCERTAINTY_ASSESSED = "uncertainty_assessed"
    PROBE_REQUESTED = "probe_requested"
    PROBE_EVIDENCE_COLLECTED = "probe_evidence_collected"
    HYPOTHESIS_UPDATED = "hypothesis_updated"
    INTERVENTION_PROPOSED = "intervention_proposed"
    VERIFICATION_EXECUTED = "verification_executed"
    VERIFICATION_ACCEPTED = "verification_accepted"
    VERIFICATION_REJECTED = "verification_rejected"
    VERIFICATION_INCONCLUSIVE = "verification_inconclusive"
    MEMORY_COMMITTED = "memory_committed"
    ABSTAINED = "abstained"


class ResearchCycleEvent(str, Enum):
    ASSESS_UNCERTAINTY = "assess_uncertainty"
    REQUEST_PROBE = "request_probe"
    COMPLETE_PROBE = "complete_probe"
    UPDATE_HYPOTHESIS = "update_hypothesis"
    PROPOSE_INTERVENTION = "propose_intervention"
    EXECUTE_VERIFICATION = "execute_verification"
    ACCEPT_VERIFICATION = "accept_verification"
    REJECT_VERIFICATION = "reject_verification"
    MARK_INCONCLUSIVE = "mark_inconclusive"
    REASSESS_UNCERTAINTY = "reassess_uncertainty"
    COMMIT_MEMORY = "commit_memory"
    ABSTAIN = "abstain"


TRANSITIONS = {
    (ResearchCycleState.ROLLOUT_FAILED, ResearchCycleEvent.ASSESS_UNCERTAINTY): ResearchCycleState.UNCERTAINTY_ASSESSED,
    (ResearchCycleState.UNCERTAINTY_ASSESSED, ResearchCycleEvent.REQUEST_PROBE): ResearchCycleState.PROBE_REQUESTED,
    (ResearchCycleState.UNCERTAINTY_ASSESSED, ResearchCycleEvent.UPDATE_HYPOTHESIS): ResearchCycleState.HYPOTHESIS_UPDATED,
    (ResearchCycleState.UNCERTAINTY_ASSESSED, ResearchCycleEvent.ABSTAIN): ResearchCycleState.ABSTAINED,
    (ResearchCycleState.PROBE_REQUESTED, ResearchCycleEvent.COMPLETE_PROBE): ResearchCycleState.PROBE_EVIDENCE_COLLECTED,
    (ResearchCycleState.PROBE_EVIDENCE_COLLECTED, ResearchCycleEvent.UPDATE_HYPOTHESIS): ResearchCycleState.HYPOTHESIS_UPDATED,
    (ResearchCycleState.HYPOTHESIS_UPDATED, ResearchCycleEvent.PROPOSE_INTERVENTION): ResearchCycleState.INTERVENTION_PROPOSED,
    (ResearchCycleState.INTERVENTION_PROPOSED, ResearchCycleEvent.EXECUTE_VERIFICATION): ResearchCycleState.VERIFICATION_EXECUTED,
    (ResearchCycleState.VERIFICATION_EXECUTED, ResearchCycleEvent.ACCEPT_VERIFICATION): ResearchCycleState.VERIFICATION_ACCEPTED,
    (ResearchCycleState.VERIFICATION_EXECUTED, ResearchCycleEvent.REJECT_VERIFICATION): ResearchCycleState.VERIFICATION_REJECTED,
    (ResearchCycleState.VERIFICATION_EXECUTED, ResearchCycleEvent.MARK_INCONCLUSIVE): ResearchCycleState.VERIFICATION_INCONCLUSIVE,
    (ResearchCycleState.VERIFICATION_ACCEPTED, ResearchCycleEvent.COMMIT_MEMORY): ResearchCycleState.MEMORY_COMMITTED,
    (ResearchCycleState.VERIFICATION_REJECTED, ResearchCycleEvent.REASSESS_UNCERTAINTY): ResearchCycleState.UNCERTAINTY_ASSESSED,
    (ResearchCycleState.VERIFICATION_INCONCLUSIVE, ResearchCycleEvent.REASSESS_UNCERTAINTY): ResearchCycleState.UNCERTAINTY_ASSESSED,
}


@dataclass(frozen=True)
class ResearchCycle:
    cycle_id: str
    state: ResearchCycleState = ResearchCycleState.ROLLOUT_FAILED
    history: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.cycle_id.strip():
            raise ValueError("cycle_id must be non-empty")

    def transition(self, event: ResearchCycleEvent, reference_id: str) -> "ResearchCycle":
        if not reference_id.strip():
            raise ValueError("every transition requires a provenance reference")
        target = TRANSITIONS.get((self.state, event))
        if target is None:
            raise ValueError(f"invalid research-cycle transition: {self.state.value} + {event.value}")
        return replace(
            self,
            state=target,
            history=self.history + ((event.value, reference_id),),
        )
