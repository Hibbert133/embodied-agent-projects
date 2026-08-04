from __future__ import annotations

import unittest

from src.probemem.models import InterventionSkill
from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionExperience, RegimeActionMemory
from src.probemem_verifier.weighted_posterior import QueryConditionedCalibratedVerifier


def record(record_id: str, episode: int, value: float, status: str, skill=InterventionSkill.BOUNDED_PLANAR_COMPENSATION):
    signature = ProbeRegimeSignature(1, f"e-{episode}", episode, (value, 0, value, value, 0.5, 0.2, 0.3, 0.4))
    return RegimeActionExperience(1, record_id, episode, episode + 1, signature, skill, None, None, status, 0.1, 0.2, 10, "run", "manifest", "selected")


class WeightedPosteriorTest(unittest.TestCase):
    def test_nearer_record_has_larger_weight(self):
        memory = RegimeActionMemory((record("near", 1, 0.0, "ACCEPTED"), record("far", 2, 10.0, "REJECTED")))
        query = ProbeRegimeSignature(1, "q", 3, (0.1, 0, 0.1, 0.1, 0.5, 0.2, 0.3, 0.4))
        estimate = QueryConditionedCalibratedVerifier().verify_both(memory, query, episode_id=3)[InterventionSkill.BOUNDED_PLANAR_COMPENSATION.value].global_posterior
        weights = dict(zip(estimate.record_ids, estimate.record_weights))
        self.assertGreater(weights["near"], weights["far"])

    def test_duplicate_record_id_cannot_inflate_ess(self):
        duplicate = record("same", 1, 0.0, "ACCEPTED")
        with self.assertRaises(ValueError):
            RegimeActionMemory((duplicate, duplicate))

    def test_same_mean_can_have_different_uncertainty(self):
        query = ProbeRegimeSignature(1, "q", 10, (0, 0, 0, 0, 0.5, 0.2, 0.3, 0.4))
        prior = QueryConditionedCalibratedVerifier().verify_both(RegimeActionMemory(), query, episode_id=10)[InterventionSkill.BOUNDED_PLANAR_COMPENSATION.value].global_posterior
        records = tuple(record(f"a-{i}", i, 0.0, "ACCEPTED" if i % 2 else "REJECTED") for i in range(1, 9))
        informed = QueryConditionedCalibratedVerifier().verify_both(RegimeActionMemory(records), query, episode_id=10)[InterventionSkill.BOUNDED_PLANAR_COMPENSATION.value].global_posterior
        self.assertAlmostEqual(prior.posterior_mean, informed.posterior_mean)
        self.assertLess(informed.posterior_variance, prior.posterior_variance)

    def test_current_episode_is_not_visible(self):
        memory = RegimeActionMemory((record("current", 3, 0.0, "ACCEPTED"),))
        query = ProbeRegimeSignature(1, "q", 3, (0, 0, 0, 0, 0.5, 0.2, 0.3, 0.4))
        estimate = QueryConditionedCalibratedVerifier().verify_both(memory, query, episode_id=3)[InterventionSkill.BOUNDED_PLANAR_COMPENSATION.value].global_posterior
        self.assertEqual(estimate.record_ids, ())


if __name__ == "__main__":
    unittest.main()
