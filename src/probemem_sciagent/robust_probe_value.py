"""Ambiguity-aware robust lower-bound value rule for quantized probe claims."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from src.probemem_sciagent.probe_registry import PROBE_MAXIMUM_STEPS
from src.probemem_sciagent.probe_value import TOTAL_CASE_MAX_STEPS
from src.probemem_sciagent.quantized_probe_value import (
    PROBABILITY_TOKENS,
    QUANTIZED_CONTRACT_VERSION,
    attach_quantized_probe_value_contract,
    validate_quantized_probe_value_certificate,
)
from src.probemem_sciagent.schemas import SciAgentDecision


ROBUST_CONTRACT_VERSION = "sciagent_robust_quantized_probe_evsi_v1"
MAXIMUM_CURRENT_PROBABILITY_GAP = 0.10
QUANTIZATION_HALF_WIDTH = 0.025


@dataclass(frozen=True)
class RobustProbeValueAssessment:
    selected_probe_type: str | None
    current_best_skill: str | None
    current_probability_gap: float
    robust_expected_value_gain: float
    normalized_probe_cost: float
    decision_change_probability: float
    outcome_discriminative: bool
    admitted: bool
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["rejection_reasons"] = list(self.rejection_reasons)
        return value


def attach_robust_probe_value_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = attach_quantized_probe_value_contract(payload)
    contract = dict(value["probe_value_contract"])
    contract.update({
        "contract_version": ROBUST_CONTRACT_VERSION,
        "maximum_current_probability_gap": MAXIMUM_CURRENT_PROBABILITY_GAP,
        "quantization_half_width": QUANTIZATION_HALF_WIDTH,
        "robust_admission_rule": (
            "Host admits only when current selected-minus-alternative probability "
            "is at most 0.10, the two registered outcomes derive different final "
            "skills, and lower-bound expected gain exceeds normalized probe cost."
        ),
    })
    value["probe_value_contract"] = contract
    value["probe_value_instruction"] = (
        "Always return top-level probe_value_certificate. For MODE_1 use only the "
        "supplied quantized tokens. The Host applies an ambiguity-aware robust "
        "lower-bound rule. For MODE_0 or MODE_2 return null."
    )
    return value


def validate_robust_probe_value_certificate(
    raw: Any, *, decision: SciAgentDecision | Mapping[str, Any],
    capability_contract: Mapping[str, Any], probe_value_contract: Mapping[str, Any],
) -> RobustProbeValueAssessment:
    if probe_value_contract.get("contract_version") != ROBUST_CONTRACT_VERSION:
        raise ValueError("unknown robust probe value contract")
    base_contract = dict(probe_value_contract)
    base_contract["contract_version"] = QUANTIZED_CONTRACT_VERSION
    base = validate_quantized_probe_value_certificate(
        raw, decision=decision, capability_contract=capability_contract,
        probe_value_contract=base_contract,
    )
    mode = _field(decision, "decision_mode")
    if mode != "RUN_MICRO_PROBE":
        return RobustProbeValueAssessment(
            None, None, 0.0, 0.0, 0.0, 0.0, False, False,
            ("AGENT_DID_NOT_REQUEST_PROBE",),
        )
    probability_tokens = probe_value_contract["probability_tokens"]
    current_selected = _probability(raw["current_selected_probability_token"], probability_tokens)
    current_alternative = _probability(raw["current_alternative_probability_token"], probability_tokens)
    gap = current_selected - current_alternative
    branches = []
    for item in raw["outcome_branches"]:
        probability = _probability(item["branch_probability_token"], probability_tokens)
        selected = _probability(item["selected_probability_token"], probability_tokens)
        alternative = _probability(item["alternative_probability_token"], probability_tokens)
        final_role = "SELECTED" if selected >= alternative else "ALTERNATIVE"
        lower_utility = max(
            0.0, selected - QUANTIZATION_HALF_WIDTH,
            alternative - QUANTIZATION_HALF_WIDTH,
        )
        branches.append((probability, final_role, lower_utility))
    discriminative = {row[1] for row in branches} == {"SELECTED", "ALTERNATIVE"}
    robust_posterior = sum(probability * utility for probability, _, utility in branches)
    robust_gain = robust_posterior - min(1.0, current_selected + QUANTIZATION_HALF_WIDTH)
    change_probability = sum(p for p, role, _ in branches if role == "ALTERNATIVE")
    cost = PROBE_MAXIMUM_STEPS[base.selected_probe_type] / TOTAL_CASE_MAX_STEPS
    reasons = []
    if gap > MAXIMUM_CURRENT_PROBABILITY_GAP + 1e-9:
        reasons.append("CURRENT_ACTION_NOT_AMBIGUOUS")
    if not discriminative:
        reasons.append("OUTCOMES_NOT_DECISION_DISCRIMINATIVE")
    if robust_gain <= cost:
        reasons.append("ROBUST_VALUE_NOT_ABOVE_NORMALIZED_COST")
    return RobustProbeValueAssessment(
        base.selected_probe_type, base.current_best_skill, gap, robust_gain, cost,
        change_probability, discriminative, not reasons, tuple(reasons),
    )


def _field(decision: SciAgentDecision | Mapping[str, Any], name: str) -> Any:
    return decision[name] if isinstance(decision, Mapping) else getattr(decision, name)


def _probability(token: Any, mapping: Mapping[str, Any]) -> float:
    if not isinstance(token, str) or token not in mapping:
        raise ValueError("unknown robust probability token")
    value = float(mapping[token])
    if value not in PROBABILITY_TOKENS.values():
        raise ValueError("robust probability is outside frozen lattice")
    return value
