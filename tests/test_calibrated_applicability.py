from __future__ import annotations

import unittest

from src.probemem.models import InterventionSkill
from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionExperience, RegimeActionMemory
from src.probemem_verifier.applicability import ApplicabilityThresholds, assess_applicability
from src.probemem_verifier.weighted_posterior import QueryConditionedCalibratedVerifier


class CalibratedApplicabilityTest(unittest.TestCase):
    def test_far_records_cannot_be_applicable(self):
        records = []
        for i, skill in enumerate((InterventionSkill.BOUNDED_PLANAR_COMPENSATION, InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY) * 3, 1):
            signature = ProbeRegimeSignature(1, f"e{i}", i, (100 + i, 0, 100 + i, 100 + i, 0.5, 0.2, 0.3, 0.4))
            records.append(RegimeActionExperience(1, f"r{i}", i, i + 1, signature, skill, None, None, "ACCEPTED", 0.1, 0.2, 10, "run", "manifest", "selected"))
        query = ProbeRegimeSignature(1, "q", 10, (0, 0, 0, 0, 0.5, 0.2, 0.3, 0.4))
        candidates = QueryConditionedCalibratedVerifier().verify_both(RegimeActionMemory(records), query, episode_id=10)
        result = assess_applicability(candidates, ApplicabilityThresholds(2, 0.5, 1, 0.3))
        self.assertTrue(all(not item.applicable for item in result.candidates.values()))
        self.assertTrue(any("OUTSIDE_LOCAL_COVERAGE" in item.rejection_reasons for item in result.candidates.values()))


if __name__ == "__main__":
    unittest.main()
