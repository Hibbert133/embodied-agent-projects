import unittest

from src.probemem_verifier.glm_verifier import HistoryAwareGlmVerifier
from src.probemem_verifier.online_policy import BudgetedVerifierPolicy
from tests.probemem_verifier_helpers import COMP, memory, signature


class TimeoutMessages:
    def create(self, **kwargs):
        raise TimeoutError("synthetic timeout")


class TimeoutClient:
    messages = TimeoutMessages()


class InvalidBlock:
    type = "text"
    text = "{}"


class InvalidResponse:
    content = [InvalidBlock()]


class InvalidMessages:
    def create(self, **kwargs):
        return InvalidResponse()


class InvalidClient:
    messages = InvalidMessages()


class BudgetedPolicyTest(unittest.TestCase):
    def test_clear_case_bypasses_verifier(self) -> None:
        decision = BudgetedVerifierPolicy(mode="budgeted_verifier").decide(
            score=0.30, signature=signature(), memory=memory(), episode_id=21,
        )
        self.assertFalse(decision.override.verifier_called)

    def test_ambiguity_band_calls_verifier_but_low_coverage_cannot_override(self) -> None:
        decision = BudgetedVerifierPolicy(mode="budgeted_verifier").decide(
            score=0.12, signature=signature(), memory=memory(), episode_id=21,
        )
        self.assertTrue(decision.override.verifier_called)
        self.assertFalse(decision.override.override_applied)
        self.assertEqual(decision.override.final_skill, decision.proposal.selected_skill)

    def test_timeout_and_invalid_glm_output_fall_back_to_default(self) -> None:
        for client in (TimeoutClient(), InvalidClient()):
            verifier = HistoryAwareGlmVerifier(client=client, maximum_repairs=0)
            policy = BudgetedVerifierPolicy(mode="budgeted_verifier", verifier=verifier)
            decision = policy.decide(score=0.12, signature=signature(), memory=memory(), episode_id=21)
            self.assertEqual(decision.override.override_reason, "VERIFIER_FAIL_CLOSED")
            self.assertEqual(decision.override.final_skill, decision.proposal.selected_skill)


if __name__ == "__main__":
    unittest.main()
