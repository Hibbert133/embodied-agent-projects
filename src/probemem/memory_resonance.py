"""Prediction-outcome resonance for online action memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from src.probemem.models import InterventionSkill
from src.probemem.regime_memory import ACTION_SKILLS, OUTCOMES
from src.probemem.resonance import classify_resonance


@dataclass(frozen=True)
class ActionResonanceRecord:
    episode_id: int
    selected_skill: InterventionSkill
    predicted_status: str
    observed_status: str
    predicted_accept_probability: float
    observed_progress: float
    observed_class_probability: float
    brier_score: float
    resonance_class: str
    supporting_memory_ids: tuple[str, ...]
    contradicting_memory_ids: tuple[str, ...]

    @classmethod
    def create(
        cls, *, episode_id: int, selected_skill: InterventionSkill,
        predicted_status: str, probabilities: Mapping[str, float], observed_status: str,
        observed_progress: float, supporting_memory_ids: tuple[str, ...] = (),
        contradicting_memory_ids: tuple[str, ...] = (),
    ) -> "ActionResonanceRecord":
        if selected_skill not in ACTION_SKILLS or set(probabilities) != set(OUTCOMES):
            raise ValueError("resonance requires a registered skill and complete outcome distribution")
        if abs(sum(float(value) for value in probabilities.values()) - 1.0) > 1e-9:
            raise ValueError("outcome probabilities must sum to one")
        target = {status: float(status == observed_status) for status in OUTCOMES}
        brier = sum((float(probabilities[status]) - target[status]) ** 2 for status in OUTCOMES)
        return cls(
            episode_id=episode_id, selected_skill=selected_skill,
            predicted_status=predicted_status, observed_status=observed_status,
            predicted_accept_probability=float(probabilities["ACCEPTED"]),
            observed_progress=float(observed_progress), observed_class_probability=float(probabilities[observed_status]),
            brier_score=brier, resonance_class=classify_resonance(predicted_status, observed_status).value,
            supporting_memory_ids=supporting_memory_ids, contradicting_memory_ids=contradicting_memory_ids,
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["selected_skill"] = self.selected_skill.value
        return value
