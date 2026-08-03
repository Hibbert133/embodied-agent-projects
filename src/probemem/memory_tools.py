"""Leakage-safe host tools for action-conditioned regime memory."""

from __future__ import annotations

from typing import Any

from src.probemem.models import InterventionSkill
from src.probemem.regime_memory import ACTION_SKILLS, ProbeRegimeSignature, RegimeActionMemory
from src.reasoning.evidence import validate_no_oracle_evidence


def retrieve_action_memory_payload(
    memory: RegimeActionMemory, query: ProbeRegimeSignature, *, created_before_episode_id: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "memory_cutoff_episode_id": created_before_episode_id,
        "candidate_actions": {},
    }
    for skill in ACTION_SKILLS:
        global_summary, recent_summary = memory.retrieve_action_history(
            query, skill, created_before_episode_id=created_before_episode_id,
        )
        payload["candidate_actions"][skill.value] = {
            "global": global_summary.to_dict(),
            "recent": recent_summary.to_dict(),
            "global_recent_acceptance_delta": recent_summary.accepted_probability - global_summary.accepted_probability,
        }
    validate_no_oracle_evidence(payload)
    return payload


def validate_memory_ids(payload: dict[str, Any], memory: RegimeActionMemory, *, created_before_episode_id: int) -> None:
    allowed = {record.record_id for record in memory.prior(created_before_episode_id)}
    cited: set[str] = set()
    for action in payload.get("candidate_actions", {}).values():
        for scope in ("global", "recent"):
            cited.update(str(item) for item in action.get(scope, {}).get("retrieved_record_ids", ()))
    if not cited <= allowed:
        raise ValueError("memory payload cites current, future, or unknown record IDs")
