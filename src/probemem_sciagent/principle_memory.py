"""Deterministically promoted, scoped principle memory."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from typing import Iterable

from src.probemem_sciagent.principle_promotion import PromotionThresholds, can_promote_hypothesis
from src.probemem_sciagent.schemas import ExperienceRecord, HypothesisRecord, PrincipleRecord


class PrincipleMemory:
    def __init__(self, records: Iterable[PrincipleRecord] = ()) -> None:
        self._current = {record.principle_id: record for record in records}
        self._events: list[dict[str, object]] = []

    @property
    def records(self) -> tuple[PrincipleRecord, ...]:
        return tuple(sorted(self._current.values(), key=lambda row: (row.created_at_step, row.principle_id)))

    @property
    def events(self) -> tuple[dict[str, object], ...]:
        return tuple(self._events)

    def get(self, principle_id: str) -> PrincipleRecord:
        try: return self._current[principle_id]
        except KeyError: raise KeyError(principle_id) from None

    def active_before(self, step: int) -> tuple[PrincipleRecord, ...]:
        return tuple(row for row in self.records if row.status == "ACTIVE" and row.created_at_step < step and row.updated_at_step < step)

    def promote(
        self, hypothesis: HypothesisRecord, *, step: int,
        thresholds: PromotionThresholds = PromotionThresholds(),
    ) -> PrincipleRecord:
        if not can_promote_hypothesis(hypothesis, thresholds):
            raise ValueError("hypothesis does not satisfy deterministic promotion")
        identifier = f"principle_{hashlib.sha256(hypothesis.hypothesis_id.encode()).hexdigest()[:16]}"
        if identifier in self._current:
            raise ValueError("hypothesis has already been promoted")
        sources = tuple(dict.fromkeys((*hypothesis.supporting_experience_ids, *hypothesis.contradicting_experience_ids)))
        record = PrincipleRecord(
            principle_id=identifier, statement=hypothesis.statement,
            applicability_conditions=hypothesis.applicability_conditions,
            recommended_skill=hypothesis.predicted_best_skill,
            support_count=hypothesis.support_count,
            contradiction_count=hypothesis.contradiction_count,
            independent_seed_count=hypothesis.independent_seed_count,
            estimated_success_rate=hypothesis.support_rate,
            scope_description="Applies only when all registered applicability conditions hold.",
            known_failure_modes=(), source_hypothesis_ids=(hypothesis.hypothesis_id,),
            source_experience_ids=sources, confidence_level="DEMO_ENGINEERING",
            status="ACTIVE", created_at_step=step, updated_at_step=step,
            most_recent_verification_status=hypothesis.most_recent_verification_status,
        )
        self._record("PRINCIPLE_PROMOTED", record, step)
        return record

    def observe_cited(self, principle_id: str, *, experience: ExperienceRecord, step: int) -> PrincipleRecord:
        current = self.get(principle_id)
        if current.status != "ACTIVE":
            raise ValueError("only active principles may support a decision")
        if current.recommended_skill != experience.selected_skill:
            raise ValueError("cited principle recommendation differs from executed skill")
        support = current.support_count + int(experience.verification_status == "ACCEPTED")
        contradiction = current.contradiction_count + int(experience.verification_status == "REJECTED")
        rate = support / (support + contradiction) if support + contradiction else 0.0
        status = current.status
        failures = current.known_failure_modes
        if experience.verification_status == "REJECTED":
            status = "RESTRICTED"
            failures = tuple(dict.fromkeys((*failures, f"counterexample:{experience.experience_id}")))
        if contradiction >= 2 or rate < 0.75:
            status = "SUSPENDED"
        sources = tuple(dict.fromkeys((*current.source_experience_ids, experience.experience_id)))
        updated = replace(
            current, support_count=support, contradiction_count=contradiction,
            estimated_success_rate=rate, known_failure_modes=failures,
            source_experience_ids=sources, status=status,
            most_recent_verification_status=experience.verification_status,
            updated_at_step=step,
        )
        self._record("PRINCIPLE_OBSERVED", updated, step)
        return updated

    def _record(self, event: str, record: PrincipleRecord, step: int) -> None:
        previous = self._current.get(record.principle_id)
        if previous is not None and step <= previous.updated_at_step:
            raise ValueError("principle updates must be chronological")
        self._current[record.principle_id] = record
        self._events.append({"event": event, "step": step, "record": record.to_dict()})
