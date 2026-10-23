"""Chronological selected-action experience memory."""

from __future__ import annotations

from typing import Iterable

from src.probemem_sciagent.schemas import ExperienceRecord


class ExperienceMemory:
    def __init__(self, records: Iterable[ExperienceRecord] = ()) -> None:
        self._records: list[ExperienceRecord] = []
        self._ids: set[str] = set()
        for record in records:
            self.append_selected(record)

    @property
    def records(self) -> tuple[ExperienceRecord, ...]:
        return tuple(self._records)

    def append_selected(self, record: ExperienceRecord) -> None:
        if record.experience_id in self._ids:
            raise ValueError("duplicate experience ID")
        if self._records and record.created_at_step <= self._records[-1].created_at_step:
            raise ValueError("experience writes must be strictly chronological")
        self._records.append(record)
        self._ids.add(record.experience_id)

    def get(self, experience_id: str) -> ExperienceRecord:
        for record in self._records:
            if record.experience_id == experience_id:
                return record
        raise KeyError(experience_id)

    def snapshot_before(self, created_at_step: int) -> tuple[ExperienceRecord, ...]:
        return tuple(record for record in self._records if record.created_at_step < created_at_step)

    def validate_ids_before(self, ids: Iterable[str], created_at_step: int) -> None:
        allowed = {record.experience_id for record in self.snapshot_before(created_at_step)}
        unknown = set(ids) - allowed
        if unknown:
            raise ValueError(f"unknown or future experience IDs: {sorted(unknown)}")


def assert_no_counterfactual_write(
    record: ExperienceRecord, *, selected_skill: str, selected_experience_id: str,
) -> None:
    if record.selected_skill != selected_skill or record.experience_id != selected_experience_id:
        raise ValueError("counterfactual or unselected outcome cannot enter experience memory")
