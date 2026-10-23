"""Tiny native tests of the newly composed source-to-intervention path."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import boundary_prefix
from boundary_host import prepare_live_session, direct_continue
from session_adapter import execute_live_session
from src.analysis.paired_probe_host_v1 import physical_comparison
from tests.test_paired_probe_host_v1 import TinyEnv, TinyPolicy
from tests.test_short_probe_reference_host_v1 import fixture as base_fixture, TOY_RECEIPTS
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import fit


JOURNALS = []
ACTIVE_TEST = None


@contextmanager
def fixture(**kwargs):
    old_step = TinyEnv.step
    def finish24(env, action):
        value = old_step(env, action)
        value[-1]["success"] = env.calls >= 24
        return value
    with patch.object(TinyEnv, "step", finish24), base_fixture(**kwargs) as value:
        session, _, events = value
        try:
            yield value
        finally:
            JOURNALS.append({"test": ACTIVE_TEST, "events": deepcopy(events),
                "physical_rows": deepcopy(session.last_rows), "attempts": session.attempts,
                "returned": session.completed, "policy_queries": session.policy_queries})


def prepare(session, before, four=None):
    with patch.object(boundary_prefix, "infer_four", return_value=fit((.1, -.05)) if four is None else four), patch.object(
            boundary_prefix, "infer_operator", return_value=fit((-.08, .12))):
        return prepare_live_session(session, model(), before)


class BoundaryHostTests(unittest.TestCase):
    def setUp(self):
        global ACTIVE_TEST
        ACTIVE_TEST = self.id()

    def test_five_paths_share_step16_and_direct_loop_matches_continuation(self):
        witnessed, first, trajectories, ends = [], [], {}, {}
        for action in ("CONTINUE_CURRENT", "SWITCH_SAVED", "RUN_UNCORRECTED", "STOP", "DIRECT_CURRENT"):
            with self.subTest(action=action), fixture() as (session, before, events):
                source = prepare(session, before);self.assertTrue(source["public"]["ready"])
                witnessed.append(session.witness())
                p = source["public"];lookup = lambda index: deepcopy(next(r for r in events if r["sequence"] == index))
                if action == "DIRECT_CURRENT":
                    direct_continue(session, p["current_choice_sequence"], lookup)
                else:
                    result = execute_live_session(session, action, current_choice_sequence=p["current_choice_sequence"],
                        saved_choice_sequence=p["saved_choice_sequence"], lookup=lookup, reset_before=before)
                    self.assertEqual(result["host_completed_suffix_steps"], 0 if action == "STOP" else 8)
                self.assertEqual(session.ctx["calls"], 16 if action == "STOP" else 24)
                self.assertEqual(session.ledger.counts["reset_completed"], 1)
                self.assertEqual(session.ledger.counts["simulation_frames_completed"], 5 * session.ctx["calls"])
                self.assertEqual((session.captures, session.restores), (0, 0))
                trajectories[action] = [physical_comparison(r) for r in session.last_rows]
                ends[action] = session.witness()
                if action in ("CONTINUE_CURRENT", "SWITCH_SAVED", "RUN_UNCORRECTED"):
                    first.append(tuple(session.last_rows[16]["command"]))
        self.assertTrue(all(value == witnessed[0] for value in witnessed))
        self.assertEqual(len(set(first)), 3)
        self.assertEqual(trajectories["CONTINUE_CURRENT"], trajectories["DIRECT_CURRENT"])
        self.assertEqual(ends["CONTINUE_CURRENT"], ends["DIRECT_CURRENT"])

    def test_forged_source_command_rejected_before_ninth_step(self):
        with fixture() as (session, before, _), patch.object(boundary_prefix, "encode_controller", return_value=__import__('numpy').zeros(4)):
            with self.assertRaisesRegex(ValueError, "command differs"):
                prepare(session, before)
            self.assertEqual(session.ctx["calls"], 8)
            with self.assertRaises(ValueError): prepare(session, before)
            self.assertEqual(session.ledger.counts["simulation_frames_completed"], 40)

    def test_invalid_four_preserves_partial_prefix_without_adapter_use(self):
        with fixture() as (session, before, _):
            result = prepare(session, before, {"valid": False, "nfev": 2})
            self.assertFalse(result["public"]["ready"]);self.assertEqual(result["public"]["reason"], "INVALID_FOUR")
            self.assertEqual(session.completed, 4);self.assertEqual(session.policy_queries, 0)

    def test_budget_shortfall_rejected_before_any_control_step(self):
        with fixture(budget_maximum=499) as (session, before, _):
            with self.assertRaisesRegex(ValueError, "reserve"):
                prepare(session, before)
            self.assertEqual(session.completed, 0)

    def test_policy_hidden_physical_work_is_counted_and_rejected(self):
        with fixture() as (session, before, _):
            old = TinyPolicy.get_action
            def bad_policy(policy, observation):
                session.env.step([0., 0., 0., 0.])
                return old(policy, observation)
            with patch.object(TinyPolicy, "get_action", bad_policy), self.assertRaisesRegex(ValueError, "policy performed"):
                prepare(session, before)
            self.assertEqual(session.completed, 8)
            self.assertEqual(session.ledger.counts["simulation_frames_completed"], 45)


if __name__ == "__main__":
    unittest.main()
