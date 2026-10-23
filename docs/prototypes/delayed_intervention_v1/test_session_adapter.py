"""Native tiny-engine fixtures; no MetaWorld task or new scientific seed."""

from copy import deepcopy
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from controller import ExecutionFailure
from session_adapter import execute_live_session
from src.analysis.paired_probe_host_v1 import physical_comparison
from src.probe.operator_identification import encode_controller
from tests.test_short_probe_reference_host_v1 import fixture as base_fixture, reset_tiny, TOY_RECEIPTS


CURRENT = {"source": "ESTIMATED_AFFINE", "matrix_xy": [[1., 0.], [0., 1.]], "offset": [.12, -.08, 0., 0.]}
SAVED = {"source": "ESTIMATED_AFFINE", "matrix_xy": [[1., 0.], [0., 1.]], "offset": [-.2, .1, 0., 0.]}
ADAPTER_CASES = []
NATIVE_JOURNALS = []
ACTIVE_TEST_NAME = None


@contextmanager
def fixture(**kwargs):
    with base_fixture(**kwargs) as value:
        session, before, events = value
        try:
            yield value
        finally:
            NATIVE_JOURNALS.append({"test": ACTIVE_TEST_NAME,
                                   "fixture_injections": {k: v.__name__ if callable(v) else v for k, v in kwargs.items()},
                                   "events": deepcopy(events), "physical_rows": deepcopy(session.last_rows),
                                   "attempts": session.attempts, "returned": session.completed,
                                   "policy_queries": session.policy_queries})


def prepare(session, events):
    session.branch = {"role": "NATIVE_SOFTWARE_PREFIX", "future": 0, "program": "CONSTANT_CURRENT"}
    old = session._agent_emit("CHOICE", {"action": "RUN_FITTED", "at_calls": 0, "controller": SAVED})
    current = session._agent_emit("CHOICE", {"action": "RUN_FITTED", "at_calls": 0, "controller": CURRENT})
    for _ in range(10):
        direct_step(session, current)
    return current["sequence"], old["sequence"], lambda seq: deepcopy(next(r for r in events if r["sequence"] == seq))


def direct_step(session, current):
    raw = session.policy_query(session.public().observation)
    saved = session._agent_emit("COMMAND", {"at_calls": session.ctx["calls"], "phase": "POLICY",
                                "decision_sequence": current["sequence"], "command": encode_controller(current["controller"], raw).tolist(),
                                "raw_policy": raw.tolist(), "before": asdict(session.public())})
    return session._agent_step(saved)


def run(session, before, refs, action="CONTINUE_CURRENT", lookup=None):
    record = execute_live_session(session, action, current_choice_sequence=refs[0], saved_choice_sequence=refs[1],
                                  lookup=refs[2] if lookup is None else lookup, reset_before=before)
    ADAPTER_CASES.append(deepcopy(record))
    return record


class AdapterTests(unittest.TestCase):
    def setUp(self):
        global ACTIVE_TEST_NAME
        ACTIVE_TEST_NAME = self.id()

    def test_four_actions_start_from_same_native_boundary_and_use_saved_choices(self):
        witnesses, first_commands = [], []
        for action in ("CONTINUE_CURRENT", "SWITCH_SAVED", "RUN_UNCORRECTED", "STOP"):
            with self.subTest(action=action), fixture() as (session, before, events):
                refs = prepare(session, events)
                witnesses.append(session.witness())
                native_time = session.env.data.time
                record = run(session, before, refs, action)
                count = 0 if action == "STOP" else 2
                self.assertEqual(record["host_completed_suffix_steps"], count)
                self.assertEqual(session.ctx["calls"], 10 + count)
                self.assertEqual(session.ledger.counts["reset_completed"], 1)
                self.assertEqual(session.ledger.counts["simulation_frames_completed"], 5 * (10 + count))
                self.assertAlmostEqual(session.env.data.time - native_time, .0125 * count)
                self.assertEqual((session.captures, session.restores), (0, 0))
                self.assertFalse(set(json.dumps(record["actor"]).split('"')) & {"seed", "fault_oracle", "native_sha256", "future"})
                by_sequence = {r["sequence"]: r for r in events}
                for row in session.last_rows[10:]:
                    saved = by_sequence[row["global_command_sequence"]]
                    self.assertEqual(saved["event"], "DELAYED_AGENT_EVENT")
                    self.assertEqual(saved["public_payload"]["command"], row["command"])
                    self.assertLess(saved["saved_ns"], row["execution_started_ns"])
                if count:
                    first_commands.append(tuple(session.last_rows[10]["command"]))
                else:
                    self.assertEqual(record["actor"]["deadline_loss"], 500)
        self.assertTrue(all(witness == witnesses[0] for witness in witnesses))
        self.assertEqual(len(set(first_commands)), 3)

    def test_continue_matches_independent_direct_loop_in_every_physical_row(self):
        outcomes = []
        for bridge in (True, False):
            with fixture() as (session, before, events):
                refs = prepare(session, events)
                if bridge:
                    run(session, before, refs)
                else:
                    current = refs[2](session._map[refs[0]])["public_payload"]
                    while session.alive():
                        direct_step(session, current)
                outcomes.append(([physical_comparison(r) for r in session.last_rows], session.witness()))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_reuse_is_rejected_without_more_physical_work(self):
        with fixture() as (session, before, events):
            refs = prepare(session, events);run(session, before, refs, "STOP")
            ledger = session.ledger.snapshot()
            with self.assertRaisesRegex(ValueError, "already consumed"):
                run(session, before, refs)
            self.assertEqual(session.ledger.snapshot(), ledger)

    def test_wrong_current_or_foreign_choice_rejected_before_new_step(self):
        for mode in ("wrong_current", "foreign"):
            with fixture() as (session, before, events):
                refs = prepare(session, events)
                bad = (refs[1] if mode == "wrong_current" else 99999, refs[1], refs[2])
                with self.assertRaises(ValueError):run(session, before, bad)
                self.assertEqual(session.completed, 10)

    def test_current_record_must_explain_actual_last_command(self):
        with fixture() as (session, before, events):
            refs = prepare(session, events)
            def altered(seq):
                row = refs[2](seq)
                if seq == session._map[refs[0]]:row["public_payload"]["controller"]["offset"][0] = .7
                return row
            with self.assertRaisesRegex(ValueError, "actual last command"):
                run(session, before, refs, lookup=altered)
            self.assertEqual(session.completed, 10)

    def test_oracle_controller_is_rejected_before_actor(self):
        with fixture() as (session, before, events):
            refs = prepare(session, events)
            def altered(seq):
                row = refs[2](seq)
                if seq == session._map[refs[1]]:row["public_payload"]["controller"]["source"] = "ORACLE_EVALUATOR"
                return row
            with self.assertRaisesRegex(ValueError, "oracle controller"):
                run(session, before, refs, lookup=altered)
            self.assertEqual(session.completed, 10)

    def test_unresolved_source_command_and_changed_noise_are_rejected(self):
        for mode in ("pending", "noise"):
            with fixture() as (session, before, events):
                refs = prepare(session, events)
                if mode == "pending":session._pending = {"unexecuted": True}
                else:
                    rows = session.ctx["noise_rows"].copy();rows[11] = 0;rows.flags.writeable = False;session.ctx["noise_rows"] = rows
                with self.assertRaises(ValueError):run(session, before, refs)
                self.assertEqual(session.completed, 10)

    def test_invalid_reset_receipt_and_missing_study_reserve(self):
        for mode in ("reset", "budget"):
            with fixture() as (session, before, events):
                refs = prepare(session, events)
                if mode == "reset":before = session.ledger.snapshot()
                else:session.run_budget["maximum"] = 499
                with self.assertRaises(ValueError):run(session, before, refs)
                self.assertEqual(session.completed, 10)

    def test_host_independently_rejects_actor_command_substitution(self):
        with fixture() as (session, before, events):
            refs = prepare(session, events)
            with patch("controller.encode_controller", return_value=np.zeros(4, np.float32)):
                with self.assertRaises(ExecutionFailure):run(session, before, refs, "SWITCH_SAVED")
            self.assertEqual(session.completed, 10)
            self.assertEqual(events[-1]["event"], "DELAYED_INTERVENTION_ABORTED")
            self.assertEqual(events[-1]["host_step_attempts"], 0)

    def test_extra_native_failure_preserves_unreturned_frames(self):
        def fail_at_eleven(env, ledger):
            if env.calls == 11:raise RuntimeError("fixture error after native step")
        with fixture(step_hook=fail_at_eleven) as (session, before, events):
            refs = prepare(session, events)
            with self.assertRaises(ExecutionFailure):run(session, before, refs)
            aborted = events[-1]
            self.assertEqual(aborted["event"], "DELAYED_INTERVENTION_ABORTED")
            self.assertEqual((aborted["host_step_attempts"], aborted["host_returned_steps"], aborted["unreturned_host_attempts"]), (1, 0, 1))
            self.assertEqual(aborted["ledger_after"]["counts"]["simulation_frames_completed"], 55)
            self.assertEqual(aborted["actor_snapshot"]["unconfirmed_step_attempts"], 1)
            with self.assertRaises(ValueError):run(session, before, refs)

    def test_mid_trajectory_reset_detected_and_cost_preserved(self):
        def reset_at_eleven(env, ledger):
            if env.calls == 11:ledger.reset_call(reset_tiny, env)
        with fixture(step_hook=reset_at_eleven) as (session, before, events):
            refs = prepare(session, events)
            with self.assertRaises(ExecutionFailure):run(session, before, refs)
            aborted = events[-1]
            self.assertEqual(aborted["ledger_after"]["counts"]["reset_completed"], 2)
            self.assertEqual(aborted["ledger_after"]["counts"]["simulation_frames_completed"], 55)
            self.assertTrue(aborted["physical_completeness_unverified"])

    def test_policy_side_effect_native_step_is_rejected_before_command(self):
        with fixture() as (session, before, events):
            refs = prepare(session, events);original = session.policy_query
            def altered(obs):
                raw = original(obs)
                session.env.step(np.zeros(4, np.float32))
                return raw
            session.policy_query = altered
            with self.assertRaises(ExecutionFailure):run(session, before, refs)
            aborted = events[-1]
            self.assertEqual(aborted["host_step_attempts"], 0)
            self.assertEqual(aborted["ledger_after"]["counts"]["simulation_frames_completed"], 55)


if __name__ == "__main__":
    unittest.main(verbosity=2)
