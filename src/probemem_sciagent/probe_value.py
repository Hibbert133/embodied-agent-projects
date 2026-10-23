"""Deterministic expected-value audit for proposed SciAgent micro-probes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isclose
from typing import Any, Mapping

from src.probemem.compact_evidence import REGISTERED_SKILLS
from src.probemem_sciagent.probe_registry import PROBE_MAXIMUM_STEPS
from src.probemem_sciagent.schemas import SciAgentDecision


TOTAL_CASE_MAX_STEPS = 1256
MINIMUM_BRANCH_PROBABILITY = 0.05
PROBABILITY_TOLERANCE = 1e-6
PROBE_OUTCOMES = {
    "COMPENSATION_RESPONSE_PROBE": (
        "COMPENSATION_RESPONSE_ALIGNED",
        "COMPENSATION_RESPONSE_NOT_ALIGNED",
    ),
    "RETRY_REPEATABILITY_PROBE": (
        "RETRY_PROGRESS_REPEATABLE",
        "RETRY_PROGRESS_NOT_REPEATABLE",
    ),
}
PROBE_VALUE_KEYS = {
    "selected_probe_token", "current_candidates", "outcome_branches",
    "claimed_expected_value_gain",
}
CANDIDATE_KEYS = {"skill_token", "success_probability"}
BRANCH_KEYS = {"outcome_token", "branch_probability", "final_skill_token", "candidates"}


@dataclass(frozen=True)
class ProbeValueAssessment:
    selected_probe_type: str
    current_best_skill: str
    expected_value_gain: float
    normalized_probe_cost: float
    decision_change_probability: float
    admitted: bool
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["rejection_reasons"] = list(self.rejection_reasons)
        return value


def attach_probe_value_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    capability = payload.get("capability_contract")
    if not isinstance(capability, Mapping):
        raise ValueError("probe value contract requires capability tokens")
    value = dict(payload)
    value["probe_value_contract"] = {
        "contract_version": "sciagent_probe_evsi_v1",
        "total_case_max_steps": TOTAL_CASE_MAX_STEPS,
        "minimum_branch_probability": MINIMUM_BRANCH_PROBABILITY,
        "probability_tolerance": PROBABILITY_TOLERANCE,
        "probe_cost_steps": dict(PROBE_MAXIMUM_STEPS),
        "outcome_tokens": {
            "OUTCOME_COMP_ALIGNED": "COMPENSATION_RESPONSE_ALIGNED",
            "OUTCOME_COMP_NOT_ALIGNED": "COMPENSATION_RESPONSE_NOT_ALIGNED",
            "OUTCOME_RETRY_REPEATABLE": "RETRY_PROGRESS_REPEATABLE",
            "OUTCOME_RETRY_NOT_REPEATABLE": "RETRY_PROGRESS_NOT_REPEATABLE",
        },
        "response_schema": {
            "selected_probe_token": "token from capability_contract probe_types",
            "current_candidates": [
                {"skill_token": "skill token", "success_probability": "number 0..1"},
            ],
            "outcome_branches": [{
                "outcome_token": "registered outcome token",
                "branch_probability": "number 0..1",
                "final_skill_token": "skill token",
                "candidates": [
                    {"skill_token": "skill token", "success_probability": "number 0..1"},
                ],
            }],
            "claimed_expected_value_gain": "number",
        },
        "admission_rule": (
            "Host admits only when branches cover both registered outcomes, "
            "at least one branch changes skill, and expected posterior best "
            "success minus current best success is greater than probe_steps/1256."
        ),
    }
    value["probe_value_instruction"] = (
        "When decision_mode is MODE_1 (RUN_MICRO_PROBE), return a top-level "
        "probe_value_certificate using only supplied tokens."
    )
    return value


def validate_probe_value_certificate(
    raw: Mapping[str, Any], *, decision: SciAgentDecision | Mapping[str, Any],
    capability_contract: Mapping[str, Any], probe_value_contract: Mapping[str, Any],
) -> ProbeValueAssessment:
    decision_mode = _decision_field(decision, "decision_mode")
    selected_probe_type = _decision_field(decision, "selected_probe_type")
    selected_skill = _decision_field(decision, "selected_skill")
    if decision_mode != "RUN_MICRO_PROBE":
        raise ValueError("probe value certificate requires a probe decision")
    if set(raw) != PROBE_VALUE_KEYS:
        raise ValueError("probe value certificate has unexpected or missing fields")
    if probe_value_contract.get("contract_version") != "sciagent_probe_evsi_v1":
        raise ValueError("unknown probe value contract")
    namespaces = capability_contract.get("namespaces")
    if not isinstance(namespaces, Mapping):
        raise ValueError("capability namespaces missing")
    skill_tokens = _mapping(namespaces, "skills")
    probe_tokens = _mapping(namespaces, "probe_types")
    outcome_tokens = _mapping(probe_value_contract, "outcome_tokens")
    selected_probe = _token(raw["selected_probe_token"], probe_tokens, "selected probe")
    if selected_probe != selected_probe_type:
        raise ValueError("probe value certificate is not bound to selected probe")

    current = _candidates(raw["current_candidates"], skill_tokens)
    current_best = _argmax_skill(current)
    if current_best != selected_skill:
        raise ValueError("provisional skill is not current candidate argmax")

    branches_raw = raw["outcome_branches"]
    if not isinstance(branches_raw, list) or len(branches_raw) != 2:
        raise ValueError("probe value certificate requires two outcome branches")
    branches = []
    for item in branches_raw:
        if not isinstance(item, Mapping) or set(item) != BRANCH_KEYS:
            raise ValueError("probe value branch schema is invalid")
        outcome = _token(item["outcome_token"], outcome_tokens, "probe outcome")
        probability = _probability(item["branch_probability"], "branch probability")
        if probability < MINIMUM_BRANCH_PROBABILITY:
            raise ValueError("branch probability is below frozen minimum")
        candidates = _candidates(item["candidates"], skill_tokens)
        final_skill = _token(item["final_skill_token"], skill_tokens, "final skill")
        if final_skill != _argmax_skill(candidates):
            raise ValueError("branch final skill is not candidate argmax")
        branches.append((outcome, probability, final_skill, candidates))
    if {row[0] for row in branches} != set(PROBE_OUTCOMES[selected_probe]):
        raise ValueError("probe branches do not cover registered outcomes")
    if not isclose(sum(row[1] for row in branches), 1.0, abs_tol=PROBABILITY_TOLERANCE):
        raise ValueError("branch probabilities do not sum to one")

    current_utility = max(current.values())
    expected_posterior_utility = sum(
        probability * max(candidates.values())
        for _, probability, _, candidates in branches
    )
    gain = expected_posterior_utility - current_utility
    claimed = float(raw["claimed_expected_value_gain"])
    if not isclose(claimed, gain, abs_tol=PROBABILITY_TOLERANCE):
        raise ValueError("claimed expected value gain does not match host computation")
    cost = PROBE_MAXIMUM_STEPS[selected_probe] / TOTAL_CASE_MAX_STEPS
    change_probability = sum(
        probability for _, probability, final_skill, _ in branches
        if final_skill != current_best
    )
    reasons = []
    if change_probability <= 0.0:
        reasons.append("NO_COUNTERFACTUAL_DECISION_CHANGE")
    if gain <= cost:
        reasons.append("EXPECTED_VALUE_NOT_ABOVE_NORMALIZED_COST")
    return ProbeValueAssessment(
        selected_probe_type=selected_probe,
        current_best_skill=current_best,
        expected_value_gain=gain,
        normalized_probe_cost=cost,
        decision_change_probability=change_probability,
        admitted=not reasons,
        rejection_reasons=tuple(reasons),
    )


def _candidates(raw: Any, skill_tokens: Mapping[str, Any]) -> dict[str, float]:
    if not isinstance(raw, list) or len(raw) != len(REGISTERED_SKILLS):
        raise ValueError("candidate list must cover both skills")
    values: dict[str, float] = {}
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != CANDIDATE_KEYS:
            raise ValueError("candidate schema is invalid")
        skill = _token(item["skill_token"], skill_tokens, "candidate skill")
        if skill in values:
            raise ValueError("candidate skill is duplicated")
        values[skill] = _probability(item["success_probability"], "success probability")
    if set(values) != set(REGISTERED_SKILLS):
        raise ValueError("candidate list does not cover registered skills")
    return values


def _argmax_skill(values: Mapping[str, float]) -> str:
    return min(values, key=lambda skill: (-values[skill], REGISTERED_SKILLS.index(skill)))


def _mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"missing token namespace: {key}")
    return value


def _token(value: Any, mapping: Mapping[str, Any], label: str) -> str:
    if not isinstance(value, str) or value not in mapping:
        raise ValueError(f"unknown token for {label}")
    return str(mapping[value])


def _probability(value: Any, label: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} is outside [0, 1]")
    return number


def _decision_field(decision: SciAgentDecision | Mapping[str, Any], name: str) -> Any:
    if isinstance(decision, Mapping):
        if name not in decision:
            raise ValueError(f"decision is missing {name}")
        return decision[name]
    return getattr(decision, name)
