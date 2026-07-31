"""Freeze checks for the ProbeMem noise selector validation."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_probemem_paired_utility import validate_stopping_rule
from src.probemem.intervention_selector import RelativeProbeVariationSelector
from src.probemem.intervention_utility import (
    INTERVENTION_APPLICABILITY_FEATURES,
    InterventionApplicabilitySignature,
)
from src.probemem.models import InterventionSkill


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/probemem_v2/noise_intervention_selector_validation_v1.json"


def _signature(relative_std: float) -> InterventionApplicabilitySignature:
    values = [0.1] * len(INTERVENTION_APPLICABILITY_FEATURES)
    values[INTERVENTION_APPLICABILITY_FEATURES.index("probe_relative_bias_std")] = (
        relative_std
    )
    return InterventionApplicabilitySignature(
        schema_version=1,
        evidence_id="evidence_test",
        episode_id=1,
        values=tuple(values),
    )


class ProbeMemNoiseSelectorProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_selector_direction_and_boundary_are_frozen(self) -> None:
        selector = RelativeProbeVariationSelector(
            threshold=float(self.config["selector"]["threshold"])
        )
        self.assertEqual(
            selector.select(_signature(2.0)),
            InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY,
        )
        self.assertEqual(
            selector.select(_signature(2.0001)),
            InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
        )

    def test_validation_uses_fresh_reserved_stream(self) -> None:
        self.assertEqual(self.config["seed_range"], [840, 899])
        self.assertEqual(self.config["heldout_seed_range"], [900, 979])
        self.assertEqual(self.config["condition_cycle"], ["fault_05"])
        self.assertEqual(validate_stopping_rule(self.config), 20)

    def test_scope_forbids_api_memory_principles_and_heldout_claim(self) -> None:
        scope = self.config["scope"]
        self.assertEqual(scope["api_calls"], 0)
        self.assertFalse(scope["actionable_memory_write"])
        self.assertFalse(scope["principle_generation"])
        self.assertFalse(scope["heldout_claim"])


if __name__ == "__main__":
    unittest.main()
