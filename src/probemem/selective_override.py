"""Outcome-independent ambiguity and deterministic Memory override guards."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from src.probe.directional import BiasEstimate, summarize_probe_consistency
from src.probemem.models import InterventionSkill
from src.probemem.persistent_regime import FROZEN_CONSISTENCY_THRESHOLD
from src.reasoning.evidence import validate_no_oracle_evidence


COMP = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


@dataclass(frozen=True)
class ProbeAmbiguityAssessment:
    full_score: float
    leave_one_out_scores: tuple[float, ...]
    full_action: InterventionSkill
    leave_one_out_actions: tuple[InterventionSkill, ...]
    ambiguous: bool

    @property
    def should_call_glm(self) -> bool:
        return self.ambiguous

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["full_action"] = self.full_action.value
        value["leave_one_out_actions"] = [action.value for action in self.leave_one_out_actions]
        value["should_call_glm"] = self.should_call_glm
        return value


@dataclass(frozen=True)
class SelectiveOverrideDecision:
    selected_skill: InterventionSkill
    deterministic_skill: InterventionSkill
    proposed_skill: InterventionSkill | None
    ambiguity_required_api: bool
    memory_preference: InterventionSkill | None
    override_authorized: bool
    fallback_used: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for name in ("selected_skill", "deterministic_skill", "proposed_skill", "memory_preference"):
            item = getattr(self, name)
            value[name] = None if item is None else item.value
        return value


def assess_probe_ambiguity(
    estimates: Sequence[BiasEstimate], *, threshold: float = FROZEN_CONSISTENCY_THRESHOLD,
) -> ProbeAmbiguityAssessment:
    """Use leave-one-repeat-out side stability; no matched outcome is consumed."""

    if len(estimates) != 4:
        raise ValueError("registered selective override requires exactly four probe estimates")
    if threshold < 0:
        raise ValueError("frozen variance threshold must be non-negative")
    full_score = summarize_probe_consistency(estimates).estimated_bias_std_norm
    omitted = tuple(
        summarize_probe_consistency(tuple(item for index, item in enumerate(estimates) if index != omitted_index)).estimated_bias_std_norm
        for omitted_index in range(len(estimates))
    )
    full_action = _variance_action(full_score, threshold)
    actions = tuple(_variance_action(score, threshold) for score in omitted)
    return ProbeAmbiguityAssessment(
        full_score=float(full_score), leave_one_out_scores=tuple(float(score) for score in omitted),
        full_action=full_action, leave_one_out_actions=actions,
        ambiguous=any(action is not full_action for action in actions),
    )


def estimates_from_probe_context(probe_context: Mapping[str, Any]) -> tuple[BiasEstimate, ...]:
    validate_no_oracle_evidence(probe_context)
    repetitions = probe_context.get("repetitions")
    if not isinstance(repetitions, Sequence) or isinstance(repetitions, (str, bytes)) or len(repetitions) != 4:
        raise ValueError("registered repeated probe requires exactly four repetitions")
    estimates = []
    for repetition in repetitions:
        if not isinstance(repetition, Mapping) or not isinstance(repetition.get("inference"), Mapping):
            raise ValueError("probe repetition lacks Agent-visible inference")
        inference = repetition["inference"]
        estimates.append(BiasEstimate(
            dominant_axis=str(inference["dominant_axis"]),
            estimated_direction=str(inference["estimated_direction"]),
            estimated_drift_per_step=tuple(float(value) for value in inference["estimated_drift_per_step"]),
            axis_response_gain=tuple(float(value) for value in inference["axis_response_gain"]),
            residual=float(inference["residual"]), confidence=float(inference["confidence"]),
            recommended_correction_axis=str(inference["recommended_correction_axis"]),
            recommended_correction_direction=str(inference["recommended_correction_direction"]),
        ))
    return tuple(estimates)


def agreed_memory_preference(memory_payload: Mapping[str, Any]) -> InterventionSkill | None:
    """Return an action only when global and recent acceptance preferences agree."""

    validate_no_oracle_evidence(memory_payload)
    actions = memory_payload.get("candidate_actions")
    if not isinstance(actions, Mapping) or set(actions) != {COMP.value, RETRY.value}:
        raise ValueError("action-conditioned payload must contain both registered skills")
    preferences = []
    for scope in ("global", "recent"):
        comp = float(actions[COMP.value][scope]["accepted_probability"])
        retry = float(actions[RETRY.value][scope]["accepted_probability"])
        preferences.append(COMP if comp > retry else RETRY if retry > comp else None)
    return preferences[0] if preferences[0] is not None and preferences[0] is preferences[1] else None


def guard_memory_override(
    *, assessment: ProbeAmbiguityAssessment, proposed_skill: InterventionSkill | None,
    memory_payload: Mapping[str, Any],
) -> SelectiveOverrideDecision:
    """Protect stable physical decisions and fail back on Memory disagreement."""

    deterministic = assessment.full_action
    if not assessment.ambiguous:
        return SelectiveOverrideDecision(
            deterministic, deterministic, None, False, None, False, False,
            "High-confidence leave-one-repeat-out decision bypasses GLM and Memory.",
        )
    preference = agreed_memory_preference(memory_payload)
    if proposed_skill is None:
        return SelectiveOverrideDecision(
            deterministic, deterministic, None, True, preference, False, True,
            "Invalid, unavailable, or abstaining proposal falls back to the frozen rule.",
        )
    if proposed_skill is deterministic:
        return SelectiveOverrideDecision(
            deterministic, deterministic, proposed_skill, True, preference, False, False,
            "GLM proposal agrees with the frozen rule; no override is required.",
        )
    if preference is proposed_skill:
        return SelectiveOverrideDecision(
            proposed_skill, deterministic, proposed_skill, True, preference, True, False,
            "Ambiguous physical evidence and global/recent Memory agree with the proposed override.",
        )
    return SelectiveOverrideDecision(
        deterministic, deterministic, proposed_skill, True, preference, False, True,
        "Memory scopes conflict with the proposed override; use the frozen-rule fallback.",
    )


def _variance_action(score: float, threshold: float) -> InterventionSkill:
    return RETRY if score > threshold else COMP
