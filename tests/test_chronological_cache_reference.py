import copy
from dataclasses import asdict
import unittest
import numpy as np
from tests.test_cold_cache_prediction import fixture
from src.probe.cold_start_response import ColdPrefix
from src.probe.cold_cache_prediction import PredictionQuery, response
from src.probe.chronological_cache_reference import (METHODS, BLOCK8, BALANCED8, VerifiedPoint, accepted_cache,
    initial_choice, check_choice, budget_valid, ivr_reference)
from src.rollout.chronological_faults import (population, deterministic_action, ChronologicalNoise, apply_fault)


def visible_prefix(commands):
    model, parameters, query, _ = fixture()
    mu = response(model, PredictionQuery(query.task, query.initial_observation, commands, True), parameters)[0].reshape(-1, 2)
    states = []; current = np.array(query.initial_observation)
    for row in mu:
        current = current.copy(); current[:2] += row; states.append(tuple(current))
    return model, ColdPrefix(query.task, query.initial_observation, commands, tuple(states), True)


def cache_fixture():
    model, prefix = visible_prefix(BLOCK8)
    fit = {"valid": True, "matrix_xy": np.eye(2).tolist(), "bias_xy": [0., 0.]}
    return model, accepted_cache(fit, prefix, prefix.task, 0, success=True, joint_model=model)


class ChronologicalCacheTest(unittest.TestCase):
    def test_initial_routes_and_periodic_counter_are_explicit(self):
        _, cache = cache_fixture()
        for method in METHODS:
            action = initial_choice(method, None, 0)
            self.assertEqual(action, {"NO_PROBE": "RUN_IDENTITY", "ALWAYS16_OLD": "PROBE16", "PASSIVE_RECENT8": "PASSIVE8"}.get(method, "PROBE8"))
        self.assertEqual(initial_choice("PERIODIC4", cache, 4), "PROBE8")
        self.assertEqual(initial_choice("PERIODIC4", cache, 3), "RUN_CACHED")
        self.assertEqual(initial_choice("UNCERTAINTY4", cache, 1), "CHECK4")

    def test_future_cache_rejected_and_failure_never_writes_cache(self):
        _, cache = cache_fixture()
        with self.assertRaises(ValueError): initial_choice("STALE", cache, 0)
        self.assertIsNone(accepted_cache(None, None, "push-v3", 1, success=False))
        with self.assertRaises(ValueError): accepted_cache({"valid": False}, None, "push-v3", 1, success=True)

    def test_nested_hidden_cache_fields_are_rejected(self):
        _, cache = cache_fixture(); value = asdict(cache)
        for key in ("seed", "fault_oracle", "future_success"):
            with self.assertRaises(ValueError): VerifiedPoint.from_dict({**value, key: 0})
        hidden = copy.deepcopy(value); hidden["belief"]["schedule_oracle"] = "GRADUAL"
        with self.assertRaises(ValueError): VerifiedPoint.from_dict(hidden)

    def test_unchanged_synthetic_response_reuses_saved_cache(self):
        model, cache = cache_fixture(); _, prefix = visible_prefix(BLOCK8[:4])
        for method in ("PLUGIN4", "UNCERTAINTY4", "CUSUM4"):
            self.assertEqual(check_choice(method, model, prefix, cache, 0., (0., 0., 0., 0.))["action"], "RUN_CACHED")

    def test_observed_large_change_requests_actual_remaining_probe(self):
        model, cache = cache_fixture(); _, prefix = visible_prefix(BLOCK8[:4])
        states = [tuple(v+.01*(i+1) if j < 2 else v for j, v in enumerate(row)) for i, row in enumerate(prefix.observations)]
        changed = ColdPrefix(prefix.task, prefix.initial_observation, prefix.commands, tuple(states), True)
        for method in ("PLUGIN4", "UNCERTAINTY4", "CUSUM4"):
            self.assertEqual(check_choice(method, model, changed, cache, 0., (0., 0., 0., 0.))["action"], "REFRESH8")

    def test_incomplete_or_wrong_program_is_rejected(self):
        model, cache = cache_fixture(); _, balanced = visible_prefix(BALANCED8[:4])
        with self.assertRaises(ValueError): check_choice("PLUGIN4", model, balanced, cache, 0., (0.,)*4)
        self.assertEqual(check_choice("BALANCED4", model, balanced, cache, 0., (0.,)*4)["action"], "RUN_CACHED")

    def test_task_information_reference_has_nested_nonnegative_value(self):
        model, cache = cache_fixture(); _, prefix = visible_prefix(BLOCK8[:4])
        value = ivr_reference(model, prefix, cache, (.3, .4, 0., 0.))
        self.assertGreaterEqual(value["relative_variance_reduction"], 0)
        self.assertLessEqual(value["expected_variance_after8"], value["variance_after4"]+1e-12)

    def test_budget_is_checked_before_requesting_physical_steps(self):
        self.assertFalse(budget_valid(35, 4)); self.assertTrue(budget_valid(36, 4))
        with self.assertRaises(ValueError): budget_valid(500, -1)


class ChronologicalFaultTest(unittest.TestCase):
    def test_main_population_is_complete_fresh_and_balanced(self):
        rows = population("MAIN"); self.assertEqual(len(rows), 36)
        cases = [c for row in rows for c in row["cases"]]
        self.assertEqual({c["seed"] for c in cases}, set(range(17000, 17432)))
        self.assertEqual(len(cases), 432)
        for task in ("push-v3", "reach-v3", "door-open-v3"):
            self.assertEqual(sum(c["task"] == task for c in cases), 144)
        for row in rows:
            weights = [c["fraction_oracle"] for c in row["cases"]]
            if row["schedule_oracle"] == "UNCHANGED": self.assertEqual(weights, [0.]*12)
            if row["schedule_oracle"] == "ABRUPT": self.assertEqual(weights, [0.]*6+[1.]*6)
            if row["schedule_oracle"] == "GRADUAL": self.assertTrue(all(a <= b for a, b in zip(weights, weights[1:])))

    def test_column_change_is_invisible_to_block_four_but_not_balanced_four(self):
        for row in population("MAIN"):
            if row["family_oracle"] != "COLUMN_Y": continue
            a, b = row["endpoint_states_oracle"]
            for command in BLOCK8[:4]: np.testing.assert_array_equal(deterministic_action(command, a), deterministic_action(command, b))
            self.assertTrue(any(not np.array_equal(deterministic_action(command, a), deterministic_action(command, b)) for command in BALANCED8[:4]))

    def test_noise_is_shared_by_clock_and_never_rewinds(self):
        a, b = ChronologicalNoise(17000), ChronologicalNoise(17000)
        self.assertEqual(a.commitment_oracle, b.commitment_oracle)
        for _ in range(500): np.testing.assert_array_equal(a.consume(), b.consume())
        self.assertEqual(a.past_hash(), a.commitment_oracle["full_sha256"])
        self.assertEqual(a.cursor, 500)
        with self.assertRaises(ValueError): a.consume()

    def test_invalid_action_does_not_spend_private_noise(self):
        tape = ChronologicalNoise(17000); fault = population("SMOKE")[0]["cases"][0]["fault_oracle"]
        with self.assertRaises(ValueError): apply_fault((2., 0., 0., 0.), fault, tape)
        self.assertEqual(tape.cursor, 0)
        bad = {**fault, "matrix_xy": [[float('nan'), 0.], [0., 1.]]}
        with self.assertRaises(ValueError): apply_fault((0.,)*4, bad, tape)
        self.assertEqual(tape.cursor, 0)

    def test_deadzone_mapping_is_distinct_and_keeps_other_actuators(self):
        fault = {"matrix_xy": np.eye(2).tolist(), "bias_xy": [0., 0.], "deadzone_xy": [.2, .1]}
        np.testing.assert_allclose(deterministic_action((.1, -.55, .3, .7), fault), (0., -.5, .3, .7), atol=1e-7)


if __name__ == "__main__": unittest.main()
