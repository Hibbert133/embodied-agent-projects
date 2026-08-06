"""Host validation of Agent decisions and cited memory IDs."""

from __future__ import annotations

from typing import Any, Mapping

from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.schemas import DECISION_STAGES, SciAgentDecision


DECISION_KEYS = {
    "evidence_summary", "candidate_hypotheses", "retrieved_principle_ids",
    "retrieved_experience_ids", "decision_mode", "selected_probe_type",
    "selected_skill", "expected_effect", "uncertainty_reason",
    "predicted_success_probability", "stop_reason", "retrieved_hypothesis_ids",
    "tested_hypothesis_ids", "probe_justification_codes",
}


def validate_decision_mapping(
    value: Mapping[str, Any], *, snapshot: ScientificMemorySnapshot, stage: str,
) -> SciAgentDecision:
    if stage not in DECISION_STAGES or set(value) != DECISION_KEYS:
        raise ValueError("SciAgent decision has unexpected or missing fields")
    decision = SciAgentDecision(
        evidence_summary=str(value["evidence_summary"]),
        candidate_hypotheses=tuple(str(item) for item in value["candidate_hypotheses"]),
        retrieved_principle_ids=tuple(str(item) for item in value["retrieved_principle_ids"]),
        retrieved_experience_ids=tuple(str(item) for item in value["retrieved_experience_ids"]),
        decision_mode=str(value["decision_mode"]),
        selected_probe_type=None if value["selected_probe_type"] is None else str(value["selected_probe_type"]),
        selected_skill=None if value["selected_skill"] is None else str(value["selected_skill"]),
        expected_effect=str(value["expected_effect"]), uncertainty_reason=str(value["uncertainty_reason"]),
        predicted_success_probability=float(value["predicted_success_probability"]),
        stop_reason=None if value["stop_reason"] is None else str(value["stop_reason"]),
        retrieved_hypothesis_ids=tuple(str(item) for item in value["retrieved_hypothesis_ids"]),
        tested_hypothesis_ids=tuple(str(item) for item in value["tested_hypothesis_ids"]),
        probe_justification_codes=tuple(str(item) for item in value["probe_justification_codes"]),
    )
    if not set(decision.retrieved_principle_ids) <= snapshot.allowed_principle_ids:
        raise ValueError("decision cited unknown or future principle IDs")
    if not set(decision.retrieved_experience_ids) <= snapshot.allowed_experience_ids:
        raise ValueError("decision cited unknown or future experience IDs")
    if not set(decision.retrieved_hypothesis_ids) <= snapshot.allowed_hypothesis_ids:
        raise ValueError("decision cited unknown or future hypothesis IDs")
    hypothesis_status = {row.hypothesis_id: row.status for row in snapshot.hypotheses}
    if any(hypothesis_status[item] in ("CONTRADICTED", "RETIRED") for item in decision.tested_hypothesis_ids):
        raise ValueError("contradicted or retired hypotheses cannot be tested")
    if stage == "POST_PROBE" and decision.decision_mode == "RUN_MICRO_PROBE":
        raise ValueError("post-probe decisions cannot recurse")
    return decision
