"""Chronology-owning host policy around the online SciAgent."""

from __future__ import annotations

from src.probemem_sciagent.audit import SciAgentAudit
from src.probemem_sciagent.experience_memory import ExperienceMemory, assert_no_counterfactual_write
from src.probemem_sciagent.hypothesis_memory import HypothesisMemory
from src.probemem_sciagent.knowledge_updater import KnowledgeUpdateResult, apply_verified_knowledge_update
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot, retrieve_scientific_memory
from src.probemem_sciagent.principle_memory import PrincipleMemory
from src.probemem_sciagent.schemas import ExperienceRecord, KnowledgeUpdateProposal, MicroProbeRecord, SciAgentDecision


class SciAgentOnlinePolicy:
    def __init__(self) -> None:
        self.experiences = ExperienceMemory()
        self.hypotheses = HypothesisMemory()
        self.principles = PrincipleMemory()
        self.audit = SciAgentAudit()
        self._step = 0
        self._decisions: dict[str, SciAgentDecision] = {}
        self._probes: dict[str, MicroProbeRecord] = {}

    def next_step(self) -> int:
        self._step += 1
        return self._step

    def retrieve(self, *, query_signature: dict, condition_codes: tuple[str, ...]) -> ScientificMemorySnapshot:
        cutoff = self._step + 1
        return retrieve_scientific_memory(
            query_signature=query_signature, current_condition_codes=condition_codes,
            created_before_step=cutoff, experiences=self.experiences,
            hypotheses=self.hypotheses, principles=self.principles,
        )

    def persist_decision(self, *, decision_id: str, episode_id: str, decision: SciAgentDecision) -> int:
        if decision_id in self._decisions:
            raise ValueError("duplicate decision ID")
        step = self.next_step()
        for hypothesis_id in decision.tested_hypothesis_ids:
            self.hypotheses.mark_under_test(hypothesis_id, step=step)
        self._decisions[decision_id] = decision
        self.audit.event(episode_id, "DECISION_PERSISTED", decision_id=decision_id, step=step, decision=decision.to_dict())
        return step

    def persist_probe(self, record: MicroProbeRecord) -> None:
        if record.probe_record_id in self._probes:
            raise ValueError("duplicate probe record ID")
        if record.created_at_step <= 0 or record.created_at_step > self._step + 1:
            raise ValueError("probe chronology is invalid")
        self._step = max(self._step, record.created_at_step)
        self._probes[record.probe_record_id] = record
        self.audit.event(record.episode_id, "MICRO_PROBE_COMPLETED", probe_id=record.probe_record_id, step=record.created_at_step)

    def persist_selected_outcome(
        self, *, decision_id: str, experience: ExperienceRecord,
        selected_skill: str, proposals: tuple[KnowledgeUpdateProposal, ...] = (),
    ) -> KnowledgeUpdateResult:
        if decision_id not in self._decisions:
            raise ValueError("selected outcome requires a persisted decision")
        assert_no_counterfactual_write(experience, selected_skill=selected_skill, selected_experience_id=experience.experience_id)
        decision = self._decisions[decision_id]
        if decision.selected_skill != selected_skill:
            raise ValueError("executed skill differs from persisted Agent decision")
        self.experiences.append_selected(experience)
        self._step = max(self._step, experience.created_at_step)
        probe = None
        if experience.probe_record_ids:
            probe = self._probes[experience.probe_record_ids[-1]]
        result = apply_verified_knowledge_update(
            decision=decision, experience=experience, probe=probe, proposals=proposals,
            experiences=self.experiences, hypotheses=self.hypotheses,
            principles=self.principles, step=self.next_step(),
        )
        self.audit.event(experience.episode_id, "SELECTED_EXPERIENCE_APPENDED", experience_id=experience.experience_id, selected_skill=selected_skill)
        return result
