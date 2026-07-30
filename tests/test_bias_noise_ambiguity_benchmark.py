import unittest

from scripts.build_bias_noise_ambiguity_benchmark import (
    PASSIVE_MATCH_FEATURES,
    PassiveFailureCase,
    classify_probe,
    match_passive_failures,
)


def case(case_id: str, mechanism: str, values: tuple[float, float, float]) -> PassiveFailureCase:
    return PassiveFailureCase(
        case_id=case_id,
        condition_id=case_id,
        seed=1,
        mechanism_class=mechanism,
        episode_return=values[0],
        final_object_goal_distance=values[1],
        progress_to_goal=values[2],
        perturbation_parameters={},
    )


class BiasNoiseAmbiguityBenchmarkTest(unittest.TestCase):
    def test_global_matching_avoids_greedy_conflict(self) -> None:
        biases = [
            case("bias_a", "stable_bias", (0.0, 0.0, 0.0)),
            case("bias_b", "stable_bias", (3.0, 3.0, 3.0)),
        ]
        noises = [
            case("noise_a", "stochastic_noise", (1.0, 1.0, 1.0)),
            case("noise_b", "stochastic_noise", (0.1, 0.1, 0.1)),
        ]
        pairs = match_passive_failures(biases, noises)
        self.assertEqual(
            [(pair.noise_case.case_id, pair.bias_case.case_id) for pair in pairs],
            [("noise_a", "bias_b"), ("noise_b", "bias_a")],
        )

    def test_tie_break_is_deterministic(self) -> None:
        biases = [
            case("bias_b", "stable_bias", (0.0, 0.0, 0.0)),
            case("bias_a", "stable_bias", (0.0, 0.0, 0.0)),
        ]
        noise = [case("noise", "stochastic_noise", (1.0, 1.0, 1.0))]
        self.assertEqual(match_passive_failures(biases, noise)[0].bias_case.case_id, "bias_a")

    def test_matching_rejects_probe_or_oracle_features(self) -> None:
        bias = [case("bias", "stable_bias", (0.0, 0.0, 0.0))]
        noise = [case("noise", "stochastic_noise", (1.0, 1.0, 1.0))]
        with self.assertRaisesRegex(ValueError, "registered passive feature set"):
            match_passive_failures(
                bias,
                noise,
                features=(*PASSIVE_MATCH_FEATURES, "estimated_bias_std_norm"),
            )

    def test_frozen_threshold_semantics(self) -> None:
        self.assertEqual(classify_probe(0.1, 0.1), "stable_bias")
        self.assertEqual(classify_probe(0.100001, 0.1), "stochastic_noise")
        with self.assertRaisesRegex(ValueError, "non-negative"):
            classify_probe(0.0, -0.1)


if __name__ == "__main__":
    unittest.main()
