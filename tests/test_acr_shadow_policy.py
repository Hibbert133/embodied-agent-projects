from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from src.probemem.acr_shadow_policy import AcrGlmShadowPolicy, AcrShadowDecision, CANDIDATES
from scripts.run_acr_glm_shadow_smoke import build_shadow_evidence


def _body() -> dict:
    return {
        "evidence_sufficient": True,
        "action_predictions": {
            CANDIDATES[0]: {"predicted_status": "INCONCLUSIVE", "accept_probability": 0.4, "confidence": 0.5},
            CANDIDATES[1]: {"predicted_status": "ACCEPTED", "accept_probability": 0.7, "confidence": 0.6},
        },
        "selected_decision": "REPEAT_STOCHASTIC_RETRY",
        "reason": "Retry has the higher bounded estimate.",
    }


class _Messages:
    def __init__(self, text: str) -> None:
        self.text = text

    def create(self, **_: object) -> object:
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)], usage=SimpleNamespace(input_tokens=10, output_tokens=20))


class AcrShadowPolicyTests(unittest.TestCase):
    def test_requires_predictions_for_both_candidates(self) -> None:
        body = _body()
        del body["action_predictions"][CANDIDATES[0]]
        with self.assertRaises(ValueError):
            AcrShadowDecision.from_mapping(body)

    def test_valid_shadow_decision_is_never_an_execution_contract(self) -> None:
        decision = AcrShadowDecision.from_mapping(_body())
        self.assertEqual(decision.selected_decision, "REPEAT_STOCHASTIC_RETRY")
        self.assertFalse(hasattr(decision, "continuous_action"))

    def test_oracle_payload_fails_before_api_call(self) -> None:
        policy = AcrGlmShadowPolicy(client=SimpleNamespace(messages=_Messages(json.dumps(_body()))))
        with self.assertRaises(ValueError):
            policy.decide({"evidence_id": "e1", "perturbation_type": "noise"})

    def test_invalid_output_repairs_then_fails_closed(self) -> None:
        policy = AcrGlmShadowPolicy(client=SimpleNamespace(messages=_Messages("not json")))
        decision, audit = policy.decide({"evidence_id": "e1", "first_verification_status": "REJECTED"})
        self.assertEqual(decision.selected_decision, "ABSTAIN")
        self.assertEqual(audit["status"], "fail_closed")
        self.assertEqual(len(audit["attempts"]), 2)

    def test_runner_allowlist_drops_evaluator_outcome(self) -> None:
        evidence = build_shadow_evidence({
            "episode_id": "3", "realization_index": "2",
            "first_verification_status": "INCONCLUSIVE",
            "first_observed_progress": "0.1",
            "first_final_object_goal_distance": "0.2",
            "paired_retry_status_evaluator_only": "ACCEPTED",
            "paired_retry_accepted_evaluator_only": "True",
        }, remaining_budget=500)
        self.assertNotIn("paired_retry_status_evaluator_only", evidence)
        self.assertNotIn("paired_retry_accepted_evaluator_only", evidence)


if __name__ == "__main__":
    unittest.main()
