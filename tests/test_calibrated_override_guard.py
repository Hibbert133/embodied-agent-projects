from __future__ import annotations

from dataclasses import replace
import unittest

from src.probemem_verifier.applicability import ApplicabilityAssessment, MemoryApplicability
from src.probemem_verifier.calibrated_override_guard import CalibratedGuardThresholds, decide_calibrated_override
from src.probemem_verifier.posterior_comparison import PosteriorComparison
from src.probemem_verifier.weighted_posterior import QueryConditionedCandidatePosterior, WeightedPosteriorEstimate


COMP, RETRY = "BOUNDED_PLANAR_COMPENSATION", "INDEPENDENT_STOCHASTIC_RETRY"


def estimate(skill, mean, lower, upper, ess=5):
    return WeightedPosteriorEstimate(skill, "global", 5, 2, mean, 0.01, lower, upper, 0.1, 4, ess, 0.0, (f"{skill}-1",), (1.0,), (f"{skill}-1",), ())


def bundle(skill, mean, lower, upper, ess=5):
    value = estimate(skill, mean, lower, upper, ess)
    return QueryConditionedCandidatePosterior(skill, value, replace(value, scope="recent"))


class CalibratedOverrideGuardTest(unittest.TestCase):
    def setUp(self):
        self.candidates = {COMP: bundle(COMP, 0.2, 0.1, 0.3), RETRY: bundle(RETRY, 0.8, 0.7, 0.9)}
        self.app = ApplicabilityAssessment({COMP: MemoryApplicability(COMP, True, (), (("ok", True),)), RETRY: MemoryApplicability(RETRY, True, (), (("ok", True),))}, RETRY, RETRY, True, "GLOBAL_RECENT_AGREEMENT")
        self.comparison = PosteriorComparison(COMP, RETRY, 0.2, 0.8, 0.6, 0.99, 10000, 1)
        self.thresholds = CalibratedGuardThresholds(0.9, 0.15, 3)

    def test_all_conditions_allow_override(self):
        result = decide_calibrated_override(default_skill=COMP, verifier_called=True, candidates=self.candidates, applicability=self.app, comparison=self.comparison, thresholds=self.thresholds)
        self.assertTrue(result.override_applied)

    def test_low_ess_cannot_override(self):
        candidates = dict(self.candidates)
        candidates[RETRY] = bundle(RETRY, 0.8, 0.7, 0.9, ess=2)
        result = decide_calibrated_override(default_skill=COMP, verifier_called=True, candidates=candidates, applicability=self.app, comparison=self.comparison, thresholds=self.thresholds)
        self.assertIn("ALTERNATIVE_EFFECTIVE_SAMPLE_SIZE", result.override_reason)

    def test_overlapping_intervals_cannot_override(self):
        candidates = dict(self.candidates)
        candidates[RETRY] = bundle(RETRY, 0.8, 0.25, 0.9)
        result = decide_calibrated_override(default_skill=COMP, verifier_called=True, candidates=candidates, applicability=self.app, comparison=self.comparison, thresholds=self.thresholds)
        self.assertIn("CREDIBLE_INTERVAL_SEPARATION", result.override_reason)

    def test_superiority_and_conflict_block(self):
        comparison = replace(self.comparison, probability_alternative_better=0.8)
        app = replace(self.app, recent_preference=COMP, preference_agreement=False, preference_reason="GLOBAL_RECENT_CONFLICT")
        result = decide_calibrated_override(default_skill=COMP, verifier_called=True, candidates=self.candidates, applicability=app, comparison=comparison, thresholds=self.thresholds)
        self.assertIn("SUPERIORITY_PROBABILITY", result.override_reason)
        self.assertIn("GLOBAL_RECENT_AGREEMENT", result.override_reason)


if __name__ == "__main__":
    unittest.main()
