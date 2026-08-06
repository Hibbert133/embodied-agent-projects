"""Host-owned application of post-verification knowledge proposals."""

from __future__ import annotations

from dataclasses import dataclass

from src.probemem_sciagent.experience_memory import ExperienceMemory
from src.probemem_sciagent.hypothesis_memory import HypothesisMemory
from src.probemem_sciagent.principle_memory import PrincipleMemory
from src.probemem_sciagent.principle_promotion import PromotionThresholds, can_promote_hypothesis
from src.probemem_sciagent.schemas import ExperienceRecord, KnowledgeUpdateProposal, MicroProbeRecord, SciAgentDecision


@dataclass(frozen=True)
class KnowledgeUpdateResult:
    accepted_operations: tuple[str, ...]
    rejected_operations: tuple[str, ...]
    promoted_principle_ids: tuple[str, ...]


def apply_verified_knowledge_update(
    *, decision: SciAgentDecision, experience: ExperienceRecord,
    probe: MicroProbeRecord | None, proposals: tuple[KnowledgeUpdateProposal, ...],
    experiences: ExperienceMemory, hypotheses: HypothesisMemory,
    principles: PrincipleMemory, step: int,
    thresholds: PromotionThresholds = PromotionThresholds(),
) -> KnowledgeUpdateResult:
    accepted: list[str] = []
    rejected: list[str] = []
    for hypothesis_id in decision.tested_hypothesis_ids:
        try:
            hypotheses.observe(
                hypothesis_id, experience=experience, experience_memory=experiences,
                probe=probe, step=step,
            )
            accepted.append(f"OBSERVE:{hypothesis_id}")
        except (KeyError, ValueError) as exc:
            rejected.append(f"OBSERVE:{hypothesis_id}:{exc}")
    for principle_id in decision.retrieved_principle_ids:
        try:
            principle = principles.get(principle_id)
            if principle.recommended_skill == experience.selected_skill:
                principles.observe_cited(principle_id, experience=experience, step=step)
                accepted.append(f"PRINCIPLE_OBSERVE:{principle_id}")
        except (KeyError, ValueError) as exc:
            rejected.append(f"PRINCIPLE_OBSERVE:{principle_id}:{exc}")
    for proposal in proposals:
        if proposal.operation == "CREATE_HYPOTHESIS":
            try:
                record = hypotheses.create_from_induction(
                    statement=proposal.statement or "", applicability_conditions=proposal.applicability_conditions,
                    predicted_best_skill=proposal.predicted_best_skill or "",
                    proposed_probe_type=proposal.proposed_probe_type,
                    induction_experience=experience, step=step,
                )
                accepted.append(f"CREATE:{record.hypothesis_id}")
            except ValueError as exc:
                rejected.append(f"CREATE:{exc}")
        elif proposal.operation.startswith("ADD_HYPOTHESIS") or proposal.operation == "MARK_HYPOTHESIS_TESTED":
            if proposal.target_id in decision.tested_hypothesis_ids:
                accepted.append(f"HOST_OBSERVED:{proposal.target_id}")
            else:
                rejected.append(f"UNTESTED_TARGET:{proposal.target_id}")
        elif proposal.operation in ("RESTRICT_PRINCIPLE", "SUSPEND_PRINCIPLE"):
            rejected.append(f"HOST_STATUS_RULE_ONLY:{proposal.target_id}")
    promoted: list[str] = []
    for hypothesis in hypotheses.records:
        if can_promote_hypothesis(hypothesis, thresholds):
            try:
                promoted.append(principles.promote(hypothesis, step=step, thresholds=thresholds).principle_id)
            except ValueError:
                pass
    return KnowledgeUpdateResult(tuple(accepted), tuple(rejected), tuple(promoted))
