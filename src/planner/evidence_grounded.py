"""Leakage-safe mechanism-to-intervention mapping for frozen P1."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping

import numpy as np

from src.autoresearch import RecoveryPolicyConfig, choose_runtime_skill
from src.reasoning.evidence import validate_no_oracle_evidence
from src.recovery_skills import build_planar_recovery_skills, select_skill


class InterventionFamily(str, Enum):
    BIAS_COMPENSATION = "bias_compensation"
    STOCHASTIC_RETRY = "stochastic_retry"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class GroundedInterventionPlan:
    plan_id: str
    evidence_id: str
    mechanism_belief: str
    family: InterventionFamily
    skill_id: str
    schedule: str
    correction: tuple[float, float, float, float]
    evidence_source: str
    requires_fresh_verification: bool
    rationale: str

    def __post_init__(self) -> None:
        if not all((self.plan_id.strip(), self.evidence_id.strip(), self.rationale.strip())):
            raise ValueError("grounded intervention requires identity and rationale")
        if self.mechanism_belief not in {"stable_bias", "stochastic_noise"}:
            raise ValueError("unsupported mechanism belief")
        if len(self.correction) != 4 or self.correction[2:] != (0.0, 0.0):
            raise ValueError("intervention correction must be planar")
        if self.family is InterventionFamily.STOCHASTIC_RETRY and any(self.correction):
            raise ValueError("stochastic retry cannot add a deterministic correction")
        if self.family is InterventionFamily.ABSTAIN and self.requires_fresh_verification:
            raise ValueError("abstention cannot request fresh verification")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def execution_signature(self) -> tuple[Any, ...]:
        """Identify matched actions so equivalent rollouts can be deduplicated."""

        return self.family.value, self.schedule, self.correction


def passive_correction_context(state: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt visible initial-rollout response estimates to the correction API."""

    validate_no_oracle_evidence(state)
    temporal = state.get("temporal_response")
    if not isinstance(temporal, Mapping):
        raise ValueError("passive correction requires temporal_response evidence")
    residual = np.asarray(temporal.get("normalized_residual_xy"), dtype=float)
    if residual.shape != (2,):
        raise ValueError("passive normalized residual must contain x and y")
    return {
        "protocol": "passive_planar_response_v1",
        "probe_environment_steps": 0,
        "inference": {
            "estimated_drift_per_step": temporal.get("estimated_drift_xy"),
            "axis_response_gain": temporal.get("response_gain_xy"),
            "residual": float(np.linalg.norm(residual)),
        },
    }


def first_registered_probe_context(repeated_context: Mapping[str, Any]) -> dict[str, Any]:
    """Use the preregistered first repetition for correction parameterization."""

    validate_no_oracle_evidence(repeated_context)
    repetitions = repeated_context.get("repetitions")
    if not isinstance(repetitions, list) or len(repetitions) != 4:
        raise ValueError("registered correction requires four probe repetitions")
    first = repetitions[0]
    if not isinstance(first, Mapping) or not isinstance(first.get("inference"), Mapping):
        raise ValueError("first probe repetition is missing visible inference")
    return {
        "protocol": "registered_probe_first_repetition_v1",
        "probe_environment_steps": int(repeated_context["probe_environment_steps"]),
        "inference": dict(first["inference"]),
    }


def select_grounded_intervention(
    *,
    plan_id: str,
    evidence_id: str,
    mechanism_belief: str,
    correction_context: Mapping[str, Any] | None,
    recovery_config: RecoveryPolicyConfig,
    evidence_source: str,
) -> GroundedInterventionPlan:
    if mechanism_belief == "stochastic_noise":
        return GroundedInterventionPlan(
            plan_id=plan_id,
            evidence_id=evidence_id,
            mechanism_belief=mechanism_belief,
            family=InterventionFamily.STOCHASTIC_RETRY,
            skill_id="independent_seed_retry",
            schedule="whole",
            correction=(0.0, 0.0, 0.0, 0.0),
            evidence_source=evidence_source,
            requires_fresh_verification=True,
            rationale="mechanism belief favors a fresh execution realization",
        )
    if mechanism_belief != "stable_bias" or correction_context is None:
        raise ValueError("stable-bias intervention requires visible correction evidence")
    validate_no_oracle_evidence(correction_context)
    diagnosis, skills = build_planar_recovery_skills(correction_context)
    decision = choose_runtime_skill(recovery_config, diagnosis)
    if decision.skill_id == "abstain_and_escalate":
        return GroundedInterventionPlan(
            plan_id=plan_id,
            evidence_id=evidence_id,
            mechanism_belief=mechanism_belief,
            family=InterventionFamily.ABSTAIN,
            skill_id=decision.skill_id,
            schedule="none",
            correction=(0.0, 0.0, 0.0, 0.0),
            evidence_source=evidence_source,
            requires_fresh_verification=False,
            rationale=decision.reason,
        )
    skill = select_skill(skills, decision.skill_id)
    return GroundedInterventionPlan(
        plan_id=plan_id,
        evidence_id=evidence_id,
        mechanism_belief=mechanism_belief,
        family=InterventionFamily.BIAS_COMPENSATION,
        skill_id=decision.skill_id,
        schedule=decision.schedule,
        correction=skill.correction,
        evidence_source=evidence_source,
        requires_fresh_verification=True,
        rationale=decision.reason,
    )
