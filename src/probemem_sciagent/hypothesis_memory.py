"""Append-audited hypothesis memory with immutable materialized records."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Iterable

from src.probemem_sciagent.experience_memory import ExperienceMemory
from src.probemem_sciagent.schemas import ExperienceRecord, HypothesisRecord, MicroProbeRecord


class HypothesisMemory:
    def __init__(self, records: Iterable[HypothesisRecord] = ()) -> None:
        self._current = {record.hypothesis_id: record for record in records}
        self._events: list[dict[str, object]] = []

    @property
    def records(self) -> tuple[HypothesisRecord, ...]:
        return tuple(sorted(self._current.values(), key=lambda row: (row.created_at_step, row.hypothesis_id)))

    @property
    def events(self) -> tuple[dict[str, object], ...]:
        return tuple(self._events)

    def get(self, hypothesis_id: str) -> HypothesisRecord:
        try:
            return self._current[hypothesis_id]
        except KeyError:
            raise KeyError(hypothesis_id) from None

    def snapshot_before(self, step: int) -> tuple[HypothesisRecord, ...]:
        return tuple(record for record in self.records if record.created_at_step < step and record.updated_at_step < step)

    def create_from_induction(
        self, *, statement: str, applicability_conditions: tuple[str, ...],
        predicted_best_skill: str, proposed_probe_type: str | None,
        induction_experience: ExperienceRecord, step: int,
    ) -> HypothesisRecord:
        key = "|".join((predicted_best_skill, proposed_probe_type or "NONE", *sorted(applicability_conditions)))
        identifier = f"hyp_{hashlib.sha256(key.encode()).hexdigest()[:16]}"
        if identifier in self._current:
            current = self._current[identifier]
            induction = tuple(dict.fromkeys((*current.induction_experience_ids, induction_experience.experience_id)))
            updated = replace(current, induction_experience_ids=induction, updated_at_step=step)
            self._record("INDUCTION_ADDED", updated, step)
            return updated
        record = HypothesisRecord(
            hypothesis_id=identifier, statement=statement,
            applicability_conditions=applicability_conditions,
            predicted_best_skill=predicted_best_skill,
            induction_experience_ids=(induction_experience.experience_id,),
            proposed_probe_type=proposed_probe_type,
            created_at_step=step, updated_at_step=step,
        )
        self._record("HYPOTHESIS_CREATED", record, step)
        return record

    def mark_under_test(self, hypothesis_id: str, *, step: int) -> HypothesisRecord:
        current = self.get(hypothesis_id)
        if current.status in ("RETIRED", "CONTRADICTED"):
            raise ValueError("retired or contradicted hypothesis cannot be tested")
        updated = replace(current, status="UNDER_TEST", updated_at_step=step)
        self._record("HYPOTHESIS_UNDER_TEST", updated, step)
        return updated

    def observe(
        self, hypothesis_id: str, *, experience: ExperienceRecord,
        experience_memory: ExperienceMemory, probe: MicroProbeRecord | None, step: int,
    ) -> HypothesisRecord:
        current = self.get(hypothesis_id)
        if current.created_at_step >= experience.created_at_step:
            raise ValueError("an outcome cannot validate a hypothesis created after the decision")
        if current.predicted_best_skill != experience.selected_skill:
            raise ValueError("experience skill does not test the hypothesis prediction")
        tested = tuple(dict.fromkeys((*current.tested_experience_ids, experience.experience_id)))
        support = current.supporting_experience_ids
        contradiction = current.contradicting_experience_ids
        if experience.verification_status == "ACCEPTED":
            support = tuple(dict.fromkeys((*support, experience.experience_id)))
        elif experience.verification_status == "REJECTED":
            contradiction = tuple(dict.fromkeys((*contradiction, experience.experience_id)))
        probes = current.targeted_probe_record_ids
        if probe is not None and current.proposed_probe_type == probe.probe_type:
            probes = tuple(dict.fromkeys((*probes, probe.probe_record_id)))
        seeds = {experience_memory.get(item).seed for item in (*support, *contradiction)}
        decisive = len(support) + len(contradiction)
        status = "UNDER_TEST"
        if contradiction and len(contradiction) >= len(support):
            status = "CONTRADICTED"
        elif len(support) >= 2 and len(support) > len(contradiction):
            status = "SUPPORTED"
        updated = replace(
            current, supporting_experience_ids=support,
            contradicting_experience_ids=contradiction, tested_experience_ids=tested,
            targeted_probe_record_ids=probes, verification_count=len(tested),
            support_count=len(support), contradiction_count=len(contradiction),
            independent_seed_count=len(seeds), targeted_verification_count=len(probes),
            most_recent_verification_status=experience.verification_status,
            status=status, updated_at_step=step,
        )
        self._record("HYPOTHESIS_OBSERVED", updated, step)
        return updated

    def _record(self, event: str, record: HypothesisRecord, step: int) -> None:
        previous = self._current.get(record.hypothesis_id)
        if previous is not None and step <= previous.updated_at_step:
            raise ValueError("hypothesis updates must be chronological")
        self._current[record.hypothesis_id] = record
        self._events.append({"event": event, "step": step, "record": record.to_dict()})
