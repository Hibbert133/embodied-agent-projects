from __future__ import annotations

import unittest

from src.probemem_verifier.posterior_comparison import compare_posteriors, derive_comparison_seed
from src.probemem_verifier.weighted_posterior import WeightedPosteriorEstimate


def estimate(skill, alpha, beta):
    mean = alpha / (alpha + beta)
    return WeightedPosteriorEstimate(skill, "global", alpha, beta, mean, 0.01, 0.1, 0.9, None, 0, 0, 0, (), (), (), ())


class PosteriorComparisonTest(unittest.TestCase):
    def test_sampling_is_reproducible(self):
        seed = derive_comparison_seed(19804, stage="calibration", method="v2", episode_id=21)
        left = estimate("BOUNDED_PLANAR_COMPENSATION", 2, 5)
        right = estimate("INDEPENDENT_STOCHASTIC_RETRY", 5, 2)
        first = compare_posteriors(left, right, sampling_seed=seed)
        self.assertEqual(first, compare_posteriors(left, right, sampling_seed=seed))
        self.assertGreater(first.probability_alternative_better, 0.8)


if __name__ == "__main__":
    unittest.main()
