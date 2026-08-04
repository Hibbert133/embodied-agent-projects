from __future__ import annotations

import unittest

from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionMemory
from src.probemem_verifier.applicability import ApplicabilityThresholds
from src.probemem_verifier.calibrated_override_guard import CalibratedGuardThresholds
from src.probemem_verifier.calibrated_policy import WeightedVerifierPolicy


class CalibratedPolicyTest(unittest.TestCase):
    def test_high_confidence_keeps_frozen_admission_and_default(self):
        policy = WeightedVerifierPolicy(mode="calibrated_v2", stage="test", comparison_seed=1, applicability_thresholds=ApplicabilityThresholds(2, 1, 1, 0.3), guard_thresholds=CalibratedGuardThresholds(0.9, 0.1, 2))
        signature = ProbeRegimeSignature(1, "q", 21, (0, 0, 0, 0.4, 0.5, 0.2, 0.3, 0.4))
        decision = policy.decide(score=0.4, signature=signature, memory=RegimeActionMemory(), episode_id=21)
        self.assertFalse(decision.override.verifier_called)
        self.assertEqual(decision.override.final_skill, decision.proposal.selected_skill)

    def test_calibrated_mode_requires_frozen_thresholds(self):
        with self.assertRaises(ValueError):
            WeightedVerifierPolicy(mode="calibrated_v2", stage="test", comparison_seed=1)


if __name__ == "__main__":
    unittest.main()
