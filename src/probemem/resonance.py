"""Host-derived prediction/outcome resonance for ProbeMem-ACR."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from src.probemem.action_memory import OUTCOME_STATUSES
from src.probemem.models import InterventionSkill


class ResonanceClass(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNRESOLVED = "UNRESOLVED"
    CONTRADICTED = "CONTRADICTED"


_RESONANCE_MATRIX = {
    ("ACCEPTED", "ACCEPTED"): ResonanceClass.SUPPORTED,
    ("ACCEPTED", "INCONCLUSIVE"): ResonanceClass.UNRESOLVED,
    ("ACCEPTED", "REJECTED"): ResonanceClass.CONTRADICTED,
    ("INCONCLUSIVE", "ACCEPTED"): ResonanceClass.UNRESOLVED,
    ("INCONCLUSIVE", "INCONCLUSIVE"): ResonanceClass.SUPPORTED,
    ("INCONCLUSIVE", "REJECTED"): ResonanceClass.UNRESOLVED,
    ("REJECTED", "ACCEPTED"): ResonanceClass.CONTRADICTED,
    ("REJECTED", "INCONCLUSIVE"): ResonanceClass.UNRESOLVED,
    ("REJECTED", "REJECTED"): ResonanceClass.SUPPORTED,
}


def classify_resonance(predicted_status: str, observed_status: str) -> ResonanceClass:
    try:
        return _RESONANCE_MATRIX[(predicted_status, observed_status)]
    except KeyError as exc:
        raise ValueError("resonance requires registered outcome statuses") from exc


@dataclass(frozen=True)
class ResonanceRecord:
    schema_version: int
    prediction_id: str
    episode_id: int
    selected_skill: InterventionSkill
    predicted_status: str
    observed_status: str
    predicted_progress: float | None
    observed_progress: float
    status_match: bool
    progress_error: float | None
    observed_class_probability: float
    resonance_class: ResonanceClass

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not self.prediction_id.strip() or self.episode_id <= 0:
            raise ValueError("invalid resonance identity or schema")
        if self.predicted_status not in OUTCOME_STATUSES or self.observed_status not in OUTCOME_STATUSES:
            raise ValueError("invalid resonance status")
        if self.status_match != (self.predicted_status == self.observed_status):
            raise ValueError("status_match must be host-derived")
        if not 0.0 <= self.observed_class_probability <= 1.0:
            raise ValueError("observed-class probability must be in [0, 1]")
        expected_error = (
            None if self.predicted_progress is None else abs(self.predicted_progress - self.observed_progress)
        )
        if expected_error is None:
            if self.progress_error is not None:
                raise ValueError("progress error must be null without a prediction")
        elif self.progress_error is None or abs(expected_error - self.progress_error) > 1e-12:
            raise ValueError("progress error must be host-derived")
        if self.resonance_class is not classify_resonance(self.predicted_status, self.observed_status):
            raise ValueError("resonance class must match the frozen matrix")
        if not math.isfinite(self.observed_progress):
            raise ValueError("observed progress must be finite")

    @classmethod
    def create(
        cls,
        *,
        prediction_id: str,
        episode_id: int,
        selected_skill: InterventionSkill,
        predicted_status: str,
        probabilities: Mapping[str, float],
        observed_status: str,
        predicted_progress: float | None,
        observed_progress: float,
    ) -> "ResonanceRecord":
        if set(probabilities) != set(OUTCOME_STATUSES):
            raise ValueError("resonance requires all outcome probabilities")
        return cls(
            schema_version=1,
            prediction_id=prediction_id,
            episode_id=episode_id,
            selected_skill=selected_skill,
            predicted_status=predicted_status,
            observed_status=observed_status,
            predicted_progress=predicted_progress,
            observed_progress=observed_progress,
            status_match=predicted_status == observed_status,
            progress_error=(
                None if predicted_progress is None else abs(predicted_progress - observed_progress)
            ),
            observed_class_probability=float(probabilities[observed_status]),
            resonance_class=classify_resonance(predicted_status, observed_status),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "prediction_id": self.prediction_id,
            "episode_id": self.episode_id,
            "selected_skill": self.selected_skill.value,
            "predicted_status": self.predicted_status,
            "observed_status": self.observed_status,
            "predicted_progress": self.predicted_progress,
            "observed_progress": self.observed_progress,
            "status_match": self.status_match,
            "progress_error": self.progress_error,
            "observed_class_probability": self.observed_class_probability,
            "resonance_class": self.resonance_class.value,
        }
