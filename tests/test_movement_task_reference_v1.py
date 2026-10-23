"""Synthetic callback tests; no simulator, scientific seed, or API execution."""
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter_ns
import unittest
from unittest.mock import patch

import numpy as np

from src.analysis.movement_model_source_v1 import load_bank
from src.probe.continuous import StepObservation
from src.probe.movement_history_reference_v1 import MovementHistoryV1, estimate_movement
from src.probe.movement_task_reference_v1 import METHODS, MovementTaskFailure, run_movement_task
from src.probe.movement_history_reference_v1 import operator_samples
from src.probe.operator_identification import sample_digest
from src.probe.physical_reprobe_v1 import Start, StepReceipt


def observation(x=0., z=.25, *, success=False, terminated=False):
    values = [0.]*39;values[:3] = [x, .6, z];values[4:7] = [0., .8, .02]
    return StepObservation(values, terminated, False, success)


class SyntheticHost:
    def __init__(self, *, start_step=16, early=False, unreachable=False, terminate=False, never_end=False):
        self.start = Start("push-v3", start_step, observation(z=.05 if unreachable else .25),
                           ((1., 0.), (0., 1.)), (.02, -.01))
        self.context = (observation(-.003), observation(-.001), self.start.current)
        self.calls = start_step;self.commands = [];self.events = [];self.queries = 0
        self.early, self.unreachable, self.terminate, self.never_end = early, unreachable, terminate, never_end

    def emit(self, kind, payload):
        value = {**deepcopy(payload), "sequence": len(self.events), "saved_ns": perf_counter_ns()}
        self.events.append({"kind": kind, "payload": deepcopy(value)})
        return value

    def policy(self, obs):
        self.queries += 1;obs[0] = 999.  # The caller must supply an independent array.
        return np.array([.2, -.1, .1, -1.], np.float32)

    def step(self, saved):
        self.commands.append(deepcopy(saved));self.calls += 1
        move = saved["phase"] == "REPOSITION"
        number = sum(r["phase"] == "REPOSITION" for r in self.commands)
        # A drifting then settled observation sequence: real within this fixture,
        # not a model of robot dynamics. It generates nonzero integral evidence.
        x = (.004 if number == 1 else .008) if move else .009
        ended = (move and self.early) or (not move and not self.never_end)
        return StepReceipt(observation(x, .05 if self.unreachable else .25,
                            success=ended and not self.terminate, terminated=ended and self.terminate), self.calls)

    def run(self, method, reference=None):
        return run_movement_task(self.start, self.context, method=method, reference=reference,
                                 policy=self.policy, step=self.step, emit=self.emit)


def synthetic_valid_estimate(reference, history):
    with patch("src.probe.movement_history_reference_v1.infer_operator", return_value={
            "valid": True, "matrix_xy": [[.8, 0.], [0., 1.2]], "bias_xy": [.1, -.02],
            "samples": len(history.transitions), "sample_digest": sample_digest(operator_samples(history)),
            "physical_response_qualified": False, "probability_guarantee": False, "research_simulation_only": True,
            "design_rank": 3, "scaled_condition": 10., "residual_rmse_m": 0., "singular_values": [1.2, .8],
            "selected_start": "BOUNDED_LINEAR_REFINEMENT",
            "optimizer_trials": [{"parameters": [.8, 0., .1, 0., 1.2, -.02], "success": True, "nfev": 2,
                                  "start": "BOUNDED_LINEAR_REFINEMENT", "residual_rmse_m": 0.}], "reason": "POINT_FORWARD_PREDICTION_ERROR_FIT"}):
        return estimate_movement(reference.decoded(), history)


class MovementTaskReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models, _ = load_bank(Path(__file__).resolve().parents[1])

    def run_method(self, method, **kwargs):
        host = SyntheticHost(**kwargs)
        ref = self.models["push-v3"] if method == "MOVE_ARX_KEEP" else None
        return host, host.run(method, ref)

    def test_all_three_movement_methods_have_identical_actual_movement(self):
        with patch("src.probe.movement_task_reference_v1.estimate_bound_movement", synthetic_valid_estimate):
            runs = [self.run_method(m) for m in METHODS[1:]]
        movement = [[r["command"] for r in h.commands if r["phase"] == "REPOSITION"] for h, _ in runs]
        self.assertEqual(movement[0], movement[1]);self.assertEqual(movement[0], movement[2])
        self.assertGreater(len(movement[0]), 3)
        task_commands = [h.commands[-1]["command"] for h, _ in runs]
        self.assertNotEqual(task_commands[0], task_commands[1]);self.assertNotEqual(task_commands[0], task_commands[2])
        self.assertEqual([r["outcome"]["action"] for _, r in runs],
                         ["RUN_SAVED_C8", "RUN_SAVED_INTEGRAL", "RUN_SAVED_ARX"])

    def test_direct_uses_old_correction_without_movement_or_fitting(self):
        with patch("src.probe.movement_task_reference_v1.estimate_bound_movement", side_effect=AssertionError("no fit")):
            host, result = self.run_method("DIRECT_C8")
        np.testing.assert_allclose(host.commands[0]["command"], [.22, -.11, .1, -1.], atol=1e-7)
        self.assertEqual((result["outcome"]["reposition_steps"], result["outcome"]["fit_attempts"]), (0, 0))
        self.assertEqual(result["outcome"]["deadline_loss"], 17)

    def test_actual_short_history_rejects_fit_and_keeps_pre_movement_c8(self):
        host, result = self.run_method("MOVE_ARX_KEEP")
        kept, _ = self.run_method("MOVE_KEEP_C8")
        self.assertEqual(result["fit"]["estimate"]["status"], "INVALID_ESTIMATE")
        self.assertEqual(result["outcome"]["action"], "REJECT_ARX_KEEP_SAVED_C8")
        self.assertEqual(host.commands[-1]["command"], kept.commands[-1]["command"])
        self.assertEqual(result["outcome"]["fit_attempts"], 1)

    def test_history_includes_actual_context_and_every_movement_response(self):
        seen = []
        def fit(reference, history):
            seen.append(history);return synthetic_valid_estimate(reference, history)
        with patch("src.probe.movement_task_reference_v1.estimate_bound_movement", fit):
            host, result = self.run_method("MOVE_ARX_KEEP")
        history = MovementHistoryV1.from_mapping(result["history"]["history"])
        self.assertEqual(history, seen[0]);self.assertEqual(history.context, host.context)
        self.assertEqual(len(history.transitions), result["outcome"]["reposition_steps"])
        self.assertEqual(history.transitions[0].before, host.start.current)
        self.assertEqual(result["outcome"]["optimizer_nfev"], 2)
        self.assertEqual(result["events"], host.events)
        self.assertTrue(all(r["decision_sequence"] < r["sequence"] for r in host.commands))

    def test_early_success_stays_success_without_fit_or_task_query(self):
        with patch("src.probe.movement_task_reference_v1.estimate_bound_movement", side_effect=AssertionError("no fit")):
            for method in METHODS[1:]:
                host, result = self.run_method(method, early=True)
                self.assertTrue(result["outcome"]["success"])
                self.assertEqual((host.queries, result["outcome"]["fit_attempts"], result["outcome"]["deadline_loss"]), (0, 0, 17))
                self.assertEqual(result["outcome"]["action"], "ENDED_NO_UPDATE")

    def test_termination_without_success_is_not_success_or_an_estimation_failure(self):
        host, result = self.run_method("MOVE_ARX_KEEP", early=True, terminate=True)
        self.assertFalse(result["outcome"]["success"])
        self.assertEqual((host.queries, result["outcome"]["deadline_loss"], result["outcome"]["fit_attempts"]), (0, 500, 0))

    def test_unreached_anchor_uses_all_64_responses_and_continues_task(self):
        host, result = self.run_method("MOVE_INTEGRAL", unreachable=True)
        self.assertFalse(result["outcome"]["anchor_reached"])
        self.assertEqual((result["outcome"]["reposition_steps"], result["outcome"]["task_steps"]), (64, 1))
        self.assertEqual(host.queries, 1)

    def test_total_budget_stops_at_500_without_restart(self):
        host, result = self.run_method("MOVE_KEEP_C8", never_end=True, unreachable=True, start_step=336)
        self.assertEqual(host.calls, 500);self.assertEqual(len(host.commands), 164)
        self.assertEqual(result["outcome"]["task_steps"], 100)
        self.assertFalse(result["outcome"]["success"])

    def test_bad_method_budget_context_and_model_fail_before_any_callbacks(self):
        for mode in ("unknown", "budget", "context", "model", "unexpected_model"):
            host = SyntheticHost(start_step=337 if mode == "budget" else 16)
            method = "MOVE_ARX_KEEP";ref = self.models["push-v3"]
            if mode == "unknown":method = "BEST_AFTER_RESULTS"
            if mode == "context":host.context = (host.context[0],)*3
            if mode == "model":ref = self.models["reach-v3"]
            if mode == "unexpected_model":method = "MOVE_KEEP_C8"
            with self.subTest(mode=mode), self.assertRaises(ValueError):host.run(method, ref)
            self.assertEqual((host.events, host.commands, host.queries), ([], [], 0))

    def test_unknown_stale_and_falsely_qualified_estimates_never_drive_task(self):
        for key, value in (("history_sha256", "0"*64), ("model_sha256", "0"*64),
                           ("status", "UNKNOWN"), ("physical_response_qualified", True), ("future_success", True)):
            def changed(reference, history):
                result = synthetic_valid_estimate(reference, history);result[key] = value;return result
            host = SyntheticHost()
            with self.subTest(key=key), patch("src.probe.movement_task_reference_v1.estimate_bound_movement", changed), self.assertRaises(MovementTaskFailure):
                host.run("MOVE_ARX_KEEP", self.models["push-v3"])
            self.assertEqual(host.queries, 0)

    def test_estimator_exception_preserves_partial_execution_without_fallback(self):
        host = SyntheticHost()
        with patch("src.probe.movement_task_reference_v1.estimate_bound_movement", side_effect=RuntimeError("injected")), self.assertRaises(MovementTaskFailure) as raised:
            host.run("MOVE_ARX_KEEP", self.models["push-v3"])
        record = raised.exception.record
        self.assertEqual(record["completed_steps"], host.calls);self.assertEqual(record["fit_attempts"], 1)
        self.assertFalse(record["optimizer_nfev_complete"]);self.assertEqual(host.queries, 0)

    def test_nested_private_fields_and_malformed_inverse_or_trial_are_rejected(self):
        for mode in ("private", "trial", "reason", "inverse", "samples"):
            def changed(reference, history):
                result = synthetic_valid_estimate(reference, history);fit = result["fit"]
                if mode == "private":fit["executed_action_oracle"] = [0.]*4
                elif mode == "trial":fit["optimizer_trials"][0]["future_success"] = True
                elif mode == "reason":fit["reason"] = "UNREGISTERED_FALLBACK"
                elif mode == "inverse":fit["matrix_xy"] = [[0., 0.], [0., 0.]]
                else:fit["samples"] += 1
                return result
            host = SyntheticHost()
            with self.subTest(mode=mode), patch("src.probe.movement_task_reference_v1.estimate_bound_movement", changed), self.assertRaises(MovementTaskFailure):
                host.run("MOVE_ARX_KEEP", self.models["push-v3"])
            self.assertEqual(host.queries, 0)

    def test_changed_acknowledgement_or_physical_receipt_is_not_accepted(self):
        for mode in ("ack", "count", "mutation"):
            host = SyntheticHost();emit, step = host.emit, host.step
            def changed_emit(kind, payload):
                result = emit(kind, payload)
                if kind == "MOVEMENT_TASK_DECISION":result["controller"]["offset"][0] += .1
                return result
            def changed_step(saved):
                result = step(saved)
                if mode == "count":return replace(result, completed_steps=result.completed_steps+1)
                saved["command"][0] += .1;return result
            if mode == "ack":host.emit = changed_emit
            else:host.step = changed_step
            with self.subTest(mode=mode), self.assertRaises(MovementTaskFailure):host.run("DIRECT_C8")
            if mode == "ack":self.assertEqual(host.commands, [])


if __name__ == "__main__":unittest.main()
