import unittest

from src.probemem_verifier.candidate_verifier import DeterministicBayesianVerifier
from tests.probemem_verifier_helpers import COMP, summary


class CandidateVerifierTest(unittest.TestCase):
    def test_beta_posterior_uses_fractional_inconclusive_weight(self) -> None:
        candidate = DeterministicBayesianVerifier().verify(
            summary(COMP, accepted=3, inconclusive=1, rejected=1)
        )
        self.assertAlmostEqual(candidate.predicted_accept_probability, 4.5 / 7.0)
        self.assertEqual(candidate.predicted_status, "INCONCLUSIVE")
        self.assertEqual(candidate.coverage_count, 5)

    def test_empty_memory_is_neutral_and_not_applicable(self) -> None:
        candidate = DeterministicBayesianVerifier().verify(
            summary(COMP, accepted=0, inconclusive=0, rejected=0)
        )
        self.assertEqual(candidate.predicted_accept_probability, 0.5)
        self.assertFalse(candidate.memory_applicable)


if __name__ == "__main__":
    unittest.main()
