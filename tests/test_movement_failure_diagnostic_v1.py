"""Only arrays, synthetic sequences and existing saved records. No native fixtures."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import socket
import subprocess
import unittest

import numpy as np

from src.analysis import movement_failure_diagnostic_v1 as d
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard

ROOT = Path(__file__).resolve().parents[1]
FAULT = {"matrix_xy": [[1., .2], [-.1, .8]], "bias_xy": [.12, -.08], "deadzone_xy": [0., 0.]}


def model():
    beta = np.zeros((11, 2))
    beta[1, 0] = .4
    beta[2, 1] = .4
    beta[4, 0] = .1
    beta[5, 1] = .1
    beta[7, 0] = .01
    beta[8, 1] = .012
    return {"mean": [0.]*10, "scale": [1.]*10, "coefficients": beta.tolist()}


class ArrayDiagnosticTests(unittest.TestCase):
    def test_exact_float32_chain(self):
        u = [.5, -.8, .9, -1.]
        noise = np.array([.1, -.2, .3], np.float32)
        pre, noisy, applied, _ = d.actuator_trace(u, FAULT, noise)
        expected = np.asarray(u, np.float32)
        expected[:2] = np.asarray(FAULT["matrix_xy"], np.float32) @ expected[:2] + np.asarray(FAULT["bias_xy"], np.float32)
        self.assertTrue(np.array_equal(pre, expected))
        expected[:3] += noise
        self.assertTrue(np.array_equal(noisy, expected))
        self.assertTrue(np.array_equal(applied, np.clip(expected, -1, 1)))

    def test_nonzero_deadzone(self):
        f = deepcopy(FAULT); f["matrix_xy"] = np.eye(2).tolist(); f["bias_xy"] = [0., 0.]; f["deadzone_xy"] = [.2, .4]
        pre, _, _, _ = d.actuator_trace([.1, -.7, 0., 0.], f, [0., 0., 0.])
        np.testing.assert_allclose(pre[:2], [0., -.5], atol=1e-7)

    def test_early_clip_is_detected(self):
        f = {"matrix_xy": [[2., 0.], [0., 1.]], "bias_xy": [0., 0.], "deadzone_xy": [0., 0.]}
        _, _, applied, wrong = d.actuator_trace([.7, 0., 0., 0.], f, [-.3, 0., 0.])
        self.assertNotEqual(applied[0], wrong[0])
        row = {"logical_step": 2, "noise_cursor_after": 3, "command": [.7, 0., 0., 0.], "executed_action_oracle": wrong.tolist()}
        with self.assertRaisesRegex(ValueError, "actuator chain"):
            d.check_actuator(row, f, [-.3, 0., 0.], 2)

    def test_noise_cursor_mismatch(self):
        row = {"logical_step": 2, "noise_cursor_after": 2, "command": [0.]*4, "executed_action_oracle": [0.]*4}
        with self.assertRaisesRegex(ValueError, "cursor"):
            d.check_actuator(row, FAULT, [0.]*3, 2)

    def test_noise_row_offset_mismatch(self):
        tape = d.noise_tape(25000)
        actual = d.actuator_trace([0.]*4, FAULT, tape[0])[2]
        row = {"logical_step": 0, "noise_cursor_after": 1, "command": [0.]*4, "executed_action_oracle": actual.tolist()}
        with self.assertRaisesRegex(ValueError, "actuator chain"):
            d.check_actuator(row, FAULT, tape[1], 0)

    def test_inverse_is_not_forward_mapping(self):
        raw = [.3, -.4, .1, 0.]
        controller = d.inverse_controller(FAULT["matrix_xy"], FAULT["bias_xy"])
        _, pre, sent = d.controller_trace(raw, controller)
        np.testing.assert_allclose(np.asarray(FAULT["matrix_xy"]) @ pre[:2]+FAULT["bias_xy"], raw[:2], atol=2e-8)
        forward, _ = d.working_input(raw, FAULT["matrix_xy"], FAULT["bias_xy"])
        self.assertFalse(np.allclose(sent, forward))

    def test_policy_and_controller_clipping_distinct(self):
        controller = {"matrix_xy": [[2., 0.], [0., 1.]], "offset": [.3, 0., 0., 0.]}
        desired, pre, sent = d.controller_trace([3., .1, 2., -2.], controller)
        np.testing.assert_array_equal(desired, [1., np.float32(.1), 1., -1.])
        self.assertGreater(pre[0], 1.)
        self.assertEqual(sent[0], 1.)

    def test_missing_two_real_displacements(self):
        h = d.CausalHistory([0.]*39)
        self.assertIsNone(h.request(0)); h.observe(0, [1.]*39)
        self.assertIsNone(h.request(1)); h.observe(1, [3.]*39)
        last, prior = h.request(2)
        np.testing.assert_array_equal(last, [2.]*3)
        np.testing.assert_array_equal(prior, [1.]*3)

    def test_future_request_rejected(self):
        h = d.CausalHistory([0.]*39)
        with self.assertRaisesRegex(ValueError, "future"):
            h.request(2)

    def test_unrequested_and_repeated_response_rejected(self):
        h = d.CausalHistory([0.]*39)
        with self.assertRaises(ValueError):
            h.observe(0, [0.]*39)
        h.request(0)
        with self.assertRaises(ValueError):
            h.request(0)

    def test_no_zero_padding_predict(self):
        with self.assertRaisesRegex(ValueError, "zero padding"):
            d.prediction(model(), None, [0.]*4)

    def test_future_saved_parameter_step_rejected(self):
        fit = {"estimate": {"decision_step": 30}, "at_calls": 30, "saved_ns": 100}
        with self.assertRaisesRegex(ValueError, "future parameter"):
            d.ensure_saved_before(fit, {"logical_step": 29, "execution_started_ns": 200})

    def test_future_saved_parameter_clock_rejected(self):
        fit = {"estimate": {"decision_step": 30}, "at_calls": 30, "saved_ns": 200}
        with self.assertRaises(ValueError):
            d.ensure_saved_before(fit, {"logical_step": 30, "execution_started_ns": 100})
        d.ensure_saved_before(fit, {"logical_step": 30, "execution_started_ns": 201})

    def test_known_model_expected_residual_and_mismatch(self):
        m = model(); history = ([.01, -.02, 0.], [.003, .002, 0.]); u = [.2, -.3, 0., 0.]
        predicted = d.prediction(m, history, u)
        np.testing.assert_allclose(predicted, [.0063, -.0114], atol=1e-15)
        actual = predicted+np.array([.001, -.002])
        np.testing.assert_allclose(actual-d.prediction(m, history, u), [.001, -.002], atol=1e-15)

    def test_noise_input_identity_independent(self):
        m = model(); h = ([.01, -.02, 0.], [.003, .002, 0.]); u = [.9, -.7, .8, 0.]
        pre, _, actual, _ = d.actuator_trace(u, FAULT, [-.03, .05, .2])
        true, _ = d.working_input(u, FAULT["matrix_xy"], FAULT["bias_xy"])
        a, z, t = (d.prediction(m, h, inp) for inp in (actual, np.clip(pre, -1, 1), true))
        y = np.array([.01, -.01])
        np.testing.assert_allclose(y-t, (y-a)+(a-z)+(z-t), atol=1e-15)
        self.assertGreater(np.linalg.norm(a-z), 0)

    def test_independent_predictor_preserves_float64_standardization(self):
        from scripts.audit_movement_failure_diagnostic_v1 import predict
        m = model(); h = ([.01, -.02, 0.], [.003, .002, 0.]); u = np.array([.3333333, -.4444444, 0., 0.], np.float32)
        np.testing.assert_allclose(predict(m, h[0], h[1], u), d.prediction(m, h, u), atol=1e-15, rtol=0)

    def test_feedback_reverse_lag_uses_past_noise(self):
        from scripts.supplement_movement_failure_diagnostic_v1 import correlations
        noise = [0., 1., -1., 2., -2., .5, 1.5]
        steps = [{"step":i, "noise":[n,n], "command":[noise[i-1] if i else 0.]*2,
                  "last":[float(i),float(i)], "error_true":[float(i)*.1]*2} for i,n in enumerate(noise)]
        corr = next(c for c in correlations(steps) if c["pair"] == "noise_past__command_current" and c["lag"] == 1 and c["axis"] == 0)
        self.assertEqual(corr["n"], 6)
        self.assertAlmostEqual(corr["r"], 1.)

    def test_zero_length_segment_missing_not_zero(self):
        cell = d.summarize_steps([])
        self.assertEqual(cell["n"], 0)
        self.assertIsNone(cell["error_true_rmse"])
        self.assertEqual(cell["missing_reason"], "ZERO_LENGTH_SEGMENT")

    def test_rank_deficient_input_and_null_condition(self):
        self.assertIsNone(d.input_design([])["rank"])
        result = d.input_design([[0., 0., 0., 0.]]*3)
        self.assertEqual(result["rank"], 1)
        self.assertIsNone(result["condition"])

    def test_constant_and_short_correlation(self):
        self.assertIsNone(d.pearson([0., 0., 0.], [1., 2., 3.])["r"])
        self.assertEqual(d.pearson([1., None], [2., 3.])["n"], 1)

    def test_equal_group_aggregation_not_time_pooling(self):
        result = d.grouped_means([{"group": 0, "x": 1.}, {"group": 0, "x": 3.}, {"group": 1, "x": 10.}], ["x"])
        self.assertEqual(result["x"]["mean"], 6.)
        self.assertEqual(result["x"]["available_groups"], 2)

    def test_frozen_followup_budget_and_partition_separation(self):
        def unique(pairs):
            value = {}
            for k,v in pairs:
                if k in value:
                    raise ValueError("duplicate configuration key")
                value[k] = v
            return value
        cfg = json.loads((ROOT/"configs/movement_task/response_model_qualification_design_v1.json").read_text(encoding="utf-8"), object_pairs_hook=unique)
        partitions = [set(range(cfg[k]["episode_seeds"][0],cfg[k]["episode_seeds"][1]+1)) for k in ("training","calibration","qualification")]
        self.assertTrue(all(not partitions[i]&partitions[j] for i in range(3) for j in range(i)))
        self.assertEqual(sum(cfg[k]["executions"] for k in ("training","calibration","qualification")), 270)
        budget = cfg["new_data_budget"]
        self.assertEqual(270*cfg["maximum_steps_per_execution"], budget["control_steps"])
        self.assertEqual(51*270, budget["all_resets"])
        self.assertEqual(25500*270+5*budget["control_steps"], budget["physical_frames"])
        self.assertEqual(cfg["new_api_calls"], 0)
        self.assertFalse(cfg["task_utility_gate_established_by_this_protocol"])

    def test_early_success_case_preserved(self):
        sent = [.4, 0., 0., 0.]; noise = d.noise_tape(25000)[0]
        actual = d.actuator_trace(sent, FAULT, noise)[2].tolist()
        initial = [0.]*39; after = [0.]*39; after[0] = .001
        row = {"logical_step": 0, "noise_cursor_after": 1, "phase": "FIXED_PROBE", "command": sent, "raw_policy": None,
               "executed_action_oracle": actual, "after": {"observation": after}, "info": {}}
        case = {"unit": 0, "task": "push-v3", "variant": "UNCHANGED_MOVE_ARX_KEEP", "seed": 25000, "planned_boundary": 16,
                "fault_oracle": FAULT, "fault_transition": None, "movement": None, "state_witnesses": [], "physical_rows": [row],
                "prefix": {"public": {"events": [{"kind": "PREFIX_PROGRAM", "payload": {"initial": {"observation": initial}}}]}},
                "success": True, "total_steps": 1, "reposition_steps": 0, "deadline_loss": 1, "action": "NO_LIVE_BOUNDARY", "stopped": False,
                "completed": True, "boundary_ready": False}
        s, steps, cells = d.analyze_case(case, model(), d.canonical_context(case))
        self.assertTrue(s["success"]); self.assertIsNone(s["fit_valid"])
        self.assertEqual(s["missing_or_fit_reason"], "NO_LIVE_BOUNDARY")
        self.assertEqual(s["history_unavailable_steps"], 1)
        self.assertTrue(all(c["n"] == 0 for c in cells))

    def test_guard_blocks_simulator_network_optimizer(self):
        with read_only_analysis_guard():
            for name in ("metaworld", "mujoco", "gymnasium", "openai", "httpx", "scipy.optimize"):
                with self.assertRaises(RuntimeError):
                    __import__(name)
            with self.assertRaises(RuntimeError):
                socket.socket()
            with self.assertRaises(RuntimeError):
                subprocess.run(["never-execute-this-program"])


class SavedRecordTests(unittest.TestCase):
    def test_four_saved_methods_without_environment(self):
        folder = ROOT/"outputs/movement_task/development_v1/movement_task_20261019T191708Z_eee0803df5bf"
        bank_path = ROOT/"outputs/forward_prediction/baselines_v1/forward_prediction_20261014T064233Z_bb812df15401/models.json"
        bank = json.loads(bank_path.read_text(encoding="utf-8"))["models"]
        with gzip.open(folder/"collection/cases.jsonl.gz", "rt", encoding="utf-8") as f:
            records = [json.loads(next(f)) for _ in range(4)]
        context = d.canonical_context(records[-1])
        with read_only_analysis_guard():
            for case in records:
                summary, steps, cells = d.analyze_case(case, bank[case["task"]]["LINEAR_ARX"], context)
                self.assertEqual(summary["record_rows"], case["total_steps"])
                self.assertLess(summary["algebra_max_abs"], 1e-14)
                self.assertEqual(len(cells), 16)

    def test_saved_invalid_fit_and_early_end_retained(self):
        folder = ROOT/"outputs/movement_task/development_v1/movement_task_20261019T191708Z_eee0803df5bf"
        bank = json.loads((ROOT/"outputs/forward_prediction/baselines_v1/forward_prediction_20261014T064233Z_bb812df15401/models.json").read_text(encoding="utf-8"))["models"]
        found = set()
        with read_only_analysis_guard(), gzip.open(folder/"collection/cases.jsonl.gz", "rt", encoding="utf-8") as f:
            for line in f:
                case = json.loads(line)
                if not case["variant"].endswith("MOVE_ARX_KEEP") or case["action"] not in ("REJECT_ARX_KEEP_SAVED_C8", "ENDED_NO_UPDATE") or case["action"] in found:
                    continue
                summary, steps, _ = d.analyze_case(case, bank[case["task"]]["LINEAR_ARX"], d.canonical_context(case))
                self.assertEqual(summary["success"], case["success"])
                self.assertEqual(summary["action"], case["action"])
                if case["action"] == "REJECT_ARX_KEEP_SAVED_C8":
                    self.assertFalse(summary["fit_valid"])
                    self.assertTrue(all(s["arx_sent"] is None for s in steps))
                else:
                    self.assertIsNone(summary["fit_valid"])
                    self.assertEqual(summary["own_task"]["n"], 0)
                found.add(case["action"])
                if len(found) == 2:
                    break
        self.assertEqual(len(found), 2)


if __name__ == "__main__":
    unittest.main()
