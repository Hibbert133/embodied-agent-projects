"""Saved nominal programs: synthetic state machine and one-axis native host."""
from copy import deepcopy
from dataclasses import asdict
import unittest
from unittest.mock import patch

import numpy as np

from src.probe import selected_nominal_acquisition_v1 as actor
from src.probe import local_reprobe_v1 as previous
from src.probe.selected_response_reference_v1 import NominalSelectedTrajectory
from src.analysis import selected_nominal_host_v1 as host
from tests.test_physical_reprobe_v1 import Host, start, observation
from tests import test_physical_reprobe_host_v1 as fixture

SOFTWARE_RECEIPTS = []


def program(sign=1.):
    values = np.c_[sign*np.random.default_rng(401).uniform(-.6, .6, (8, 2)), np.zeros((8, 2))]
    return actor.NominalProgram(tuple(tuple(float(v) for v in row) for row in values))


class SelectedNominalActorTests(unittest.TestCase):
    def test_preassigned_program_changes_actual_probe_without_changing_relocation(self):
        initial = start((.2, .8, .25));left, right = Host(initial), Host(initial)
        a = actor.acquire(initial, program(), left.step, left.emit)
        b = actor.acquire(initial, program(-1), right.step, right.emit)
        self.assertEqual(a["reason"], "COMPLETE_NOMINAL_TRAIN")
        count = a["reposition_steps"];self.assertEqual(count, b["reposition_steps"])
        self.assertEqual([r["command"] for r in left.executed[:count]], [r["command"] for r in right.executed[:count]])
        self.assertEqual([r["command"] for r in left.executed[count:]], [list(c) for c in program().commands])
        self.assertNotEqual(a["nominal_trajectory"]["observations"], b["nominal_trajectory"]["observations"])
        self.assertEqual(left.events[0]["payload"]["probe_program"], [list(c) for c in program().commands])
        self.assertLess(left.events[0]["payload"]["saved_ns"], left.executed[0]["saved_ns"])

    def test_original_fixed_program_preserves_all_actual_commands(self):
        initial = start((.12, .7, .19));left, right = Host(initial), Host(initial)
        a = previous.acquire(initial, left.step, left.emit, method="LOCAL_PID")
        b = actor.acquire(initial, actor.NominalProgram(previous.PROGRAM), right.step, right.emit)
        self.assertEqual([r["command"] for r in left.executed], [r["command"] for r in right.executed])
        self.assertEqual((a["new_steps"], a["final"]), (b["new_steps"], b["final"]))
        self.assertEqual(a["window"], {k:v for k,v in b["nominal_trajectory"].items() if k != "split"})

    def test_only_training_type_is_returned_and_old_input_type_rejects_it(self):
        initial = start();h = Host(initial);result = actor.acquire(initial, program(), h.step, h.emit)
        sample = NominalSelectedTrajectory.from_mapping(result["nominal_trajectory"])
        self.assertEqual(sample.split, "TRAIN");self.assertEqual(sample.commands, program().commands)
        with self.assertRaises(ValueError):previous.SelectedAnchorWindow.from_mapping(result["nominal_trajectory"])
        self.assertFalse(result["measurement_model_qualified"]);self.assertEqual(result["parameter_fits"], 0)

    def test_unknown_private_invalid_and_nonplanar_programs_rejected(self):
        for key in ("seed", "fault_oracle", "future_result"):
            with self.assertRaises(ValueError):actor.NominalProgram.from_mapping({**asdict(program()), key: {}})
        for commands in ([list(c) for c in program().commands[:7]], [[.9, 0, 0, 0]]*8,
                [[True, 0, 0, 0]]*8, [[0, 0, .1, 0]]*8, [[0, 0, 0, 1]]*8):
            with self.assertRaises(ValueError):actor.NominalProgram(commands)

    def test_changed_saved_program_rejected_before_movement(self):
        initial = start();h = Host(initial)
        def emit(kind, payload):
            saved = h.emit(kind, payload)
            if kind == "REACQUIRE_CHOICE":saved["probe_program"][0][0] += .01
            return saved
        with self.assertRaises(ValueError):actor.acquire(initial, program(), h.step, emit)
        self.assertEqual(h.used, 0)

    def test_budget_terminal_unreachable_and_scope_failures_keep_no_sample(self):
        for initial, options, expected, steps in ((start(steps=329), {}, "ENTRY_BUDGET_INSUFFICIENT", 0),
                (start(success=True), {}, "ALREADY_ENDED", 0),
                (start((.1, .7, .1)), {"stationary": True}, "ANCHOR_NOT_REACHED", 64)):
            h = Host(initial, **options);r = actor.acquire(initial, program(), h.step, h.emit)
            self.assertEqual(r["reason"], expected);self.assertEqual(h.used, steps);self.assertIsNone(r["nominal_trajectory"])
        initial = start()
        h = Host(initial, transform=lambda host: observation((0, .6, .1)) if host.used == 4 else host.current)
        r = actor.acquire(initial, program(), h.step, h.emit)
        self.assertEqual(r["reason"], "PROBE_SCOPE_EXIT");self.assertEqual(r["probe_steps"], 1)
        self.assertIsNone(r["nominal_trajectory"])


class SelectedNominalHostTests(unittest.TestCase):
    setUp = fixture.PhysicalReprobeHostTests.setUp

    def tearDown(self):
        SOFTWARE_RECEIPTS.append({"test":self.id(), "native_frames":self.frames, "native_resets":self.native_resets,
            "host_control_steps":self.session.completed, "host_policy_queries":self.session.policy_queries,
            "lifecycle":self.ledger.snapshot(), "new_metaworld_steps":0, "new_scientific_seeds":0, "new_api_calls":0,
            "scope":"One-axis software fixture, synthetic saved initial correction; no physical identification qualification"})
        for p in reversed(self.patches):p.stop()
        self.env.close()

    def execute(self, lookup=None):
        return host.execute_nominal(self.session, self.choice, lookup or (lambda i:deepcopy(self.events[i])),
            reset_before={"counts":{}, "by_phase":{}}, program=program())

    def test_native_commands_continuity_single_reset_and_complete_costs(self):
        s = self.session;before = s.completed;queries = s.policy_queries;tape = s.ctx["noise_rows"]
        result = self.execute();public = result["public"]
        self.assertEqual(public["reason"], "COMPLETE_NOMINAL_TRAIN");self.assertEqual(public["probe_steps"], 8)
        self.assertEqual(self.native_resets, 1);self.assertIs(tape, s.ctx["noise_rows"])
        self.assertEqual(self.frames, 5*s.completed);self.assertEqual(queries, s.policy_queries)
        self.assertEqual(result["new_control_steps"], s.completed-before)
        self.assertEqual(result["new_simulation_frames"], 5*(s.completed-before))
        self.assertEqual((result["new_parameter_fits"], s.captures, s.restores), (0, 0, 0))
        self.assertEqual([tuple(r["command"]) for r in s.last_rows[-8:]], list(program().commands))
        for row in s.last_rows[before:]:
            saved = self.events[row["global_command_sequence"]]
            self.assertLess(saved["saved_ns"], row["execution_started_ns"])
            self.assertEqual(saved["public_payload"]["command"], row["command"])

    def test_repeat_and_wrong_source_do_not_execute_more_physics(self):
        self.execute();before = self.frames
        with self.assertRaisesRegex(ValueError, "already consumed"):self.execute()
        self.assertEqual(self.frames, before)

    def test_non_nominal_current_context_rejected_before_action(self):
        self.session.fault["bias_xy"] = [.1, 0.];before = self.frames
        with self.assertRaisesRegex(ValueError, "nominal actuator"):self.execute()
        self.assertEqual(self.frames, before)

    def test_old_non_nominal_physical_history_cannot_be_relabelled_train(self):
        self.session.last_rows[0]["executed_action_oracle"][0] += .01;before = self.frames
        with self.assertRaisesRegex(ValueError, "source history"):self.execute()
        self.assertEqual(self.frames, before)

    def test_prior_context_installation_cannot_be_hidden_by_current_identity(self):
        self.session._stale_context_installed = True;before = self.frames
        with self.assertRaisesRegex(ValueError, "nominal actuator"):self.execute()
        self.assertEqual(self.frames, before)

    def test_context_change_during_operation_is_detected_with_spent_step_counted(self):
        original = self.session._agent_step
        def changed(saved):
            result = original(saved);self.session.fault["bias_xy"] = [.1, 0.];return result
        before = self.frames
        with patch.object(self.session, "_agent_step", changed):
            with self.assertRaisesRegex(ValueError, "nominal actuator"):self.execute()
        self.assertEqual(self.frames-before, 5);self.assertEqual(self.frames, 5*self.session.completed)

    def test_actor_cannot_substitute_different_program_in_saved_choice(self):
        original = host.acquire
        def changed(initial, assigned, step, emit):return original(initial, program(-1), step, emit)
        before = self.frames
        with patch.object(host, "acquire", changed):
            with self.assertRaisesRegex(ValueError, "saved relocation choice"):self.execute()
        self.assertEqual(self.frames, before)

    def test_false_source_fit_rejected(self):
        def changed(index):
            row = deepcopy(self.events[index])
            if index == self.session._map[self.choice]:row["public_payload"]["controller"]["offset"][0] += .1
            return row
        before = self.frames
        with self.assertRaisesRegex(ValueError, "saved valid fit"):self.execute(changed)
        self.assertEqual(self.frames, before)

    def test_study_budget_reserves_full_operation_before_action(self):
        self.session.run_budget["maximum"] = self.session.completed+71;before = self.frames
        with self.assertRaisesRegex(ValueError, "whole-study budget"):self.execute()
        self.assertEqual(self.frames, before)

    def test_noise_tape_replacement_is_rejected_even_with_equal_values(self):
        original = self.session._agent_step
        def replaced(saved):
            result = original(saved);self.session.ctx["noise_rows"] = self.session.ctx["noise_rows"].copy()
            self.session.ctx["noise_rows"].flags.writeable = False;return result
        before = self.frames
        with patch.object(self.session, "_agent_step", replaced):
            with self.assertRaisesRegex(ValueError, "noise tape"):self.execute()
        self.assertEqual(self.frames-before, 5)

    def test_extra_controlled_reset_is_detected(self):
        original = self.session._agent_step
        def reset_after(saved):
            result = original(saved)
            with self.ledger.scope("CONTROLLED_RESET"):self.env.reset()
            return result
        with patch.object(self.session, "_agent_step", reset_after):
            with self.assertRaisesRegex(ValueError, "reset"):self.execute()
        self.assertEqual(self.native_resets, 2)


if __name__ == "__main__":unittest.main()
