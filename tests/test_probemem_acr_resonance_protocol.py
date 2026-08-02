from __future__ import annotations

import unittest

from src.probemem.resonance_policy import (
    COMPENSATION,
    RETRY,
    decide_second_attempt,
)


class ResonanceSecondAttemptPolicyTests(unittest.TestCase):
    def decide(self, method: str, status: str, remaining: int = 500):
        return decide_second_attempt(
            method=method,
            first_verification_status=status,
            remaining_budget=remaining,
            reserved_second_verification_budget=500,
        )

    def test_accepted_always_stops(self) -> None:
        for method in ("single_retry", "repeat_retry", "switch_compensation", "status_conditioned", "rejection_abstain"):
            with self.subTest(method=method):
                decision = self.decide(method, "ACCEPTED")
                self.assertFalse(decision.request_second_attempt)
                self.assertIsNone(decision.selected_skill)

    def test_fixed_and_status_conditioned_actions(self) -> None:
        self.assertIs(self.decide("repeat_retry", "REJECTED").selected_skill, RETRY)
        self.assertIs(self.decide("switch_compensation", "INCONCLUSIVE").selected_skill, COMPENSATION)
        self.assertIs(self.decide("status_conditioned", "INCONCLUSIVE").selected_skill, RETRY)
        self.assertIs(self.decide("status_conditioned", "REJECTED").selected_skill, COMPENSATION)

    def test_rejection_abstain_stops_after_rejection(self) -> None:
        decision = self.decide("rejection_abstain", "REJECTED")
        self.assertFalse(decision.request_second_attempt)
        self.assertIsNone(decision.selected_skill)

    def test_budget_fails_closed(self) -> None:
        decision = self.decide("repeat_retry", "INCONCLUSIVE", remaining=499)
        self.assertFalse(decision.request_second_attempt)
        self.assertIsNone(decision.selected_skill)
        self.assertEqual(decision.reason, "insufficient_budget_for_second_verification")

    def test_oracle_cannot_enter_agent_policy(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported Agent method"):
            self.decide("oracle_second", "REJECTED")


if __name__ == "__main__":
    unittest.main()
