"""Artificial callback qualification; no new MetaWorld state or task seed."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import boundary_prefix as prefix
from src.probe.operator_identification import affine_controller, encode_controller
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import CallbackHost, fit


class Host(CallbackHost):
    def step(self, saved):
        # STEP_RESULT and fit records are persisted between physical commands.
        return super().step(saved)


class BoundaryPrefixTests(unittest.TestCase):
    def run_prefix(self, host=None, four=None, eight=None):
        host = host or Host(model(), finish=100)
        with patch.object(prefix, "infer_four", return_value=fit((.1, -.05)) if four is None else four) as f4, patch.object(
                prefix, "infer_operator", return_value=fit((-.08, .12)) if eight is None else eight) as f8:
            result = prefix.prepare_boundary("push-v3", host.initial, host.model, host.policy, host.step, host.emit)
        return host, result, f4, f8

    def test_actual_four_and_eight_prefixes_and_eight_step_controller_are_used(self):
        host, result, f4, f8 = self.run_prefix()
        self.assertTrue(result["ready"]);self.assertEqual(result["completed_steps"], 16)
        self.assertEqual(result["policy_queries"], 8);self.assertEqual(result["fits_completed"], 2)
        self.assertEqual(len(f4.call_args.args[1].commands), 4)
        self.assertEqual(len(f8.call_args.args[1].commands), 8)
        self.assertEqual(f4.call_args.args[1].commands, f8.call_args.args[1].commands[:4])
        self.assertEqual(f4.call_args.args[1].observations, f8.call_args.args[1].observations[:4])
        expected = encode_controller(affine_controller([[1., 0.], [0., 1.]], [-.08, .12]), [.3, -.2, 0., 0.]).tolist()
        self.assertEqual(host.sent[8:], [expected] * 8)
        saved = host.events[result["saved_choice_sequence"]][1]
        current = host.events[result["current_choice_sequence"]][1]
        self.assertEqual(saved["at_calls"], 4);self.assertEqual(current["at_calls"], 8)
        self.assertFalse(result["saved_candidate_was_previously_applied"])

    def test_invalid_four_stops_without_second_probe_or_policy(self):
        host, result, _, f8 = self.run_prefix(four={"valid": False, "nfev": 3})
        self.assertFalse(result["ready"]);self.assertEqual(result["reason"], "INVALID_FOUR")
        self.assertEqual(host.calls, 4);self.assertEqual(result["optimizer_nfev"], 3)
        f8.assert_not_called();self.assertFalse(host.policy_inputs)

    def test_invalid_eight_stops_without_substitution(self):
        host, result, _, _ = self.run_prefix(eight={"valid": False, "nfev": 2})
        self.assertFalse(result["ready"]);self.assertEqual(result["reason"], "INVALID_EIGHT")
        self.assertEqual(host.calls, 8);self.assertIsNone(result["current_choice_sequence"])
        self.assertIsNotNone(result["saved_choice_sequence"]);self.assertFalse(host.policy_inputs)

    def test_early_probe_and_policy_end_are_retained(self):
        for finish in (2, 6, 12, 16):
            with self.subTest(finish=finish):
                host, result, _, _ = self.run_prefix(Host(model(), finish=finish))
                self.assertEqual(host.calls, finish);self.assertFalse(result["ready"])
                self.assertTrue(result["final_observation"]["success"])

    def test_journal_mutation_rejected_before_motion(self):
        host = Host(model(), finish=100);original = host.emit
        def corrupt(kind, payload):
            payload["at_calls"] = 99
            return original(kind, payload)
        host.emit = corrupt
        with self.assertRaisesRegex(ValueError, "acknowledgement"):
            self.run_prefix(host)
        self.assertEqual(host.calls, 0)

    def test_saved_candidate_cannot_silently_replace_current_control(self):
        a, _, _, _ = self.run_prefix(four=fit((.25, -.2)))
        b, _, _, _ = self.run_prefix(four=fit((-.25, .2)))
        self.assertEqual(a.sent, b.sent)

    def test_prefix_has_no_truth_seed_or_future_fields(self):
        _, result, _, _ = self.run_prefix()
        forbidden = {"seed", "fault", "fault_oracle", "future", "noise_rows", "native_sha256", "rng_state"}
        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden)
                for item in value.values(): inspect(item)
            elif isinstance(value, (tuple, list)):
                for item in value: inspect(item)
        inspect(result)


if __name__ == "__main__":
    unittest.main()
