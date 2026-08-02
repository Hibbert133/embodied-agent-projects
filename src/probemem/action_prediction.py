"""Frozen deterministic action-conditioned outcome estimator."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from src.probemem.action_evidence import ActionConditionalEvidencePack
from src.probemem.action_memory import EXECUTABLE_ACR_SKILLS, OUTCOME_STATUSES
from src.probemem.models import InterventionSkill
from src.reasoning.evidence import validate_no_oracle_evidence


@dataclass(frozen=True)
class CandidateActionPrediction:
    intervention_skill: InterventionSkill
    probabilities: Mapping[str, float]
    predicted_status: str
    predicted_progress: float | None
    utility: float
    history_count: int

    def __post_init__(self) -> None:
        if set(self.probabilities) != set(OUTCOME_STATUSES):
            raise ValueError("action prediction requires all outcome probabilities")
        if any(not 0.0 <= item <= 1.0 for item in self.probabilities.values()):
            raise ValueError("outcome probabilities must be in [0, 1]")
        if abs(sum(self.probabilities.values()) - 1.0) > 1e-12:
            raise ValueError("outcome probabilities must sum to one")
        if self.predicted_status not in OUTCOME_STATUSES:
            raise ValueError("unsupported predicted status")
        if self.predicted_progress is not None and not math.isfinite(self.predicted_progress):
            raise ValueError("predicted progress must be finite or null")
        expected = self.probabilities["ACCEPTED"] + 0.5 * self.probabilities["INCONCLUSIVE"]
        if abs(expected - self.utility) > 1e-12:
            raise ValueError("action utility differs from frozen definition")

    def to_dict(self) -> dict[str, Any]:
        return {
            "intervention_skill": self.intervention_skill.value,
            "probabilities": dict(self.probabilities),
            "predicted_status": self.predicted_status,
            "predicted_progress": self.predicted_progress,
            "utility": self.utility,
            "history_count": self.history_count,
        }


@dataclass(frozen=True)
class ActionConditionalDecision:
    schema_version: int
    evidence_id: str
    episode_id: int
    selected_skill: InterventionSkill | None
    decision_reason: str
    predictions: Mapping[InterventionSkill, CandidateActionPrediction]

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not self.evidence_id.strip():
            raise ValueError("unsupported ACR decision schema")
        if set(self.predictions) != set(EXECUTABLE_ACR_SKILLS):
            raise ValueError("ACR decision must predict both actions")
        if self.selected_skill is not None and self.selected_skill not in EXECUTABLE_ACR_SKILLS:
            raise ValueError("ACR selected an unregistered action")
        if self.decision_reason not in {"SELECT_HIGHER_UTILITY", "ABSTAIN_COLD_START", "ABSTAIN_TIE"}:
            raise ValueError("unsupported ACR decision reason")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "episode_id": self.episode_id,
            "selected_skill": self.selected_skill.value if self.selected_skill else None,
            "decision_reason": self.decision_reason,
            "predictions": {
                skill.value: self.predictions[skill].to_dict()
                for skill in EXECUTABLE_ACR_SKILLS
            },
        }


class DeterministicActionConditionalEstimator:
    def __init__(
        self,
        *,
        dirichlet_prior: float = 1.0,
        inconclusive_utility: float = 0.5,
        minimum_history_per_action: int = 3,
    ) -> None:
        if dirichlet_prior != 1.0 or inconclusive_utility != 0.5:
            raise ValueError("ACR v1 estimator constants are frozen")
        if minimum_history_per_action != 3:
            raise ValueError("ACR v1 minimum history is frozen at three")
        self.prior = dirichlet_prior
        self.inconclusive_utility = inconclusive_utility
        self.minimum_history = minimum_history_per_action

    @staticmethod
    def _predicted_status(probabilities: Mapping[str, float]) -> str:
        maximum = max(probabilities.values())
        winners = [key for key, value in probabilities.items() if value == maximum]
        return winners[0] if len(winners) == 1 else "INCONCLUSIVE"

    def _predict_action(self, pack: ActionConditionalEvidencePack, skill: InterventionSkill) -> CandidateActionPrediction:
        evidence = pack.candidate_actions[skill]
        parameters = {
            status: self.prior + evidence.classes[status].weighted_evidence
            for status in OUTCOME_STATUSES
        }
        total = sum(parameters.values())
        probabilities = {status: parameters[status] / total for status in OUTCOME_STATUSES}
        retrieved = evidence.retrieved
        total_weight = sum(item.weight for item in retrieved)
        progress = (
            sum(item.weight * item.record.observed_progress for item in retrieved) / total_weight
            if total_weight
            else None
        )
        return CandidateActionPrediction(
            intervention_skill=skill,
            probabilities=probabilities,
            predicted_status=self._predicted_status(probabilities),
            predicted_progress=progress,
            utility=probabilities["ACCEPTED"] + self.inconclusive_utility * probabilities["INCONCLUSIVE"],
            history_count=evidence.history_count,
        )

    def predict(self, pack: ActionConditionalEvidencePack) -> ActionConditionalDecision:
        predictions = {skill: self._predict_action(pack, skill) for skill in EXECUTABLE_ACR_SKILLS}
        if any(item.history_count < self.minimum_history for item in predictions.values()):
            selected = None
            reason = "ABSTAIN_COLD_START"
        else:
            left, right = EXECUTABLE_ACR_SKILLS
            if predictions[left].utility == predictions[right].utility:
                selected = None
                reason = "ABSTAIN_TIE"
            else:
                selected = max(EXECUTABLE_ACR_SKILLS, key=lambda skill: predictions[skill].utility)
                reason = "SELECT_HIGHER_UTILITY"
        return ActionConditionalDecision(
            schema_version=1,
            evidence_id=pack.evidence_id,
            episode_id=pack.episode_id,
            selected_skill=selected,
            decision_reason=reason,
            predictions=predictions,
        )
