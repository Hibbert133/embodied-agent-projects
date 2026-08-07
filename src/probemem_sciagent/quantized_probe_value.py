"""Quantized, host-derived value certificate for SciAgent micro-probes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from src.probemem.compact_evidence import REGISTERED_SKILLS
from src.probemem_sciagent.probe_registry import PROBE_MAXIMUM_STEPS
from src.probemem_sciagent.probe_value import (
    MINIMUM_BRANCH_PROBABILITY,
    PROBABILITY_TOLERANCE,
    PROBE_OUTCOMES,
    TOTAL_CASE_MAX_STEPS,
)
from src.probemem_sciagent.schemas import SciAgentDecision


QUANTIZED_CONTRACT_VERSION = "sciagent_quantized_probe_evsi_v1"
QUANTIZED_KEYS = {
    "selected_probe_token", "current_selected_probability_token",
    "current_alternative_probability_token", "outcome_branches",
}
QUANTIZED_BRANCH_KEYS = {
    "outcome_token", "branch_probability_token",
    "selected_probability_token", "alternative_probability_token",
}
PROBABILITY_TOKENS = {f"P_{index:02d}": index / 20.0 for index in range(21)}


@dataclass(frozen=True)
class QuantizedProbeValueAssessment:
    selected_probe_type: str | None
    current_best_skill: str | None
    expected_value_gain: float
    normalized_probe_cost: float
    decision_change_probability: float
    admitted: bool
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["rejection_reasons"] = list(self.rejection_reasons)
        return value


def attach_quantized_probe_value_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    capability = payload.get("capability_contract")
    if not isinstance(capability, Mapping):
        raise ValueError("quantized probe value contract requires capability tokens")
    value = dict(payload)
    value["probe_value_contract"] = {
        "contract_version": QUANTIZED_CONTRACT_VERSION,
        "total_case_max_steps": TOTAL_CASE_MAX_STEPS,
        "minimum_branch_probability": MINIMUM_BRANCH_PROBABILITY,
        "probability_tokens": dict(PROBABILITY_TOKENS),
        "probe_cost_steps": dict(PROBE_MAXIMUM_STEPS),
        "outcome_tokens": {
            "OUTCOME_COMP_ALIGNED": "COMPENSATION_RESPONSE_ALIGNED",
            "OUTCOME_COMP_NOT_ALIGNED": "COMPENSATION_RESPONSE_NOT_ALIGNED",
            "OUTCOME_RETRY_REPEATABLE": "RETRY_PROGRESS_REPEATABLE",
            "OUTCOME_RETRY_NOT_REPEATABLE": "RETRY_PROGRESS_NOT_REPEATABLE",
        },
        "response_schema": {
            "when_probe_requested": {
                "selected_probe_token": "token matching decision.selected_probe_type",
                "current_selected_probability_token": "P_00..P_20",
                "current_alternative_probability_token": "P_00..P_20",
                "outcome_branches": [{
                    "outcome_token": "registered outcome token",
                    "branch_probability_token": "P_01..P_20; two branches sum to P_20",
                    "selected_probability_token": "P_00..P_20",
                    "alternative_probability_token": "P_00..P_20",
                }],
            },
            "when_probe_not_requested": None,
        },
        "host_derivation": (
            "The Host derives branch argmax, expected gain, normalized cost, "
            "decision-change probability, and admission. Do not output them."
        ),
    }
    value["probe_value_instruction"] = (
        "Always return top-level probe_value_certificate. For MODE_1 return the "
        "quantized object; for MODE_0 or MODE_2 return null. Use tokens only."
    )
    return value


def validate_quantized_probe_value_certificate(
    raw: Any, *, decision: SciAgentDecision | Mapping[str, Any],
    capability_contract: Mapping[str, Any], probe_value_contract: Mapping[str, Any],
) -> QuantizedProbeValueAssessment:
    mode = _field(decision, "decision_mode")
    if probe_value_contract.get("contract_version") != QUANTIZED_CONTRACT_VERSION:
        raise ValueError("unknown quantized probe value contract")
    if mode != "RUN_MICRO_PROBE":
        if raw is not None:
            raise ValueError("non-probe decision requires null probe value certificate")
        return QuantizedProbeValueAssessment(
            None, None, 0.0, 0.0, 0.0, False, ("AGENT_DID_NOT_REQUEST_PROBE",),
        )
    if not isinstance(raw, Mapping) or set(raw) != QUANTIZED_KEYS:
        raise ValueError("quantized probe value certificate schema is invalid")
    namespaces = capability_contract.get("namespaces")
    if not isinstance(namespaces, Mapping):
        raise ValueError("capability namespaces missing")
    probe_tokens = _mapping(namespaces, "probe_types")
    outcome_tokens = _mapping(probe_value_contract, "outcome_tokens")
    probability_tokens = _mapping(probe_value_contract, "probability_tokens")
    selected_probe = _token(raw["selected_probe_token"], probe_tokens, "selected probe")
    if selected_probe != _field(decision, "selected_probe_type"):
        raise ValueError("quantized certificate is not bound to selected probe")
    selected_skill = _field(decision, "selected_skill")
    if selected_skill not in REGISTERED_SKILLS:
        raise ValueError("probe decision lacks registered provisional skill")
    alternative_skill = next(skill for skill in REGISTERED_SKILLS if skill != selected_skill)
    current_selected = _probability_token(
        raw["current_selected_probability_token"], probability_tokens,
    )
    current_alternative = _probability_token(
        raw["current_alternative_probability_token"], probability_tokens,
    )
    if current_selected < current_alternative:
        raise ValueError("provisional skill probability is below alternative")

    branches_raw = raw["outcome_branches"]
    if not isinstance(branches_raw, list) or len(branches_raw) != 2:
        raise ValueError("quantized certificate requires two outcome branches")
    branches: list[tuple[str, float, float, float]] = []
    for item in branches_raw:
        if not isinstance(item, Mapping) or set(item) != QUANTIZED_BRANCH_KEYS:
            raise ValueError("quantized branch schema is invalid")
        outcome = _token(item["outcome_token"], outcome_tokens, "probe outcome")
        branch_probability = _probability_token(
            item["branch_probability_token"], probability_tokens,
        )
        if branch_probability < MINIMUM_BRANCH_PROBABILITY:
            raise ValueError("branch probability is below frozen minimum")
        selected_probability = _probability_token(
            item["selected_probability_token"], probability_tokens,
        )
        alternative_probability = _probability_token(
            item["alternative_probability_token"], probability_tokens,
        )
        branches.append((outcome, branch_probability, selected_probability, alternative_probability))
    if {row[0] for row in branches} != set(PROBE_OUTCOMES[selected_probe]):
        raise ValueError("quantized branches do not cover registered outcomes")
    if abs(sum(row[1] for row in branches) - 1.0) > PROBABILITY_TOLERANCE:
        raise ValueError("quantized branch probabilities do not sum to one")

    current_utility = current_selected
    posterior_utility = sum(p * max(s, a) for _, p, s, a in branches)
    gain = posterior_utility - current_utility
    change_probability = sum(p for _, p, s, a in branches if a > s)
    cost = PROBE_MAXIMUM_STEPS[selected_probe] / TOTAL_CASE_MAX_STEPS
    reasons = []
    if change_probability <= 0.0:
        reasons.append("NO_COUNTERFACTUAL_DECISION_CHANGE")
    if gain <= cost:
        reasons.append("EXPECTED_VALUE_NOT_ABOVE_NORMALIZED_COST")
    return QuantizedProbeValueAssessment(
        selected_probe, selected_skill, gain, cost, change_probability,
        not reasons, tuple(reasons),
    )


def _field(decision: SciAgentDecision | Mapping[str, Any], name: str) -> Any:
    if isinstance(decision, Mapping):
        if name not in decision:
            raise ValueError(f"decision is missing {name}")
        return decision[name]
    return getattr(decision, name)


def _mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"missing token namespace: {key}")
    return value


def _token(value: Any, mapping: Mapping[str, Any], label: str) -> str:
    if not isinstance(value, str) or value not in mapping:
        raise ValueError(f"unknown token for {label}")
    return str(mapping[value])


def _probability_token(value: Any, mapping: Mapping[str, Any]) -> float:
    if not isinstance(value, str) or value not in mapping:
        raise ValueError("unknown quantized probability token")
    probability = float(mapping[value])
    if probability not in PROBABILITY_TOKENS.values():
        raise ValueError("probability token is outside frozen lattice")
    return probability
