import copy
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from src.probe.continuous import StepObservation
from src.probe.movement_history_reference_v1 import (
    MovementHistoryV1, MovementTransitionV1, estimate_movement, operator_samples,
)
from tests.test_operator_identification import model


def observed(position, *, success=False):
    return StepObservation(tuple(position), False, False, success)


def synthetic_history(count=12, *, success=False, fixed=False):
    """Algebraic AR2 fixture, not a simulator or scientific observation."""
    position = np.zeros(39)
    position[:3] = [.1, .6, .3]
    velocity = np.array([.001, -.002, .0005])
    previous = position.copy()
    previous[:3] -= velocity
    prior = previous.copy()
    prior[:3] -= [.003, -.001, .0002]
    context = tuple(observed(p) for p in (prior, previous, position))
    rows = []
    actual = np.array([[.8, .15, .06], [-.1, 1.1, -.03]])
    program = ((.3, 0.), (0., .3), (-.3, .1), (.1, -.3))
    for index in range(count):
        before = observed(position)
        xy = (.2, .1) if fixed else program[index % len(program)]
        command = (*xy, .12, -1.)
        effective = np.clip(actual @ np.array([*xy, 1.]), -1, 1)
        velocity[:2] = .5*velocity[:2]+np.array([.006, .008])*effective
        position[:3] += velocity
        rows.append(MovementTransitionV1(17+index, command, before,
                                        observed(position, success=success and index == count-1)))
    return MovementHistoryV1("push-v3", 16, 16+count, context, tuple(rows)), actual


class MovementHistoryReferenceTest(unittest.TestCase):
    def test_all_responses_use_real_pre_movement_context_including_first_two(self):
        history, _ = synthetic_history()
        samples = operator_samples(history)
        self.assertEqual(len(samples), 12)
        self.assertEqual((samples[0].step, samples[-1].step), (17, 28))
        np.testing.assert_allclose(samples[0].query.prior_displacement, [.003, -.001, .0002], atol=1e-15)
        np.testing.assert_allclose(samples[0].query.last_displacement, [.001, -.002, .0005], atol=1e-15)
        self.assertEqual(samples[0].query.command[2:], (.12, -1.))
        self.assertEqual(samples[1].query.prior_displacement, samples[0].query.last_displacement)
        np.testing.assert_allclose(samples[1].query.last_displacement[:2], samples[0].displacement)

    def test_existing_arx_recovers_synthetic_affine_without_oracle_argument(self):
        history, actual = synthetic_history()
        result = estimate_movement(model("LINEAR_ARX"), history)
        self.assertEqual(result["status"], "VALID_WORKING_ESTIMATE")
        fitted = result["fit"]
        np.testing.assert_allclose(np.column_stack((fitted["matrix_xy"], fitted["bias_xy"])), actual, atol=1e-11)
        self.assertFalse(result["physical_response_qualified"])
        self.assertFalse(result["task_utility_demonstrated"])
        self.assertEqual(result["movement_responses"], 12)
        self.assertEqual(result["optimizer_nfev"], sum(t["nfev"] for t in fitted["optimizer_trials"]))
        with self.assertRaises(TypeError):
            estimate_movement(model("LINEAR_ARX"), history, true_operator=actual)

    def test_ended_and_zero_movement_do_not_fit_or_invent_task_actions(self):
        with patch("src.probe.movement_history_reference_v1.infer_operator", side_effect=AssertionError("must not fit")):
            ended, _ = synthetic_history(success=True)
            empty, _ = synthetic_history(count=0)
            for history, status in ((ended, "ENDED_NO_UPDATE"), (empty, "NO_MOVEMENT_EVIDENCE")):
                result = estimate_movement(model("LINEAR_ARX"), history)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["fit_attempts"], 0)
                self.assertIsNone(result["fit"])
                self.assertNotIn("controller", result)

    def test_weak_and_short_history_preserve_invalid_estimates_without_fallback(self):
        for history, reason in ((synthetic_history(fixed=True)[0], "MISSING_OR_ILL_CONDITIONED_INPUT_SUPPORT"),
                                (synthetic_history(count=5)[0], "INSUFFICIENT_SAMPLES")):
            result = estimate_movement(model("LINEAR_ARX"), history)
            self.assertEqual(result["status"], "INVALID_ESTIMATE")
            self.assertEqual(result["fit"]["reason"], reason)
            self.assertNotIn("controller", result)

    def test_unknown_oracle_future_and_nested_status_fields_are_rejected(self):
        source = synthetic_history()[0].to_dict()
        for where, key in (("top", "fault_oracle"), ("context", "seed"),
                           ("transition", "executed_action_oracle"), ("after", "future_success")):
            bad = copy.deepcopy(source)
            target = {"top": bad, "context": bad["context"][0], "transition": bad["transitions"][0],
                      "after": bad["transitions"][0]["after"]}[where]
            target[key] = 1
            with self.subTest(where=where), self.assertRaises(ValueError):
                MovementHistoryV1.from_mapping(bad)

    def test_gaps_duplicates_reordering_and_changed_observation_fail(self):
        history, _ = synthetic_history()
        for rows in (history.transitions[1:], history.transitions[:1]+history.transitions,
                     tuple(reversed(history.transitions))):
            with self.assertRaises(ValueError):
                replace(history, transitions=rows, decision_step=history.start_step+len(rows))
        changed = replace(history.transitions[2], before=history.transitions[0].before)
        with self.assertRaises(ValueError):
            replace(history, transitions=history.transitions[:2]+(changed,)+history.transitions[3:])

    def test_future_cutoff_missing_context_and_budget_overrun_fail(self):
        history, _ = synthetic_history()
        for changes in ({"decision_step": 29}, {"decision_step": True}, {"context": history.context[1:]},
                        {"start_step": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(history, **changes)
        with self.assertRaises(ValueError):
            synthetic_history(count=65)
        with self.assertRaises(ValueError):
            replace(history.transitions[0], completed_step=401)

    def test_no_transition_after_termination_or_nonfinite_commands(self):
        history, _ = synthetic_history()
        for changes in ({"before": replace(history.transitions[0].before, success=True)},
                        {"command": (True, 0., 0., 0.)}, {"command": (float("nan"), 0., 0., 0.)},
                        {"command": (1.001, 0., 0., 0.)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(history.transitions[0], **changes)

    def test_roundtrip_and_mutable_inputs_cannot_rewrite_saved_snapshot(self):
        history, _ = synthetic_history()
        payload = history.to_dict()
        rebuilt = MovementHistoryV1.from_mapping(payload)
        self.assertEqual(history.sha256, rebuilt.sha256)
        payload["transitions"][0]["command"] = (0.,)*4
        self.assertEqual(history.sha256, rebuilt.sha256)
        with self.assertRaises(ValueError):
            operator_samples(payload)

    def test_wrong_model_scope_and_poisoned_model_rejected_even_on_early_end(self):
        history, _ = synthetic_history(success=True)
        for key, value in (("true_operator", []), ("physical_response_qualified", True),
                           ("mean", [0.]*9), ("ridge", .01), ("feature_count", True)):
            bad = copy.deepcopy(model("LINEAR_ARX")); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                estimate_movement(bad, history)


if __name__ == "__main__":
    unittest.main()
