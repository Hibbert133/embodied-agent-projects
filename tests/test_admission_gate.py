import unittest

from src.probemem_verifier.admission import assess_admission, should_call_verifier


class AdmissionGateTest(unittest.TestCase):
    def test_high_confidence_without_memory_signal_bypasses(self) -> None:
        self.assertFalse(should_call_verifier(0.051, False, 0.8))

    def test_ambiguity_band_is_inclusive(self) -> None:
        decision = assess_admission(0.05, False, 0.0)
        self.assertTrue(decision.verifier_called)
        self.assertIn("WITHIN_AMBIGUITY_BAND", decision.reasons)

    def test_conflict_and_recent_contradiction_require_coverage(self) -> None:
        self.assertFalse(should_call_verifier(0.2, True, 0.0, recent_contradiction=True))
        decision = assess_admission(0.2, True, 0.5, recent_contradiction=True)
        self.assertEqual(
            decision.reasons,
            ("GLOBAL_RECENT_MEMORY_CONFLICT", "RECENT_SIMILAR_CONTRADICTION"),
        )


if __name__ == "__main__":
    unittest.main()
