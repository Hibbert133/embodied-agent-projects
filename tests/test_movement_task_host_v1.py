"""Instrumented one-axis native fixtures; no MetaWorld scientific population."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from src.analysis.movement_model_source_v1 import load_bank
from src.analysis.movement_task_host_v1 import MovementHostFailure, execute_movement_task
from src.analysis.movement_task_record_v1 import audit_record
from src.probe.movement_task_reference_v1 import run_movement_task
from tests import test_physical_reprobe_host_v1 as fixture
from tests.test_movement_task_reference_v1 import synthetic_valid_estimate


SOFTWARE_RECEIPTS = []
WarmTinyEnv = fixture.WarmTinyEnv


class MovementTaskHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.models, _ = load_bank(Path(__file__).resolve().parents[1])

    def setUp(self):
        fixture.PhysicalReprobeHostTests.setUp(self)
        original = WarmTinyEnv.step
        def ended(env, action):
            obs, reward, term, trunc, info = original(env, action)
            return obs, reward, term, trunc, {**info, "success": env.calls >= 20}
        p = patch.object(WarmTinyEnv, "step", ended);p.start();self.patches.append(p)
        self.reset_before = {"counts": {}, "by_phase": {}}

    def tearDown(self):
        SOFTWARE_RECEIPTS.append({"test": self.id(), "native_frames": self.frames, "native_resets": self.native_resets,
            "host_control_steps": self.session.completed, "host_attempted_control_steps": self.session.attempts,
            "host_policy_queries": self.session.policy_queries, "lifecycle": self.ledger.snapshot(),
            "new_metaworld_steps": 0, "new_scientific_seeds": 0, "new_api_calls": 0,
            "scope": "One-axis native fixture; synthetic initial correction and optional synthetic fit, no scientific task benefit."})
        for p in reversed(self.patches):p.stop()
        self.env.close()

    def execute(self, method="MOVE_KEEP_C8", lookup=None):
        return execute_movement_task(self.session, self.choice, lookup or (lambda i: deepcopy(self.events[i])),
            reset_before=self.reset_before, method=method,
            reference=self.models["push-v3"] if method == "MOVE_ARX_KEEP" else None)

    def test_real_commands_use_saved_choices_in_one_continuous_world(self):
        s = self.session;before = s.completed;tape = s.ctx["noise_rows"];clock = float(self.env.data.time)
        result = self.execute();public = result["public"]
        self.assertEqual(public["outcome"]["total_steps"], 20)
        self.assertTrue(public["outcome"]["success"]);self.assertGreater(public["outcome"]["task_steps"], 0)
        self.assertEqual(audit_record(public, None), public["outcome"])
        self.assertIs(s.ctx["noise_rows"], tape);self.assertEqual(self.native_resets, 1)
        self.assertEqual(self.frames, 5*s.completed)
        self.assertAlmostEqual(float(self.env.data.time)-clock, .0125*(s.completed-before), places=10)
        self.assertEqual(result["new_policy_queries"], public["outcome"]["task_steps"])
        for row in s.last_rows[before:]:
            saved = self.events[row["global_command_sequence"]]
            self.assertEqual(saved["public_payload"]["command"], row["command"])
            self.assertLess(saved["saved_ns"], row["execution_started_ns"])
            self.assertEqual(row["noise_cursor_after"], row["logical_step"]+1)

    def test_bound_arx_result_drives_actual_native_task_commands(self):
        with patch("src.probe.movement_task_reference_v1.estimate_bound_movement", synthetic_valid_estimate):
            result = self.execute("MOVE_ARX_KEEP")
        self.assertEqual(result["public"]["outcome"]["action"], "RUN_SAVED_ARX")
        self.assertEqual(result["new_parameter_fits"], 1);self.assertEqual(result["optimizer_nfev"], 2)
        self.assertEqual(audit_record(result["public"], self.models["push-v3"]), result["public"]["outcome"])
        command = next(r for r in self.session.last_rows if r["phase"] == "TASK_AFTER_MOVEMENT")
        self.assertNotEqual(command["command"], command["raw_policy"])

    def test_original_source_fit_and_physical_use_are_required(self):
        before = self.frames
        def changed(index):
            row = deepcopy(self.events[index])
            if index == self.session._map[self.choice]:row["public_payload"]["controller"]["offset"][0] += .1
            return row
        with self.assertRaisesRegex(ValueError, "saved valid fit"):self.execute(lookup=changed)
        self.assertEqual(self.frames, before)

    def test_budget_or_rewound_prefix_fails_before_any_new_physics(self):
        before = self.frames;self.session.run_budget["maximum"] = 499
        with self.assertRaisesRegex(ValueError, "whole-study budget"):self.execute()
        self.session.run_budget["maximum"] = 500;self.session.last_rows[-2]["logical_step"] -= 1
        with self.assertRaisesRegex(ValueError, "chronological physical receipts"):self.execute()
        self.assertEqual(self.frames, before)

    def test_repeated_operation_is_rejected(self):
        self.execute("DIRECT_C8");before = self.frames
        with self.assertRaisesRegex(ValueError, "already consumed"):self.execute()
        self.assertEqual(self.frames, before)

    def test_changed_command_rejected_before_physics(self):
        def changed(*args, **kwargs):
            actual = kwargs["step"]
            def bad(saved):
                saved["command"][0] += .01;return actual(saved)
            kwargs["step"] = bad;return run_movement_task(*args, **kwargs)
        before = self.frames
        with patch("src.analysis.movement_task_host_v1.run_movement_task", changed), self.assertRaises(MovementHostFailure) as raised:
            self.execute("DIRECT_C8")
        self.assertEqual(self.frames, before)
        self.assertEqual(raised.exception.record["actual_completed_control_steps"], 0)

    def test_extra_native_work_preserved_in_failure_cost_not_hidden_by_actor_counter(self):
        original = self.session._agent_step
        def extra(saved):
            after = original(saved)
            with self.ledger.scope("CONTROL"):self.env.do_simulation([0.], 5)
            return after
        with patch.object(self.session, "_agent_step", extra), self.assertRaises(MovementHostFailure) as raised:self.execute()
        self.assertEqual(raised.exception.record["actual_completed_control_steps"], 1)
        self.assertEqual(raised.exception.record["new_simulation_frames_completed"], 10)
        self.assertIn("physical frame work", str(raised.exception))

    def test_reset_and_equal_valued_noise_replacement_are_detected(self):
        original = self.session._agent_step
        def changed(saved):
            after = original(saved)
            tape = self.session.ctx["noise_rows"].copy();tape.flags.writeable = False
            self.session.ctx["noise_rows"] = tape;return after
        with patch.object(self.session, "_agent_step", changed), self.assertRaisesRegex(MovementHostFailure, "noise tape replaced"):
            self.execute()

    def test_actual_mid_operation_reset_is_detected_and_counted(self):
        original = self.session._agent_step
        def changed(saved):
            after = original(saved)
            with self.ledger.scope("CONTROLLED_RESET"):self.env.reset()
            return after
        with patch.object(self.session, "_agent_step", changed), self.assertRaisesRegex(MovementHostFailure, "mid-operation reset"):
            self.execute()
        self.assertEqual(self.native_resets, 2)


if __name__ == "__main__":unittest.main()
