"""Frozen host decision for persistent-regime feasibility."""

from __future__ import annotations

from typing import Any, Mapping

from src.probemem.models import InterventionSkill
from src.reasoning.evidence import validate_no_oracle_evidence


FROZEN_CONSISTENCY_THRESHOLD = 0.11560838098372882


def select_from_persistent_probe(probe_context: Mapping[str, Any]) -> tuple[InterventionSkill, float]:
    validate_no_oracle_evidence(probe_context)
    try:
        score = float(probe_context["consistency"]["estimated_bias_std_norm"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("registered repeated probe lacks consistency score") from exc
    selected = (
        InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY
        if score > FROZEN_CONSISTENCY_THRESHOLD
        else InterventionSkill.BOUNDED_PLANAR_COMPENSATION
    )
    return selected, score
