import unittest

from src.probemem_verifier.candidate_verifier import AdmissionMemorySignals, DeterministicBayesianVerifier
from src.probemem_verifier.override_guard import decide_override
from tests.probemem_verifier_helpers import COMP, RETRY, summary


class OverrideGuardTest(unittest.TestCase):
    def _decision(self, comp, retry, signals=None):
        verifier = DeterministicBayesianVerifier()
        summaries = {COMP: comp, RETRY: retry}
        candidates = verifier.verify_both(summaries)
        return decide_override(
            default_skill=COMP, verifier_called=True, candidates=candidates,
            summaries=summaries,
            memory_signals=signals or AdmissionMemorySignals(False, 0.8, False, RETRY, RETRY),
        )

    def test_high_confidence_covered_alternative_can_override(self) -> None:
        decision = self._decision(
            summary(COMP, accepted=0, inconclusive=0, rejected=4),
            summary(RETRY, accepted=4, inconclusive=0, rejected=0),
        )
        self.assertTrue(decision.override_applied)
        self.assertEqual(decision.final_skill, RETRY)

    def test_coverage_contradiction_margin_and_conflict_block(self) -> None:
        insufficient = self._decision(
            summary(COMP, accepted=0, inconclusive=0, rejected=2),
            summary(RETRY, accepted=2, inconclusive=0, rejected=0),
        )
        self.assertIn("INSUFFICIENT_ALTERNATIVE_COVERAGE", insufficient.override_reason)

        contradicted = self._decision(
            summary(COMP, accepted=0, inconclusive=0, rejected=5),
            summary(RETRY, accepted=4, inconclusive=0, rejected=2),
        )
        self.assertIn("ALTERNATIVE_CONTRADICTION_TOO_HIGH", contradicted.override_reason)

        conflict = self._decision(
            summary(COMP, accepted=0, inconclusive=4, rejected=1),
            summary(RETRY, accepted=4, inconclusive=1, rejected=0),
            AdmissionMemorySignals(True, 0.8, False, RETRY, COMP),
        )
        self.assertIn("RECENT_GLOBAL_PREFERENCE_NOT_ALIGNED", conflict.override_reason)

    def test_probability_margin_and_confidence_block(self) -> None:
        close = self._decision(
            summary(COMP, accepted=4, inconclusive=4, rejected=2),
            summary(RETRY, accepted=5, inconclusive=3, rejected=2),
        )
        self.assertIn("PROBABILITY_MARGIN_TOO_SMALL", close.override_reason)
        self.assertIn("VERIFIER_CONFIDENCE_TOO_LOW", close.override_reason)


if __name__ == "__main__":
    unittest.main()
