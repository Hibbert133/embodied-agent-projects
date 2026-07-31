"""Falsifiable, development-only intervention-utility audit contracts.

These records describe what happened after one bounded intervention.  They do
not prove that the intervention was optimal, and they are not actionable memory
or verified principles.  Counterfactual skill comparisons require separately
matched fresh rollouts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from src.probemem.episodic_memory import EvidenceSignature
from src.probemem.models import InterventionSkill, PredictedOutcome
from src.reasoning.evidence import validate_no_oracle_evidence


INTERVENTION_UTILITY_SCHEMA_VERSION = 1
_STATUS_RANK = {"REJECTED": 0, "INCONCLUSIVE": 1, "ACCEPTED": 2}
INTERVENTION_APPLICABILITY_FEATURES = (
    "progress_to_goal",
    "final_object_goal_distance",
    "temporal_uncertainty",
    "phase_inconsistency",
    "estimated_drift_x",
    "estimated_drift_y",
    "normalized_residual_norm",
    "probe_estimated_bias_x",
    "probe_estimated_bias_y",
    "probe_estimated_bias_std_norm",
    "probe_relative_bias_std",
    "probe_mean_estimation_residual",
    "probe_dominant_axis_sign_agreement",
)


class PredictionRelation(str, Enum):
    MATCHED = "MATCHED"
    POSITIVE_SURPRISE = "POSITIVE_SURPRISE"
    NEGATIVE_SURPRISE = "NEGATIVE_SURPRISE"


class UtilityVerdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNRESOLVED = "UNRESOLVED"
    CONTRADICTED = "CONTRADICTED"


@dataclass(frozen=True)
class InterventionApplicabilitySignature:
    """Agent-visible state and registered-probe evidence at intervention time."""

    schema_version: int
    evidence_id: str
    episode_id: int
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.schema_version != INTERVENTION_UTILITY_SCHEMA_VERSION:
            raise ValueError("unsupported intervention applicability schema version")
        if not self.evidence_id.strip() or self.episode_id <= 0:
            raise ValueError("applicability signature requires causal provenance")
        if len(self.values) != len(INTERVENTION_APPLICABILITY_FEATURES):
            raise ValueError("applicability signature has an invalid feature count")
        if not all(math.isfinite(item) for item in self.values):
            raise ValueError("applicability signature requires finite features")

    @classmethod
    def from_agent_evidence(
        cls, evidence: Mapping[str, Any]
    ) -> "InterventionApplicabilitySignature":
        validate_no_oracle_evidence(evidence)
        base = EvidenceSignature.from_structured_evidence(evidence)
        probe = evidence.get("registered_probe_evidence")
        if not isinstance(probe, Mapping):
            raise ValueError("intervention applicability requires registered probe evidence")
        consistency = probe.get("consistency")
        if not isinstance(consistency, Mapping):
            raise ValueError("registered probe evidence requires consistency statistics")
        bias = tuple(float(item) for item in consistency["estimated_bias_mean"])
        if len(bias) != 2:
            raise ValueError("registered probe bias estimate must be two-dimensional")
        values = base.values + (
            bias[0],
            bias[1],
            float(consistency["estimated_bias_std_norm"]),
            float(consistency["relative_bias_std"]),
            float(consistency["mean_estimation_residual"]),
            float(consistency["dominant_axis_sign_agreement"]),
        )
        return cls(
            schema_version=INTERVENTION_UTILITY_SCHEMA_VERSION,
            evidence_id=str(evidence["evidence_id"]),
            episode_id=int(evidence["episode_id"]),
            values=values,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "episode_id": self.episode_id,
            "features": dict(zip(INTERVENTION_APPLICABILITY_FEATURES, self.values)),
        }


@dataclass(frozen=True)
class FreshVerificationObservation:
    evidence_id: str
    verification_status: str
    verification_success: bool
    environment_steps: int
    final_object_goal_distance: float
    goal_distance_change: float

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("fresh verification requires evidence provenance")
        if self.verification_status not in _STATUS_RANK:
            raise ValueError("unsupported fresh verification status")
        if self.verification_success != (self.verification_status == "ACCEPTED"):
            raise ValueError("verification success must match ACCEPTED status")
        if self.environment_steps <= 0:
            raise ValueError("fresh verification must consume positive environment steps")
        if self.final_object_goal_distance < 0:
            raise ValueError("final object-goal distance must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "verification_status": self.verification_status,
            "verification_success": self.verification_success,
            "environment_steps": self.environment_steps,
            "final_object_goal_distance": self.final_object_goal_distance,
            "goal_distance_change": self.goal_distance_change,
        }


def prediction_relation(
    predicted_status: str, observed_status: str
) -> PredictionRelation:
    if predicted_status not in _STATUS_RANK or observed_status not in _STATUS_RANK:
        raise ValueError("prediction relation requires registered verification statuses")
    difference = _STATUS_RANK[observed_status] - _STATUS_RANK[predicted_status]
    if difference == 0:
        return PredictionRelation.MATCHED
    if difference > 0:
        return PredictionRelation.POSITIVE_SURPRISE
    return PredictionRelation.NEGATIVE_SURPRISE


def utility_verdict(observed_status: str) -> UtilityVerdict:
    if observed_status == "ACCEPTED":
        return UtilityVerdict.SUPPORTED
    if observed_status == "INCONCLUSIVE":
        return UtilityVerdict.UNRESOLVED
    if observed_status == "REJECTED":
        return UtilityVerdict.CONTRADICTED
    raise ValueError("utility verdict requires a registered verification status")


@dataclass(frozen=True)
class InterventionUtilityRecord:
    """One action-conditional prediction followed by fresh verification.

    ``utility_verdict`` concerns only the executed skill in this episode.  It
    cannot identify a better alternative without a matched counterfactual.
    """

    schema_version: int
    record_id: str
    source_episode_id: int
    source_run_id: str
    source_manifest_id: str
    source_method: str
    applicability_signature: InterventionApplicabilitySignature
    selected_skill: InterventionSkill
    predicted_outcome: PredictedOutcome
    observed_outcome: FreshVerificationObservation
    prediction_relation: PredictionRelation
    utility_verdict: UtilityVerdict
    record_role: str = "development_intervention_utility_audit"
    actionable_memory: bool = False
    principle_promotion_eligible: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != INTERVENTION_UTILITY_SCHEMA_VERSION:
            raise ValueError("unsupported intervention utility schema version")
        if not all(
            item.strip()
            for item in (
                self.record_id,
                self.source_run_id,
                self.source_manifest_id,
                self.source_method,
            )
        ):
            raise ValueError("intervention utility record requires complete provenance")
        if self.source_episode_id != self.applicability_signature.episode_id:
            raise ValueError("utility record and applicability episode IDs differ")
        if self.selected_skill in {InterventionSkill.ABSTAIN, InterventionSkill.NO_INTERVENTION}:
            raise ValueError("utility audit requires an executed intervention skill")
        expected_relation = prediction_relation(
            self.predicted_outcome.verification_status,
            self.observed_outcome.verification_status,
        )
        if self.prediction_relation is not expected_relation:
            raise ValueError("prediction relation must be host-derived from fresh outcome")
        expected_verdict = utility_verdict(self.observed_outcome.verification_status)
        if self.utility_verdict is not expected_verdict:
            raise ValueError("utility verdict must be host-derived from fresh outcome")
        if self.record_role != "development_intervention_utility_audit":
            raise ValueError("schema v1 supports development audit records only")
        if self.actionable_memory or self.principle_promotion_eligible:
            raise ValueError("development utility records cannot enter actionable memory")
        validate_no_oracle_evidence(self.applicability_signature.to_dict())

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        source_episode_id: int,
        source_run_id: str,
        source_manifest_id: str,
        source_method: str,
        applicability_signature: InterventionApplicabilitySignature,
        selected_skill: InterventionSkill,
        predicted_outcome: PredictedOutcome,
        observed_outcome: FreshVerificationObservation,
    ) -> "InterventionUtilityRecord":
        return cls(
            schema_version=INTERVENTION_UTILITY_SCHEMA_VERSION,
            record_id=record_id,
            source_episode_id=source_episode_id,
            source_run_id=source_run_id,
            source_manifest_id=source_manifest_id,
            source_method=source_method,
            applicability_signature=applicability_signature,
            selected_skill=selected_skill,
            predicted_outcome=predicted_outcome,
            observed_outcome=observed_outcome,
            prediction_relation=prediction_relation(
                predicted_outcome.verification_status,
                observed_outcome.verification_status,
            ),
            utility_verdict=utility_verdict(observed_outcome.verification_status),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "source_episode_id": self.source_episode_id,
            "source_run_id": self.source_run_id,
            "source_manifest_id": self.source_manifest_id,
            "source_method": self.source_method,
            "applicability_signature": self.applicability_signature.to_dict(),
            "selected_skill": self.selected_skill.value,
            "predicted_outcome": {
                "verification_status": self.predicted_outcome.verification_status,
                "expected_progress": self.predicted_outcome.expected_progress,
                "expected_additional_steps": self.predicted_outcome.expected_additional_steps,
            },
            "observed_outcome": self.observed_outcome.to_dict(),
            "prediction_relation": self.prediction_relation.value,
            "utility_verdict": self.utility_verdict.value,
            "record_role": self.record_role,
            "actionable_memory": self.actionable_memory,
            "principle_promotion_eligible": self.principle_promotion_eligible,
        }
