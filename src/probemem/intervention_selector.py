"""Frozen, Agent-visible intervention selectors for ProbeMem development.

Selectors in this module choose only registered discrete skills. They never
receive evaluator outcomes, perturbation truth, or continuous control access.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.probemem.intervention_utility import (
    INTERVENTION_APPLICABILITY_FEATURES,
    InterventionApplicabilitySignature,
)
from src.probemem.models import InterventionSkill


@dataclass(frozen=True)
class RelativeProbeVariationSelector:
    """Choose retry for low registered-probe relative variation.

    The counterintuitive direction is a frozen development hypothesis. It must
    be tested on fresh cases and must not be interpreted as a mechanism label.
    """

    threshold: float = 2.0

    def select(
        self, signature: InterventionApplicabilitySignature
    ) -> InterventionSkill:
        if self.threshold <= 0.0:
            raise ValueError("selector threshold must be positive")
        feature_index = INTERVENTION_APPLICABILITY_FEATURES.index(
            "probe_relative_bias_std"
        )
        if signature.values[feature_index] <= self.threshold:
            return InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY
        return InterventionSkill.BOUNDED_PLANAR_COMPENSATION
