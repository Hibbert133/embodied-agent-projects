"""Typed contracts for budgeted robotic recovery autoresearch."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np


PROBE_STEPS = (2, 4, 8)
PROBE_MAGNITUDES = (0.1, 0.2)
SECONDARY_AXIS_THRESHOLDS = (0.02, 0.04, 0.06)
DOMINANCE_RATIOS = (1.5, 2.0, 3.0)
SCHEDULE_OPTIONS = (("whole",), ("whole", "phase_aware"))
EVIDENCE_DETAILS = ("terminal", "temporal")


@dataclass(frozen=True)
class RecoveryPolicyConfig:
    """The complete structured search space exposed to the Research Agent."""

    config_id: str
    probe_steps_per_direction: int
    probe_magnitude: float
    secondary_axis_threshold: float
    dominance_ratio: float
    allowed_schedules: tuple[str, ...]
    offer_abstain: bool
    evidence_detail: str
    max_recovery_rollouts: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RecoveryPolicyConfig":
        try:
            config = cls(
                config_id=str(value["config_id"]),
                probe_steps_per_direction=int(value["probe_steps_per_direction"]),
                probe_magnitude=float(value["probe_magnitude"]),
                secondary_axis_threshold=float(value["secondary_axis_threshold"]),
                dominance_ratio=float(value["dominance_ratio"]),
                allowed_schedules=tuple(str(item) for item in value["allowed_schedules"]),
                offer_abstain=bool(value["offer_abstain"]),
                evidence_detail=str(value["evidence_detail"]),
                max_recovery_rollouts=int(value["max_recovery_rollouts"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid recovery policy config: {exc}") from exc
        return validate_recovery_policy_config(config)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _matches(value: float, allowed: Sequence[float]) -> bool:
    return any(np.isclose(value, candidate, atol=1e-9) for candidate in allowed)


def validate_recovery_policy_config(config: RecoveryPolicyConfig) -> RecoveryPolicyConfig:
    if not config.config_id.strip():
        raise ValueError("config_id must be non-empty")
    if config.probe_steps_per_direction not in PROBE_STEPS:
        raise ValueError(f"probe_steps_per_direction must be one of {PROBE_STEPS}")
    if not _matches(config.probe_magnitude, PROBE_MAGNITUDES):
        raise ValueError(f"probe_magnitude must be one of {PROBE_MAGNITUDES}")
    if not _matches(config.secondary_axis_threshold, SECONDARY_AXIS_THRESHOLDS):
        raise ValueError(
            f"secondary_axis_threshold must be one of {SECONDARY_AXIS_THRESHOLDS}"
        )
    if not _matches(config.dominance_ratio, DOMINANCE_RATIOS):
        raise ValueError(f"dominance_ratio must be one of {DOMINANCE_RATIOS}")
    if config.allowed_schedules not in SCHEDULE_OPTIONS:
        raise ValueError(f"allowed_schedules must be one of {SCHEDULE_OPTIONS}")
    if not config.offer_abstain:
        raise ValueError("offer_abstain must remain true")
    if config.evidence_detail not in EVIDENCE_DETAILS:
        raise ValueError(f"evidence_detail must be one of {EVIDENCE_DETAILS}")
    if config.max_recovery_rollouts != 1:
        raise ValueError("max_recovery_rollouts must remain 1")
    return config


@dataclass(frozen=True)
class ResearchProposal:
    """Exactly two bounded candidate configs plus a falsifiable hypothesis."""

    candidates: tuple[RecoveryPolicyConfig, RecoveryPolicyConfig]
    hypothesis: str
    targeted_counterexample_ids: tuple[str, ...]
    expected_metric_change: str

    def __post_init__(self) -> None:
        if len({item.config_id for item in self.candidates}) != 2:
            raise ValueError("ResearchProposal candidates must have unique config IDs")
        if not self.hypothesis.strip() or not self.expected_metric_change.strip():
            raise ValueError("proposal hypothesis and expected metric change are required")
        if not self.targeted_counterexample_ids:
            raise ValueError("proposal must target at least one counterexample")


@dataclass(frozen=True)
class SkillOutcome:
    case_id: str
    skill_id: str
    schedule: str
    success: bool
    recovery_environment_steps: int
    final_object_goal_distance: float
    correction_nonzero_elements: int


@dataclass(frozen=True)
class RuntimeSkillDecision:
    skill_id: str
    schedule: str
    reason: str


def choose_runtime_skill(
    config: RecoveryPolicyConfig, structured_diagnosis: Mapping[str, Any]
) -> RuntimeSkillDecision:
    """Apply a candidate's explicit decision boundary to visible estimates."""

    estimate = np.abs(np.asarray(structured_diagnosis.get("estimated_action_bias"), dtype=float))
    if estimate.shape != (2,) or not np.all(np.isfinite(estimate)):
        raise ValueError("structured diagnosis must contain two finite bias estimates")
    dominant = float(np.max(estimate))
    secondary = float(np.min(estimate))
    if dominant < config.secondary_axis_threshold:
        return RuntimeSkillDecision(
            "abstain_and_escalate", "none", "both inferred components are below threshold"
        )
    ratio = dominant / max(secondary, 1e-12)
    if secondary >= config.secondary_axis_threshold and ratio <= config.dominance_ratio:
        skill_id = "simultaneous_xy_repair"
        reason = "secondary component is material and axes are not strongly dominant"
    else:
        skill_id = "dominant_axis_repair"
        reason = "one component is below threshold or the dominant ratio is high"
    schedule = (
        "phase_aware"
        if skill_id == "dominant_axis_repair" and "phase_aware" in config.allowed_schedules
        else "whole"
    )
    return RuntimeSkillDecision(skill_id, schedule, reason)


def select_counterfactual_skill(outcomes: Sequence[SkillOutcome]) -> SkillOutcome:
    """Select the audit-only best skill from actual outcomes, never fault labels."""

    if not outcomes:
        raise ValueError("counterfactual selection requires outcomes")
    case_ids = {item.case_id for item in outcomes}
    if len(case_ids) != 1:
        raise ValueError("counterfactual outcomes must belong to one case")
    abstain = [item for item in outcomes if item.skill_id == "abstain_and_escalate"]
    if len(abstain) != 1:
        raise ValueError("counterfactual outcomes require exactly one abstain option")
    successful = [item for item in outcomes if item.success]
    if not successful:
        return abstain[0]
    return min(
        successful,
        key=lambda item: (
            item.recovery_environment_steps,
            item.correction_nonzero_elements,
            0 if item.schedule == "whole" else 1,
            item.skill_id,
        ),
    )


@dataclass
class ExperimentBudget:
    max_api_calls: int
    max_environment_steps: int
    api_calls: int = 0
    environment_steps: int = 0

    def __post_init__(self) -> None:
        if self.max_api_calls <= 0 or self.max_environment_steps <= 0:
            raise ValueError("experiment budgets must be positive")

    def consume_api_call(self, count: int = 1) -> None:
        if count <= 0 or self.api_calls + count > self.max_api_calls:
            raise RuntimeError("API-call budget exceeded")
        self.api_calls += count

    def consume_environment_steps(self, count: int) -> None:
        if count < 0 or self.environment_steps + count > self.max_environment_steps:
            raise RuntimeError("environment-step budget exceeded")
        self.environment_steps += count

    def to_dict(self) -> dict[str, int]:
        return {
            "max_api_calls": self.max_api_calls,
            "max_environment_steps": self.max_environment_steps,
            "api_calls": self.api_calls,
            "environment_steps": self.environment_steps,
        }


def select_noise_calibration(
    rows: Sequence[Mapping[str, Any]], *, max_clipped_step_fraction: float = 0.5
) -> Mapping[str, Any]:
    """Pre-registered selection: closest to 50% failure, then lower std."""

    if not rows or not 0.0 <= max_clipped_step_fraction <= 1.0:
        raise ValueError("valid calibration rows and clipping threshold are required")
    eligible = [
        row for row in rows
        if float(row["clipped_step_fraction"]) <= max_clipped_step_fraction
    ]
    candidates = eligible or list(rows)
    return min(
        candidates,
        key=lambda row: (
            abs(float(row["failure_rate"]) - 0.5),
            float(row["noise_std"]),
        ),
    )
