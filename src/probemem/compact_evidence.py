"""Leakage-safe compact causal evidence for ProbeMem-Online Gate A."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

import numpy as np

from src.reasoning.evidence import validate_no_oracle_evidence


COMPACT_EVIDENCE_SCHEMA_VERSION = 1
REGISTERED_SKILLS = (
    "BOUNDED_PLANAR_COMPENSATION",
    "INDEPENDENT_STOCHASTIC_RETRY",
)

SKILL_SEMANTICS: dict[str, dict[str, str]] = {
    "BOUNDED_PLANAR_COMPENSATION": {
        "purpose": "Counteract a persistent signed drift whose direction and magnitude remain consistent across repeated probe responses.",
        "not_appropriate_when": "Probe responses show no stable direction or have high variance.",
    },
    "INDEPENDENT_STOCHASTIC_RETRY": {
        "purpose": "Execute the fixed policy under an independent realization when probe responses are highly variable and no stable signed correction is supported.",
        "not_appropriate_when": "A repeatable directional drift supports a bounded compensation.",
    },
    "ABSTAIN": {
        "purpose": "Terminate only when neither registered skill has sufficient evidence, the interaction budget is insufficient, or required evidence is invalid.",
        "not_appropriate_when": "At least one registered skill is supported by valid evidence and sufficient budget remains.",
    },
}


@dataclass(frozen=True)
class CompactCausalEvidence:
    schema_version: int
    evidence_id: str
    episode_id: int
    task_progress: float
    final_object_goal_distance: float
    estimated_drift_xy: tuple[float, float]
    estimated_bias_std_norm: float
    relative_bias_std: float
    dominant_axis_sign_agreement: float
    mean_estimation_residual: float
    probe_repeat_count: int
    probe_environment_steps: int
    remaining_interaction_budget: int
    available_registered_skills: tuple[str, str]

    def __post_init__(self) -> None:
        if self.schema_version != COMPACT_EVIDENCE_SCHEMA_VERSION or not self.evidence_id.strip():
            raise ValueError("unsupported compact evidence schema")
        if self.episode_id <= 0 or self.probe_repeat_count <= 0:
            raise ValueError("compact evidence requires positive provenance and samples")
        if min(self.probe_environment_steps, self.remaining_interaction_budget) <= 0:
            raise ValueError("compact evidence requires positive budgets")
        numeric = (
            self.task_progress, self.final_object_goal_distance, *self.estimated_drift_xy,
            self.estimated_bias_std_norm, self.relative_bias_std,
            self.dominant_axis_sign_agreement, self.mean_estimation_residual,
        )
        if not all(math.isfinite(item) for item in numeric):
            raise ValueError("compact evidence requires finite metrics")
        if self.final_object_goal_distance < 0 or self.estimated_bias_std_norm < 0:
            raise ValueError("compact evidence distances and variation must be non-negative")
        if not 0.0 <= self.dominant_axis_sign_agreement <= 1.0:
            raise ValueError("sign agreement must be in [0, 1]")
        if self.available_registered_skills != REGISTERED_SKILLS:
            raise ValueError("compact evidence must expose exactly the registered skills")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "episode_id": self.episode_id,
            "task_progress": self.task_progress,
            "final_object_goal_distance": self.final_object_goal_distance,
            "estimated_drift_xy": list(self.estimated_drift_xy),
            "estimated_bias_std_norm": self.estimated_bias_std_norm,
            "repeat_response_consistency": {
                "relative_bias_std": self.relative_bias_std,
                "dominant_axis_sign_agreement": self.dominant_axis_sign_agreement,
                "mean_estimation_residual": self.mean_estimation_residual,
            },
            "probe_sample_count": self.probe_repeat_count,
            "probe_environment_steps": self.probe_environment_steps,
            "remaining_interaction_budget": self.remaining_interaction_budget,
            "available_registered_skills": list(self.available_registered_skills),
        }


def build_compact_causal_evidence(agent_evidence: Mapping[str, Any]) -> CompactCausalEvidence:
    validate_no_oracle_evidence(agent_evidence)
    try:
        initial = agent_evidence["initial_evidence"]
        probe = agent_evidence["registered_probe_evidence"]
        repetitions = probe["repetitions"]
        consistency = probe["consistency"]
        drifts = np.asarray(
            [item["inference"]["estimated_drift_per_step"] for item in repetitions],
            dtype=float,
        )
        if drifts.ndim != 2 or drifts.shape[1] != 2 or len(drifts) != int(consistency["repeat_count"]):
            raise ValueError("probe repetitions and consistency count differ")
        mean_drift = np.mean(drifts, axis=0)
        return CompactCausalEvidence(
            schema_version=COMPACT_EVIDENCE_SCHEMA_VERSION,
            evidence_id=str(agent_evidence["evidence_id"]),
            episode_id=int(agent_evidence["episode_id"]),
            task_progress=float(initial["task_state"]["progress_to_goal"]),
            final_object_goal_distance=float(initial["task_state"]["final_object_goal_distance"]),
            estimated_drift_xy=(float(mean_drift[0]), float(mean_drift[1])),
            estimated_bias_std_norm=float(consistency["estimated_bias_std_norm"]),
            relative_bias_std=float(consistency["relative_bias_std"]),
            dominant_axis_sign_agreement=float(consistency["dominant_axis_sign_agreement"]),
            mean_estimation_residual=float(consistency["mean_estimation_residual"]),
            probe_repeat_count=int(consistency["repeat_count"]),
            probe_environment_steps=int(probe["probe_environment_steps"]),
            remaining_interaction_budget=int(agent_evidence["remaining_verification_budget"]),
            available_registered_skills=REGISTERED_SKILLS,
        )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError("full Agent evidence cannot build compact causal evidence") from exc
