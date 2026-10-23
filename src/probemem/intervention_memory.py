"""Accepted-only post-probe episodic records for ProbeMem development.

This schema complements the legacy seven-feature Phase-C memory without
changing it. Operational retrieval remains disabled until a separate protocol
freezes applicability and abstention rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.probemem.intervention_utility import InterventionApplicabilitySignature
from src.probemem.models import InterventionSkill
from src.reasoning.evidence import validate_no_oracle_evidence


VERIFIED_INTERVENTION_EPISODE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VerifiedInterventionEpisode:
    schema_version: int
    record_id: str
    source_episode_id: int
    source_run_id: str
    source_manifest_id: str
    source_git_commit: str
    selection_policy_id: str
    applicability_signature: InterventionApplicabilitySignature
    selected_skill: InterventionSkill
    fresh_verification_status: str
    final_object_goal_distance: float
    verification_steps: int
    total_interaction_steps: int
    operational_retrieval_enabled: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != VERIFIED_INTERVENTION_EPISODE_SCHEMA_VERSION:
            raise ValueError("unsupported verified intervention episode schema")
        if not all(
            value.strip()
            for value in (
                self.record_id,
                self.source_run_id,
                self.source_manifest_id,
                self.source_git_commit,
                self.selection_policy_id,
            )
        ):
            raise ValueError("verified intervention episode requires provenance")
        if self.source_episode_id != self.applicability_signature.episode_id:
            raise ValueError("episode and applicability provenance differ")
        if self.fresh_verification_status != "ACCEPTED":
            raise ValueError("only fresh ACCEPTED outcomes enter verified memory")
        if self.selected_skill in {
            InterventionSkill.ABSTAIN,
            InterventionSkill.NO_INTERVENTION,
        }:
            raise ValueError("verified intervention episode requires executed skill")
        if (
            self.final_object_goal_distance < 0.0
            or self.verification_steps <= 0
            or self.total_interaction_steps <= 0
        ):
            raise ValueError("verified intervention outcome metrics are invalid")
        if self.operational_retrieval_enabled:
            raise ValueError(
                "schema v1 snapshot is development-only until retrieval is frozen"
            )
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "source_episode_id": self.source_episode_id,
            "source_run_id": self.source_run_id,
            "source_manifest_id": self.source_manifest_id,
            "source_git_commit": self.source_git_commit,
            "selection_policy_id": self.selection_policy_id,
            "applicability_signature": self.applicability_signature.to_dict(),
            "selected_skill": self.selected_skill.value,
            "fresh_verification_status": self.fresh_verification_status,
            "final_object_goal_distance": self.final_object_goal_distance,
            "verification_steps": self.verification_steps,
            "total_interaction_steps": self.total_interaction_steps,
            "verified_episode_eligible": True,
            "operational_retrieval_enabled": self.operational_retrieval_enabled,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "VerifiedInterventionEpisode":
        signature_payload = payload["applicability_signature"]
        features = signature_payload["features"]
        from src.probemem.intervention_utility import INTERVENTION_APPLICABILITY_FEATURES

        return cls(
            schema_version=int(payload["schema_version"]),
            record_id=str(payload["record_id"]),
            source_episode_id=int(payload["source_episode_id"]),
            source_run_id=str(payload["source_run_id"]),
            source_manifest_id=str(payload["source_manifest_id"]),
            source_git_commit=str(payload["source_git_commit"]),
            selection_policy_id=str(payload["selection_policy_id"]),
            applicability_signature=InterventionApplicabilitySignature(
                schema_version=int(signature_payload["schema_version"]),
                evidence_id=str(signature_payload["evidence_id"]),
                episode_id=int(signature_payload["episode_id"]),
                values=tuple(
                    float(features[name]) for name in INTERVENTION_APPLICABILITY_FEATURES
                ),
            ),
            selected_skill=InterventionSkill(str(payload["selected_skill"])),
            fresh_verification_status=str(payload["fresh_verification_status"]),
            final_object_goal_distance=float(payload["final_object_goal_distance"]),
            verification_steps=int(payload["verification_steps"]),
            total_interaction_steps=int(payload["total_interaction_steps"]),
            operational_retrieval_enabled=bool(
                payload.get("operational_retrieval_enabled", False)
            ),
        )
