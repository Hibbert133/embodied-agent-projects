"""Leakage-safe bounded payload builders."""

from __future__ import annotations

from typing import Any, Mapping

from src.probemem.compact_evidence import REGISTERED_SKILLS, SKILL_SEMANTICS
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.schemas import APPLICABILITY_CONDITION_CODES, PROBE_TYPES
from src.reasoning.evidence import validate_no_oracle_evidence


def build_decision_payload(
    *, evidence: Mapping[str, Any], memory: ScientificMemorySnapshot,
    remaining_budget: Mapping[str, int], stage: str,
    first_decision: Mapping[str, Any] | None = None,
    probe_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "stage": stage,
        "current_agent_evidence": dict(evidence),
        "scientific_memory": memory.to_dict(),
        "registered_skill_semantics": {skill: SKILL_SEMANTICS[skill] for skill in REGISTERED_SKILLS},
        "registered_probe_types": list(PROBE_TYPES),
        "registered_applicability_conditions": list(APPLICABILITY_CONDITION_CODES),
        "remaining_budget": dict(remaining_budget),
        "first_decision": None if first_decision is None else dict(first_decision),
        "new_probe_evidence": None if probe_evidence is None else dict(probe_evidence),
        "constraints": {
            "minimum_competing_hypotheses": 2,
            "provisional_skill_required_for_probe": True,
            "continuous_actions_forbidden": True,
            "post_probe_may_not_request_another_probe": True,
        },
        "response_schema": {
            "evidence_summary": "string", "candidate_hypotheses": "list[str] covering both exact skill names",
            "retrieved_principle_ids": "list of supplied IDs", "retrieved_experience_ids": "list of supplied IDs",
            "decision_mode": "ACT_DIRECTLY | RUN_MICRO_PROBE | ABSTAIN",
            "selected_probe_type": "registered probe or null", "selected_skill": "registered skill or null",
            "expected_effect": "string", "uncertainty_reason": "string",
            "predicted_success_probability": "number 0..1", "stop_reason": "string or null",
            "retrieved_hypothesis_ids": "list of supplied IDs", "tested_hypothesis_ids": "subset of retrieved hypothesis IDs",
            "probe_justification_codes": "registered codes; non-empty only for RUN_MICRO_PROBE",
        },
    }
    validate_no_oracle_evidence(payload)
    return payload


def build_knowledge_update_payload(
    *, decision: Mapping[str, Any], selected_experience: Mapping[str, Any],
    known_hypotheses: list[Mapping[str, Any]], known_principles: list[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = {
        "persisted_pre_outcome_decision": dict(decision),
        "selected_action_experience": dict(selected_experience),
        "known_hypotheses": known_hypotheses,
        "known_principles": known_principles,
        "allowed_operations": [
            "CREATE_HYPOTHESIS", "ADD_HYPOTHESIS_SUPPORT",
            "ADD_HYPOTHESIS_CONTRADICTION", "MARK_HYPOTHESIS_TESTED",
            "RESTRICT_PRINCIPLE", "SUSPEND_PRINCIPLE",
        ],
        "constraints": {
            "current_new_hypothesis_is_induction_only": True,
            "promotion_is_host_owned": True,
            "unselected_outcomes_unavailable": True,
        },
        "response_schema": {
            "updates": [{
                "operation": "allowed operation", "target_id": "existing ID or null for create",
                "statement": "string or null", "applicability_conditions": "registered condition list",
                "predicted_best_skill": "registered skill or null", "proposed_probe_type": "registered probe or null",
                "rationale": "string",
            }]
        },
    }
    validate_no_oracle_evidence(payload)
    return payload
