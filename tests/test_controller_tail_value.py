"""Causal boundary, weighting, group separation and candidate sensitivity tests."""
from copy import deepcopy
from dataclasses import asdict
import unittest
from unittest.mock import patch
import numpy as np
from src.probe.controller_tail_value import (TailEvidence, build_evidence, features,
    feature_map, leave_group_out, remaining_prediction, command)
from src.probe.operator_identification import identity_controller
from src.analysis.controller_tail_dataset import extract, sample_steps, matched_sixteen


def evidence(saved=None, remaining=492):
    obs = np.zeros((9, 39)); obs[:, 0] = np.arange(9)*.001; obs[:, -3:] = (.1, .2, .3)
    return build_evidence("push-v3", obs, np.zeros((8, 4)), [0, 0, 0, 0], saved or identity_controller(), remaining)


def record():
    result = {"stream": 0, "task": "push-v3", "replicate": 0, "method": "NO_PROBE",
              "decisions": [{"controller": identity_controller(), "sequence": 17, "at_host_calls": 0}],
              "trace": [], "outcome": {"success": False, "stopped": True, "total_steps": 20, "deadline_loss": 500}}
    def state(t):
        obs = np.zeros(39); obs[0] = t*.001
        return {"observation": obs.tolist(), "success": False, "terminated": False, "truncated": False}
    for t in range(20):
        result["trace"].append({"before": state(t), "after": state(t+1), "raw_policy": [0, 0, 0, 0],
                                "command": [0, 0, 0, 0], "phase": "POLICY", "decision_sequence": 17})
    return result


class TailValueTests(unittest.TestCase):
    def test_schema_rejects_unknown_and_nested_truth(self):
        value = asdict(evidence())
        for key in ("seed", "operator_id_oracle", "future_outcome", "executed_action_oracle"):
            with self.assertRaises(ValueError):
                TailEvidence.from_dict({**value, key: 1})
        bad = deepcopy(value); bad["observations"] = [[{"seed": 1}]*39]*9
        with self.assertRaises((ValueError, TypeError)):
            TailEvidence.from_dict(bad)

    def test_invalid_budgets_nonfinite_and_boolean_rejected(self):
        for remaining in (0, 493, True, 492.0):
            with self.assertRaises(ValueError):
                evidence(remaining=remaining)
        for field, value in (("raw_policy", [np.nan, 0, 0, 0]), ("commands", [[False]*4]*8)):
            data = asdict(evidence()); data[field] = value
            with self.assertRaises(ValueError):
                TailEvidence.from_dict(data)

    def test_oracle_legacy_and_unknown_controller_rejected(self):
        for source in ("ORACLE_EVALUATOR", "LEGACY_OFFSET"):
            bad = identity_controller(); bad["source"] = source
            with self.assertRaises(ValueError):
                evidence(bad)
        bad = identity_controller(); bad["seed"] = 42
        with self.assertRaises(ValueError):
            command(bad, [0, 0, 0, 0])

    def test_candidate_changes_prediction_and_ablation_cancels(self):
        affine = {"source": "ESTIMATED_AFFINE", "matrix_xy": [[1, 0], [0, 1]], "offset": [.3, -.2, 0, 0]}
        x = np.array([features(evidence()), features(evidence(affine))])
        self.assertEqual(x.shape, (2, 90)); self.assertFalse(np.array_equal(x[0], x[1]))
        coef = np.zeros(91); coef[0] = .5; coef[59] = 1
        z = feature_map(x, "LINEAR_DENSE", np.zeros((90, 2)), np.zeros(2))
        self.assertNotEqual(*remaining_prediction(z, coef, 492))
        rng = np.random.default_rng(1)
        z = feature_map(x, "NO_CONTROLLER_RFF", rng.normal(size=(90, 16)), rng.uniform(0, 6, 16))
        np.testing.assert_array_equal(z[0], z[1])

    def test_holdout_targets_never_enter_coefficients(self):
        z = np.column_stack((np.ones(6), np.arange(6)))
        groups = np.repeat([0, 1, 2], 2); y = np.arange(6)/6; weights = np.ones(6)
        a = leave_group_out(z, y, weights, groups, 1)
        y[groups == 1] = 1000000
        b = leave_group_out(z, y, weights, groups, 1)
        np.testing.assert_array_equal(a, b)
        with self.assertRaises(ValueError):
            leave_group_out(z, y, weights, np.zeros(6), 0)

    def test_ridge_and_clipping_have_analytic_values(self):
        z = np.array([[1, -1], [1, 1], [1, 0]], float)
        y = np.array([0, 1, 999], float)
        coef = leave_group_out(z, y, [1, 1, 1], [0, 0, 1], 1)
        np.testing.assert_allclose(coef, [.5, 1/3])
        np.testing.assert_allclose(remaining_prediction([[1, -9], [1, 9]], coef, [10, 20]), [0, 20])

    @patch("src.analysis.controller_tail_dataset.create_task_policy")
    def test_terminal_supervision_equal_episode_weight_and_no_after_leak(self, policy):
        policy.return_value.get_action.return_value = np.zeros(4)
        source = record(); rows, meta = extract(source, 0)
        self.assertEqual([r["step"] for r in rows], [8, 12, 16, 19])
        self.assertAlmostEqual(sum(r["weight"] for r in rows), 1)
        self.assertTrue(all(r["target"] == 1 for r in rows))
        self.assertEqual(meta["outcome"]["total_steps"], 20)
        source["trace"][-1]["after"]["observation"] = [999]*39
        changed, _ = extract(source, 0)
        for a, b in zip(rows, changed):
            np.testing.assert_array_equal(a["x"], b["x"])
        source["outcome"].update(success=True, stopped=False, deadline_loss=20)
        successes, _ = extract(source, 0)
        self.assertNotEqual(rows[0]["target"], successes[0]["target"])
        np.testing.assert_array_equal(rows[0]["x"], successes[0]["x"])

    @patch("src.analysis.controller_tail_dataset.create_task_policy")
    def test_changed_saved_choice_is_rejected_and_early_end_retained(self, policy):
        policy.return_value.get_action.return_value = np.zeros(4)
        source = record(); source["trace"][12]["decision_sequence"] = 18
        with self.assertRaises(ValueError):
            extract(source, 0)
        source = record(); source["trace"] = source["trace"][:8]
        rows, meta = extract(source, 0)
        self.assertEqual(rows, []); self.assertFalse(meta["eligible"])

    def test_last_nonterminal_is_included_without_duplication(self):
        self.assertEqual(sample_steps(8, 17), [8, 12, 16])
        self.assertEqual(sample_steps(8, 8), [])

    def test_pair_registry_rejects_other_methods(self):
        with self.assertRaises(ValueError):
            matched_sixteen(record(), record())


if __name__ == "__main__":
    unittest.main()
