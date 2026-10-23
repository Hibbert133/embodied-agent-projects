"""Synthetic contract tests only; no MetaWorld environment is created."""

from copy import deepcopy
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import json
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from controller import Boundary, ControllerSnapshot, ExecutionFailure, SingleIntervention, StepReceipt
from src.probe.continuous import StepObservation


CURRENT = ControllerSnapshot(((1., 0.), (0., 1.)), (.1, .2))
SAVED = ControllerSnapshot(((0., -1.), (1., 0.)), (0., 0.))
TEST_ACTIVITY = Counter()


def observation(x=.4, *, success=False, terminated=False, truncated=False):
    return StepObservation((x, .5, .2, *([0.] * 36)), terminated, truncated, success)


class Journal:
    def __init__(self):
        self.records = []
        self.returned = []

    def __call__(self, kind, payload):
        result = {**deepcopy(payload), "sequence": len(self.records), "saved_ns": 1000 + len(self.records)}
        self.records.append({"kind": kind, "payload": deepcopy(result)})
        self.returned.append(result)
        return result


class Host:
    def __init__(self, boundary, journal, *, finish_after=2):
        self.current, self.completed = boundary.current, boundary.completed_steps
        self.journal, self.finish_after = journal, finish_after
        self.commands = []
        self.before = []

    def __call__(self, saved):
        TEST_ACTIVITY["host_callback_attempts"] += 1
        # A host checks its own ledger BEFORE any physical action.
        if saved["at_calls"] != self.completed or saved["before"] != json.loads(json.dumps(asdict(self.current))):
            raise ValueError("stale host boundary")
        if self.journal.records[-1] != {"kind": "COMMAND", "payload": saved}:
            raise ValueError("unacknowledged command")
        before = self.current
        command = tuple(saved["command"])
        self.before.append(before)
        self.commands.append(command)
        TEST_ACTIVITY["synthetic_host_transitions"] += 1
        position = list(before.observation)
        for i in range(3):
            position[i] += .01 * command[i]
        self.completed += 1
        self.current = StepObservation(tuple(position), False, False, len(self.commands) == self.finish_after)
        return StepReceipt(before, command, self.current, self.completed)


def setup(*, steps=100, saved=SAVED, current=None, finish_after=2, policy=None, emit=None):
    boundary = Boundary("push-v3", steps, observation() if current is None else current, CURRENT, saved)
    journal = Journal() if emit is None else emit
    host = Host(boundary, journal, finish_after=finish_after)
    agent = SingleIntervention(boundary, policy=policy or (lambda obs: np.array([.2, -.1, -.3, 0.], np.float32)),
                               step=host, emit=journal)
    return agent, host, journal


class ExecutorTests(unittest.TestCase):
    def test_legal_choices_change_actual_sent_commands(self):
        expected = {"CONTINUE_CURRENT": [.3, .1], "SWITCH_SAVED": [.1, .2], "RUN_UNCORRECTED": [.2, -.1]}
        final_positions = []
        for action, xy in expected.items():
            with self.subTest(action=action):
                agent, host, journal = setup()
                result = agent.execute(action)
                np.testing.assert_allclose(host.commands[0][:2], xy, atol=1e-7, rtol=0)
                self.assertEqual(result["choice"]["action_id"], action)
                self.assertEqual(result["completed_steps"], 102)
                final_positions.append(host.current.observation[:2])
        self.assertEqual(len(set(final_positions)), 3)

    def test_switch_starts_at_live_nonzero_state_without_rewind(self):
        agent, host, _ = setup()
        result = agent.execute("SWITCH_SAVED")
        self.assertEqual(host.before[0], observation())
        self.assertEqual(result["charged_steps"], 102)
        self.assertEqual(result["remaining_budget"], 398)
        self.assertEqual(host.before[1].observation[0], observation().observation[0] + .01 * host.commands[0][0])

    def test_host_rejects_stale_boundary_before_motion(self):
        agent, host, _ = setup()
        host.completed += 1
        with self.assertRaises(ExecutionFailure):
            agent.execute("SWITCH_SAVED")
        self.assertFalse(host.commands)

    def test_ending_receipt_stops_further_queries(self):
        for flag in ["success", "terminated", "truncated"]:
            agent, host, _ = setup(finish_after=99)
            def ending(saved, name=flag):
                receipt = host(saved)
                fields = {"success": False, "terminated": False, "truncated": False}
                fields[name] = True
                after = StepObservation(receipt.after.observation, **fields)
                return StepReceipt(receipt.before, receipt.command, after, receipt.completed_steps)
            agent._step = ending
            result = agent.execute("SWITCH_SAVED")
            self.assertEqual((len(host.commands), result["policy_queries_attempted"], result["completed_steps"]), (1, 1, 101))
            self.assertEqual(result["deadline_loss"], 101 if flag == "success" else 500)

    def test_saved_choice_precedes_each_command_and_receipt(self):
        agent, host, journal = setup()
        result = agent.execute("SWITCH_SAVED")
        self.assertEqual([r["kind"] for r in journal.records], ["CHOICE", "COMMAND", "STEP_RESULT", "COMMAND", "STEP_RESULT"])
        self.assertEqual(result["events"], journal.records)
        self.assertTrue(all(r["payload"]["decision_sequence"] == 0 for r in journal.records if r["kind"] == "COMMAND"))

    def test_stop_keeps_failure_penalty_and_performs_no_action(self):
        agent, host, _ = setup()
        result = agent.execute("STOP")
        self.assertEqual(result["status"], "STOPPED")
        self.assertEqual((result["deadline_loss"], result["step_attempts"], result["policy_queries_attempted"]), (500, 0, 0))
        self.assertFalse(host.commands)

    def test_missing_saved_controller_rejected_before_callbacks(self):
        agent, host, journal = setup(saved=None)
        self.assertNotIn("SWITCH_SAVED", agent.available_actions())
        with self.assertRaises(ValueError):
            agent.execute("SWITCH_SAVED")
        self.assertFalse(journal.records)
        self.assertFalse(host.commands)

    def test_unknown_and_probe_actions_rejected(self):
        for action in ["REQUEST_PROBE", "REFIT_COLD_MODEL", "ORACLE_EVALUATOR", "", 1, None]:
            agent, host, journal = setup()
            with self.subTest(action=action), self.assertRaises(ValueError):
                agent.execute(action)
            self.assertFalse(journal.records)

    def test_repeated_intervention_rejected(self):
        agent, host, _ = setup()
        agent.execute("CONTINUE_CURRENT")
        with self.assertRaises(ValueError):
            agent.execute("SWITCH_SAVED")
        self.assertEqual(len(host.commands), 2)
        self.assertEqual(agent.available_actions(), ())

    def test_one_remaining_step_is_only_one_step(self):
        agent, host, _ = setup(steps=499, finish_after=9)
        result = agent.execute("SWITCH_SAVED")
        self.assertEqual((len(host.commands), result["charged_steps"], result["remaining_budget"]), (1, 500, 0))
        self.assertEqual(result["deadline_loss"], 500)

    def test_no_remaining_budget_rejects_execution(self):
        agent, host, journal = setup(steps=500)
        self.assertEqual(agent.available_actions(), ("STOP",))
        with self.assertRaises(ValueError):
            agent.execute("CONTINUE_CURRENT")
        self.assertFalse(host.commands)
        self.assertFalse(journal.records)

    def test_early_success_terminated_and_truncated_never_step(self):
        for field in ["success", "terminated", "truncated"]:
            agent, host, _ = setup(current=observation(**{field: True}))
            self.assertEqual(agent.available_actions(), ("STOP",))
            result = agent.execute("STOP")
            self.assertFalse(host.commands)
            self.assertEqual(result["deadline_loss"], 100 if field == "success" else 500)

    def test_policy_input_mutation_does_not_change_live_boundary(self):
        def policy(obs):
            obs[:] = 123
            return [.2, -.1, -.3, 0.]
        agent, host, _ = setup(policy=policy)
        agent.execute("RUN_UNCORRECTED")
        self.assertEqual(host.before[0], observation())

    def test_callback_owned_ack_cannot_redirect_saved_choice(self):
        agent, host, journal = setup()
        def policy(obs):
            journal.returned[0]["candidate_map"]["SWITCH_SAVED"]["offset"][0] = .9
            return [.2, -.1, -.3, 0.]
        agent._policy = policy
        result = agent.execute("SWITCH_SAVED")
        self.assertAlmostEqual(host.commands[0][0], .1, places=7)
        self.assertEqual(result["choice"]["candidate_map"]["SWITCH_SAVED"]["offset"][0], 0)

    def test_bounded_commands_preserve_nominal_z_and_gripper(self):
        agent, host, _ = setup(policy=lambda obs: [2., -3., 4., -4.])
        agent.execute("CONTINUE_CURRENT")
        np.testing.assert_allclose(host.commands[0], [1., -.8, 1., -1.], atol=1e-7, rtol=0)

    def test_bad_policy_outputs_fail_before_physical_attempt(self):
        for raw in [[float("nan"), 0, 0, 0], [float("inf"), 0, 0, 0], [1e100, 0, 0, 0], [True] * 4, [0] * 3, [[0]] * 4]:
            agent, host, _ = setup(policy=lambda obs, value=raw: value)
            with self.subTest(raw=raw), self.assertRaises(ExecutionFailure) as caught:
                agent.execute("SWITCH_SAVED")
            self.assertEqual(caught.exception.reason, "POLICY_OR_COMMAND_INVALID")
            self.assertFalse(host.commands)
            self.assertEqual(caught.exception.snapshot["step_attempts"], 0)

    def test_policy_exception_is_not_retried(self):
        def bad(obs):
            raise RuntimeError("synthetic")
        agent, host, _ = setup(policy=bad)
        with self.assertRaises(ExecutionFailure) as caught:
            agent.execute("CONTINUE_CURRENT")
        self.assertEqual(caught.exception.snapshot["policy_queries_attempted"], 1)
        self.assertEqual(caught.exception.snapshot["policy_queries_completed"], 0)
        with self.assertRaises(ValueError):
            agent.execute("CONTINUE_CURRENT")

    def test_step_exception_is_charged_unconfirmed_and_not_retried(self):
        agent, host, _ = setup()
        def bad(saved):
            raise RuntimeError("physical outcome not known")
        agent._step = bad
        with self.assertRaises(ExecutionFailure) as caught:
            agent.execute("SWITCH_SAVED")
        s = caught.exception.snapshot
        self.assertEqual((s["charged_steps"], s["completed_steps"], s["unconfirmed_step_attempts"]), (101, 100, 1))
        with self.assertRaises(ValueError):
            agent.execute("SWITCH_SAVED")

    def test_receipt_mismatches_abort_after_one_attempt(self):
        for kind in ["before", "command", "count", "schema"]:
            agent, host, _ = setup()
            def altered(saved, field=kind):
                real = host(saved)
                if field == "schema":
                    return asdict(real)
                return StepReceipt(observation(.9) if field == "before" else real.before,
                                   (0., 0., 0., 0.) if field == "command" else real.command,
                                   real.after, real.completed_steps + (1 if field == "count" else 0))
            agent._step = altered
            with self.subTest(kind=kind), self.assertRaises(ExecutionFailure) as caught:
                agent.execute("CONTINUE_CURRENT")
            self.assertEqual(caught.exception.reason, "STEP_RECEIPT_MISMATCH")
            self.assertEqual((len(host.commands), caught.exception.snapshot["accepted_step_receipts"]), (1, 0))

    def test_journal_write_failures_preserve_attempt_accounting(self):
        for fail_kind, attempted, accepted in [("CHOICE", 0, 0), ("COMMAND", 0, 0), ("STEP_RESULT", 1, 1)]:
            agent, host, journal = setup()
            def emit(kind, payload, target=fail_kind):
                if kind == target:
                    raise OSError("synthetic journal failure")
                return journal(kind, payload)
            agent._emit = emit
            with self.subTest(fail_kind=fail_kind), self.assertRaises(ExecutionFailure) as caught:
                agent.execute("SWITCH_SAVED")
            s = caught.exception.snapshot
            self.assertEqual((s["step_attempts"], s["accepted_step_receipts"]), (attempted, accepted))
            self.assertEqual(caught.exception.reason, "JOURNAL_CALLBACK_FAILED")

    def test_malformed_journal_ack_never_starts_execution(self):
        for kind in ["action", "nested", "bool_number", "extra", "sequence", "time", "nonjson"]:
            agent, host, journal = setup()
            def altered(event, payload, field=kind):
                answer = journal(event, payload)
                if field == "action": answer["action_id"] = "RUN_UNCORRECTED"
                if field == "nested": answer["candidate_map"]["SWITCH_SAVED"]["offset"][0] = .1
                if field == "bool_number": answer["candidate_map"]["SWITCH_SAVED"]["matrix_xy"][1][0] = True
                if field == "extra": answer["oracle"] = 1
                if field == "sequence": answer["sequence"] = True
                if field == "time": answer["saved_ns"] = -1
                if field == "nonjson": answer["task"] = object()
                return answer
            agent._emit = altered
            with self.subTest(kind=kind), self.assertRaises(ExecutionFailure) as caught:
                agent.execute("SWITCH_SAVED")
            self.assertEqual(caught.exception.reason, "JOURNAL_ACK_MISMATCH")
            self.assertFalse(host.commands)

    def test_journal_clock_regression_before_command_aborts(self):
        agent, host, journal = setup()
        def altered(kind, payload):
            answer = journal(kind, payload)
            if kind == "COMMAND": answer["saved_ns"] = 0
            return answer
        agent._emit = altered
        with self.assertRaises(ExecutionFailure):
            agent.execute("CONTINUE_CURRENT")
        self.assertFalse(host.commands)

    def test_reentrant_execution_is_rejected(self):
        agent, host, journal = setup()
        def emit(kind, payload):
            with self.assertRaises(ValueError):
                agent.execute("RUN_UNCORRECTED")
            return journal(kind, payload)
        agent._emit = emit
        agent.execute("SWITCH_SAVED")
        self.assertEqual(len(host.commands), 2)

    def test_snapshot_mutation_does_not_modify_executor(self):
        agent, host, _ = setup()
        result = agent.execute("SWITCH_SAVED")
        result["choice"]["action_id"] = "STOP"
        result["events"].clear()
        self.assertEqual(agent.snapshot()["choice"]["action_id"], "SWITCH_SAVED")
        self.assertEqual(len(agent.snapshot()["events"]), 5)


class SchemaTests(unittest.TestCase):
    def test_ordinary_roundtrip(self):
        b = Boundary("push-v3", 100, observation(), CURRENT, SAVED)
        self.assertEqual(Boundary.from_mapping(asdict(b)), b)

    def test_oracle_and_unknown_fields_rejected_at_every_level(self):
        for level in ["root", "current", "current_controller", "saved_controller"]:
            for key in ["seed", "rng_state", "perturbation", "future_result"]:
                value = asdict(Boundary("push-v3", 100, observation(), CURRENT, SAVED))
                target = value if level == "root" else value[level]
                target[key] = "forbidden"
                with self.subTest(level=level, key=key), self.assertRaises(ValueError):
                    Boundary.from_mapping(value)

    def test_bad_steps_and_observation_shapes_rejected(self):
        for count in [-1, 501, 1., True]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                Boundary("push-v3", count, observation(), CURRENT, SAVED)
        with self.assertRaises(ValueError):
            Boundary("push-v3", 100, StepObservation((0.,) * 3, False, False, False), CURRENT)

    def test_bool_nan_and_nested_controller_values_rejected(self):
        for value in [True, float("nan"), float("inf"), {"oracle": 1}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ControllerSnapshot(((1., 0.), (0., 1.)), (value, 0.))

    def test_input_lists_cannot_mutate_frozen_controller(self):
        matrix, offset = [[1., 0.], [0., 1.]], [0., 0.]
        controller = ControllerSnapshot(matrix, offset)
        matrix[0][0], offset[0] = 9., 9.
        self.assertEqual(controller.matrix_xy[0][0], 1.)
        self.assertEqual(controller.offset_xy[0], 0.)


if __name__ == "__main__":
    unittest.main(verbosity=2)
