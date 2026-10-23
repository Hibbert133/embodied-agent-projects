"""Tiny native software fixtures, not MetaWorld task/parameter qualification."""
from contextlib import contextmanager
from dataclasses import asdict
import copy
import io
import unittest
from unittest.mock import patch

import mujoco
import numpy as np

from src.analysis.capsule_record_json_v2 import JsonJournal
from src.analysis.paired_probe_host_v1 import ProbeSession, physical_comparison
from src.analysis.short_probe_reference_host_v1 import execute_short_session
from src.probe import short_probe_execution_reference_v1 as actor
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.chronological_cache_reference import BALANCED8
from src.probe.cold_start_response import ColdPrefix
from src.probe.operator_identification import identity_controller
from src.probe.short_probe_design_reference_v1 import design_four
from tests.test_paired_probe_host_v1 import TinyEnv, TinyPolicy
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import fit


TOY_RECEIPTS = []


def reset_tiny(env):
    mujoco.mj_resetData(env.model, env.data);env.calls = 0
    return np.zeros(39), {}


@contextmanager
def fixture(*, step_hook=None, extra_native_frame=False, budget_maximum=10000):
    text = io.StringIO();journal = JsonJournal(text, {'manifest_id':'SOFTWARE_NATIVE_TINY_ONLY'})
    events = []
    def emit(event, payload):
        row = journal.emit(event, payload);events.append(row)
        return row
    ledger = LifecycleLedger(emit, 100000);budget = {'completed':0, 'maximum':budget_maximum}
    env = TinyEnv();native_frames = 0;policy_calls = 0
    original_simulation = TinyEnv.do_simulation;original_step = TinyEnv.step;native_step = mujoco.mj_step
    original_policy = TinyPolicy.get_action
    def counted_policy(current, observation):
        nonlocal policy_calls
        policy_calls += 1
        return original_policy(current, observation)
    def counted_native(*args, **kwargs):
        nonlocal native_frames
        value = native_step(*args, **kwargs)
        native_frames += int(kwargs.get('nstep', args[2] if len(args) > 2 else 1))
        return value
    def physical_simulation(current, ctrl, n_frames):
        return original_simulation(current, ctrl, n_frames+int(extra_native_frame))
    def simulate(current, ctrl, n_frames):
        return ledger.simulation_call(physical_simulation, current, ctrl, n_frames)
    def environment_step(current, action):
        value = original_step(current, action)
        if step_hook is not None:
            step_hook(current, ledger)
        return value
    with patch.object(mujoco, 'mj_step', counted_native), patch.object(TinyEnv, 'do_simulation', simulate), patch.object(TinyEnv, 'step', environment_step), patch.object(TinyPolicy, 'get_action', counted_policy):
        before_reset = ledger.snapshot()
        with ledger.scope('CONTROLLED_RESET'):
            observation, _ = ledger.reset_call(reset_tiny, env)
        fault = {'matrix_xy':[[1, 0], [0, 1]], 'bias_xy':[.1, -.06], 'deadzone_xy':[0, 0]}
        session = ProbeSession(env, TinyPolicy(), observation, 'push-v3', 700015, fault, emit, ledger, budget)
        try:
            yield session, before_reset, events
        finally:
            TOY_RECEIPTS.append({'ledger':ledger.snapshot(), 'native_successful_requested_frames':native_frames,
                'host_step_attempts':session.attempts, 'host_returned_steps':session.completed,
                'actual_tiny_policy_calls':policy_calls,
                'captures':session.captures, 'restores':session.restores})


class ShortProbeReferenceHostTest(unittest.TestCase):
    def setUp(self):
        self.model = model();self.design = design_four(self.model)

    def run_reference(self, session, before, method):
        return execute_short_session(session, method, None if method == 'NO_PROBE' else self.model, before,
                                     design=self.design if method in actor.DOPT_METHODS else None)

    def test_seven_native_paths_preserve_reset_clock_frames_and_saved_command_consumption(self):
        with patch.object(actor, 'infer_four', return_value=fit()), patch.object(actor, 'infer_operator', return_value=fit()), patch('src.analysis.paired_probe_host_v1.capture', side_effect=AssertionError('copy forbidden')), patch('src.analysis.paired_probe_host_v1.restore', side_effect=AssertionError('restore forbidden')):
            for method in actor.METHODS:
                with self.subTest(method=method), fixture() as (session, before, events):
                    summary, result = self.run_reference(session, before, method)
                    self.assertTrue(summary['outcome']['success']);self.assertEqual(session.ctx['calls'], 12)
                    self.assertEqual(summary['outcome'], result['outcome'])
                    self.assertEqual(session.ledger.counts['reset_completed'], 1)
                    self.assertEqual(session.ledger.counts['simulation_frames_completed'], 60)
                    self.assertEqual(session.run_budget['completed'], 12)
                    self.assertEqual(summary['host_command_verifications'], 12)
                    self.assertFalse(summary['complete_hidden_state_qualification'])
                    self.assertEqual((session.captures, session.restores), (0, 0))
                    byseq = {row['sequence']:row for row in events}
                    for row in session.last_rows:
                        saved = byseq[row['global_command_sequence']]
                        self.assertEqual(saved['public_payload']['command'], row['command'])
                        self.assertLess(saved['saved_ns'], row['execution_started_ns'])
                        self.assertAlmostEqual(row['simulation_time_after']-row['simulation_time_before'], .0125)
                    for row in events:
                        if row['event'] == 'AGENT_EVENT':
                            self.assertFalse(set(row['public_payload']) & {'seed', 'fault_oracle', 'native_sha256', 'future', 'role'})

    def test_same_extra_native_prefix_keeps_four_fit_or_uses_eight_fit_as_declared(self):
        runs = []
        with patch.object(actor, 'infer_four', return_value=fit()), patch.object(actor, 'infer_operator', return_value=fit((-.15, .1))):
            for method in ('DOPT4_KEEP_AT8', 'DOPT8_UPDATE'):
                with fixture() as (session, before, events):
                    summary, result = self.run_reference(session, before, method)
                    runs.append((copy.deepcopy(session.last_rows), result))
        self.assertEqual([physical_comparison(row) for row in runs[0][0][:8]], [physical_comparison(row) for row in runs[1][0][:8]])
        self.assertNotEqual(runs[0][0][8]['command'], runs[1][0][8]['command'])
        self.assertEqual(runs[0][1]['fits'][0]['at_calls'], 4)
        self.assertEqual(runs[1][1]['fits'][0]['at_calls'], 8)

    def test_session_cannot_be_reused_after_one_full_program(self):
        with fixture() as (session, before, events):
            self.run_reference(session, before, 'NO_PROBE')
            snapshot = session.ledger.snapshot();length = len(events)
            with self.assertRaises(ValueError):self.run_reference(session, before, 'NO_PROBE')
            self.assertEqual(session.ledger.snapshot(), snapshot);self.assertEqual(len(events), length)

    def test_reset_receipt_and_no_extra_initial_simulation_are_required(self):
        with fixture() as (session, before, events):
            with self.assertRaises(ValueError):self.run_reference(session, session.ledger.snapshot(), 'NO_PROBE')
            self.assertEqual(session.ctx['calls'], 0)
        with fixture() as (session, before, events):
            with session.ledger.scope('CONTROL'):
                session.env.step(np.zeros(4))
            with self.assertRaises(ValueError):self.run_reference(session, before, 'NO_PROBE')
            self.assertEqual(session.ctx['calls'], 0)
            self.assertEqual(session.ledger.counts['simulation_frames_completed'], 5)

    def test_insufficient_study_reserve_and_replaced_private_noise_fail_before_control(self):
        with fixture(budget_maximum=499) as (session, before, events):
            with self.assertRaises(ValueError):self.run_reference(session, before, 'NO_PROBE')
            self.assertEqual(session.attempts, 0)
        with fixture() as (session, before, events):
            replaced = session.ctx['noise_rows'].copy();replaced[20] = 0;replaced.flags.writeable = False
            session.ctx['noise_rows'] = replaced
            with self.assertRaises(ValueError):self.run_reference(session, before, 'NO_PROBE')
            self.assertEqual(session.attempts, 0)

    def test_exception_after_native_simulation_preserves_unreturned_cost_and_prevents_retry(self):
        def fail_after_two(env, ledger):
            if env.calls == 2:
                raise RuntimeError('artificial failure after native frames')
        with fixture(step_hook=fail_after_two) as (session, before, events):
            with self.assertRaisesRegex(RuntimeError, 'after native frames'):
                self.run_reference(session, before, 'NO_PROBE')
            aborted = events[-1];self.assertEqual(aborted['event'], 'SHORT_REFERENCE_ABORTED')
            self.assertEqual((session.attempts, session.completed), (2, 1))
            self.assertEqual(aborted['unreturned_step_attempts'], 1)
            self.assertEqual(aborted['returned_physical_rows'], 1)
            self.assertEqual(aborted['ledger_after']['counts']['simulation_frames_completed'], 10)
            self.assertEqual(aborted['policy_query_attempts'], 2)
            self.assertIsNone(aborted['optimizer_nfev']);self.assertFalse(aborted['actor_outcome_available'])
            self.assertTrue(aborted['native_transition_completeness_unverified'])
            with self.assertRaises(ValueError):self.run_reference(session, before, 'NO_PROBE')

    def test_native_time_mismatch_aborts_and_marks_incomplete_transition_knowledge(self):
        with fixture(extra_native_frame=True) as (session, before, events):
            with self.assertRaisesRegex(ValueError, 'five-frame'):
                self.run_reference(session, before, 'NO_PROBE')
            aborted = events[-1]
            self.assertEqual(aborted['event'], 'SHORT_REFERENCE_ABORTED')
            self.assertTrue(aborted['native_transition_completeness_unverified'])
            self.assertAlmostEqual(aborted['native_time_after']-aborted['native_time_before'], .015)
            self.assertEqual(aborted['ledger_after']['counts']['simulation_frames_completed'], 5)

    def test_mid_trajectory_reset_is_rejected_and_its_actual_fee_is_preserved(self):
        def reset_after_two(env, ledger):
            if env.calls == 2:
                ledger.reset_call(reset_tiny, env)
        with fixture(step_hook=reset_after_two) as (session, before, events):
            with self.assertRaisesRegex(ValueError, 'five-frame'):
                self.run_reference(session, before, 'NO_PROBE')
            aborted = events[-1]
            self.assertEqual(aborted['event'], 'SHORT_REFERENCE_ABORTED')
            self.assertEqual(aborted['ledger_after']['counts']['reset_completed'], 2)
            self.assertEqual(aborted['ledger_after']['counts']['simulation_frames_completed'], 10)
            self.assertTrue(aborted['native_transition_completeness_unverified'])

    def test_host_rejects_saved_command_that_differs_from_its_saved_controller(self):
        def broken_actor(method, task, initial, model, policy, step, emit, **kwargs):
            emit('PROGRAM', {'method':method, 'task':task, 'initial':asdict(initial)})
            choice = emit('CHOICE', {'action':'RUN_IDENTITY', 'at_calls':0, 'controller':identity_controller()})
            raw = policy(np.asarray(initial.observation)).tolist()
            saved = emit('COMMAND', {'at_calls':0, 'phase':'POLICY', 'decision_sequence':choice['sequence'],
                'command':[.1, 0, 0, 0], 'raw_policy':raw, 'before':asdict(initial)})
            step(saved)
            raise AssertionError('host should have rejected substitution')
        with fixture() as (session, before, events), patch('src.analysis.short_probe_reference_host_v1.execute_reference', broken_actor):
            with self.assertRaisesRegex(ValueError, 'differs from saved'):
                self.run_reference(session, before, 'NO_PROBE')
            self.assertEqual(session.attempts, 0)
            self.assertEqual(events[-1]['policy_query_attempts'], 1)

    def test_host_rejects_fitted_evidence_not_taken_from_its_actual_probe(self):
        def broken_actor(method, task, initial, model, policy, step, emit, **kwargs):
            emit('PROGRAM', {'method':method, 'task':task, 'initial':asdict(initial)})
            choice = emit('CHOICE', {'action':'PROBE_FOUR', 'at_calls':0, 'program':[list(row) for row in BALANCED8[:4]]})
            current = initial;commands = [];observed = []
            for index, command in enumerate(choice['program']):
                saved = emit('COMMAND', {'at_calls':index, 'phase':'FIXED_PROBE', 'decision_sequence':choice['sequence'],
                    'command':command, 'raw_policy':None, 'before':asdict(current)})
                current = step(saved);commands.append(tuple(command));observed.append(current.observation)
            altered = list(observed[-1]);altered[0] += .1;observed[-1] = tuple(altered)
            prefix = asdict(ColdPrefix(task, initial.observation, tuple(commands), tuple(observed), True))
            emit('FIT_RESULT', {'at_calls':4, 'prefix':prefix, 'prefix_evidence_sha256':actor.digest(prefix), 'fit':fit()})
            raise AssertionError('host should have rejected unobserved data')
        with fixture() as (session, before, events), patch('src.analysis.short_probe_reference_host_v1.execute_reference', broken_actor):
            with self.assertRaisesRegex(ValueError, 'actual observed probe'):
                self.run_reference(session, before, 'BALANCED4_UPDATE')
            self.assertEqual(session.completed, 4)
            self.assertEqual(events[-1]['ledger_after']['counts']['simulation_frames_completed'], 20)

    def test_post_execution_counter_mismatch_retains_unvalidated_actor_outcome(self):
        with fixture() as (session, before, events):
            session.policy_query = lambda observation:session.policy.get_action(observation)
            with self.assertRaisesRegex(ValueError, 'public outcome'):
                self.run_reference(session, before, 'NO_PROBE')
            aborted = events[-1]
            self.assertTrue(aborted['actor_outcome_available'])
            self.assertEqual(aborted['unvalidated_reported_actor_outcome']['policy_queries'], 12)
            self.assertEqual(aborted['policy_query_attempts'], 0)
            self.assertEqual(aborted['ledger_after']['counts']['simulation_frames_completed'], 60)


if __name__ == '__main__':
    unittest.main()
