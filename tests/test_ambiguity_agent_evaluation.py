import unittest

from scripts.evaluate_ambiguity_agents import (
    PassivePrediction,
    deterministic_random_request,
    fit_passive_centroid,
    select_gate_threshold,
)


def row(case_id: str, label: str, value: float) -> dict[str, object]:
    return {
        "case_id": case_id,
        "mechanism_class": label,
        "episode_return": value,
        "final_object_goal_distance": value,
        "progress_to_goal": value,
    }


class AmbiguityAgentEvaluationTest(unittest.TestCase):
    def test_passive_model_uses_registered_visible_features(self) -> None:
        rows = [
            row("b1", "stable_bias", 0.0),
            row("b2", "stable_bias", 0.1),
            row("n1", "stochastic_noise", 0.9),
            row("n2", "stochastic_noise", 1.0),
        ]
        model = fit_passive_centroid(rows)
        self.assertEqual(model.predict(row("x", "oracle_not_used", 0.05)).mechanism, "stable_bias")
        self.assertEqual(model.predict(row("y", "oracle_not_used", 0.95)).mechanism, "stochastic_noise")

    def test_gate_threshold_requests_only_ambiguous_error(self) -> None:
        rows = [row("easy", "stable_bias", 0.0), row("hard", "stochastic_noise", 1.0)]
        passive = {
            "easy": PassivePrediction("stable_bias", 0.1),
            "hard": PassivePrediction("stable_bias", 0.9),
        }
        probe = {"easy": "stable_bias", "hard": "stochastic_noise"}
        selected = select_gate_threshold(rows, passive, probe)
        self.assertEqual(selected["tuning_correct"], 2)
        self.assertEqual(selected["tuning_probe_requests"], 1)
        self.assertGreater(selected["threshold"], 0.1)
        self.assertLess(selected["threshold"], 0.9)

    def test_seeded_random_decision_is_reproducible(self) -> None:
        first = deterministic_random_request("case", 0.5, 123)
        self.assertEqual(first, deterministic_random_request("case", 0.5, 123))
        self.assertFalse(deterministic_random_request("case", 0.0, 123))
        self.assertTrue(deterministic_random_request("case", 1.0, 123))


if __name__ == "__main__":
    unittest.main()
