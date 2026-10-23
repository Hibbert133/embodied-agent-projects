"""Tiny native journal fixtures; no MetaWorld tasks or physical model qualification.

Factory/reset calls execute actual TinyEnv simulation requests. Estimators and
policy identity are explicitly stubbed for transcript/control-flow coverage.
"""
from contextlib import ExitStack
from copy import deepcopy
import io
import unittest
from unittest.mock import patch

import mujoco
import numpy as np

from src.analysis.capsule_record_json_v2 import JsonJournal
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.analysis.short_probe_reference_host_v1 import execute_short_session
from src.analysis import short_probe_journal_audit_v1 as audit
from src.analysis import short_probe_public_audit_v1 as public
from src.probe import short_probe_execution_reference_v1 as runtime
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.short_probe_design_reference_v1 import design_four
from tests.test_paired_probe_host_v1 import TinyEnv, TinyPolicy
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import fit


FIXTURE_RECEIPTS = []


def packet(method, saved, design, *, invalid_four=False, finish=12, status='success', fault_override=None):
    events = [];writer = JsonJournal(io.StringIO(), {'experiment_run_id':'TINY_JOURNAL_SOFTWARE_ONLY',
        'manifest_id':'TINY_JOURNAL_SOFTWARE_ONLY', 'source_git_commit':'SOFTWARE_FIXTURE'})
    key = {'study_phase':'SOFTWARE', 'stream':0, 'episode':0, 'task':'push-v3', 'seed':700017, 'method':method}
    identity = {**writer.identity, **key}
    def emit(event, payload):
        row = writer.emit(event, {**key, **payload});events.append(row);return row
    ledger = LifecycleLedger(emit, 1000000);env = TinyEnv();policy = TinyPolicy()
    native_frames = 0;policy_queries = 0
    original_simulation = TinyEnv.do_simulation;original_step = TinyEnv.step;original_policy = TinyPolicy.get_action
    def simulate(current, ctrl, n_frames):
        def requested(current, ctrl, n_frames):
            nonlocal native_frames
            result = original_simulation(current, ctrl, n_frames);native_frames += n_frames;return result
        return ledger.simulation_call(requested, current, ctrl, n_frames)
    def reset(current):
        mujoco.mj_resetData(current.model, current.data);current.calls = 0
        for _ in range(100):
            current.do_simulation([0.], 5)
        return np.zeros(39), {}
    def step(current, action):
        observation, reward, _, _, info = original_step(current, action);done = current.calls >= finish
        return observation, reward, done and status == 'terminated', done and status == 'truncated', {**info, 'success':done and status == 'success'}
    def query(current, observation):
        nonlocal policy_queries
        policy_queries += 1;return original_policy(current, observation)
    four = {'valid':False, 'nfev':1, 'reason':'SOFTWARE_TEST_INVALID_FOUR'} if invalid_four else fit()
    eight = fit((-.1, .04), nfev=2)
    with ExitStack() as stack:
        stack.enter_context(patch.object(TinyEnv, 'do_simulation', simulate));stack.enter_context(patch.object(TinyEnv, 'step', step))
        stack.enter_context(patch.object(TinyPolicy, 'get_action', query))
        stack.enter_context(patch.object(runtime, 'infer_four', return_value=four));stack.enter_context(patch.object(runtime, 'infer_operator', return_value=eight))
        emit('FACTORY_INTENT', {'ledger':ledger.snapshot()})
        with ledger.scope('GOAL_GENERATION'):
            for _ in range(50):
                ledger.reset_call(reset, env)
        emit('FACTORY_COMPLETE', {'ledger':ledger.snapshot()})
        before = ledger.snapshot()
        with ledger.scope('CONTROLLED_RESET'):
            initial, _ = ledger.reset_call(reset, env)
        fault = deepcopy(fault_override) if fault_override is not None else {'matrix_xy':[[1., 0.], [0., 1.]], 'bias_xy':[.1, -.06], 'deadzone_xy':[0., 0.]}
        session = ProbeSession(env, policy, initial, 'push-v3', key['seed'], fault, emit, ledger, {'completed':0, 'maximum':500})
        host, actor = execute_short_session(session, method, None if method == 'NO_PROBE' else saved, before,
            design=design if method in runtime.DOPT_METHODS else None)
    FIXTURE_RECEIPTS.append({'method':method, 'actual_native_requested_frames':native_frames, 'ledger':ledger.snapshot(),
        'host_step_attempts':session.attempts, 'host_returned_steps':session.completed, 'actual_tiny_policy_queries':policy_queries,
        'captures':session.captures, 'restores':session.restores})
    return {'events':events, 'host':host, 'public':actor, 'identity':identity,
        'spec':{'task':'push-v3', 'seed':key['seed'], 'method':method, 'fault_oracle':fault}, 'four':four, 'eight':eight}


class ShortProbeJournalAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = model();cls.design = design_four(cls.model)
        cls.packets = {method:packet(method, cls.model, cls.design) for method in runtime.METHODS}
        cls.fallback = packet('DOPT4_FALLBACK8', cls.model, cls.design, invalid_four=True)
        cls.stopped = packet('DOPT4_KEEP_AT8', cls.model, cls.design, invalid_four=True)
        cls.early = packet('DOPT4_UPDATE', cls.model, cls.design, finish=2)
        cls.budget = packet('NO_PROBE', cls.model, cls.design, finish=999)

    def check(self, value, **kwargs):
        method = value['spec']['method']
        with patch.object(audit, 'create_task_policy', return_value=TinyPolicy()), patch.object(public, 'infer_four', return_value=value['four']), patch.object(public, 'infer_operator', return_value=value['eight']):
            return audit.audit_journal(value['events'], value['public'], value['host'], value['spec'],
                None if method == 'NO_PROBE' else self.model, design=self.design if method in runtime.DOPT_METHODS else None,
                identity=value['identity'], **kwargs)

    def event(self, value, kind):
        return next(row for row in value['events'] if row['event'] == kind)

    def test_seven_complete_programs_reconstruct_all_factory_control_and_query_fees(self):
        for method, value in self.packets.items():
            with self.subTest(method=method):
                result = self.check(value)
                self.assertEqual(result['integrity'], 'COLD_JOURNAL_CONSISTENT')
                self.assertEqual((result['factory_resets'], result['controlled_resets'], result['controlled_steps']), (50, 1, 12))
                self.assertEqual(result['ledger']['counts']['reset_completed'], 51)
                self.assertEqual(result['ledger']['counts']['simulation_frames_completed'], 25560)
                self.assertEqual(result['policy_queries_recomputed'], value['public']['outcome']['policy_queries'])
                self.assertEqual(set(result['boundaries']), {4, 8})
                self.assertFalse(result['independent_physics_execution']);self.assertFalse(result['complete_population_statistics_audited'])

    def test_fallback_stopping_early_ending_and_failure_keep_actual_costs_and_denominators(self):
        for value, expected_steps, expected_loss, expected_stopped in ((self.fallback, 12, 12, False),
                (self.stopped, 8, 500, True), (self.early, 2, 2, False), (self.budget, 500, 500, False)):
            with self.subTest(method=value['spec']['method'], steps=expected_steps):
                result = self.check(value);self.assertEqual(result['controlled_steps'], expected_steps)
                self.assertEqual(value['public']['outcome']['deadline_loss'], expected_loss)
                self.assertEqual(value['public']['outcome']['stopped'], expected_stopped)
                self.assertEqual(result['ledger']['counts']['simulation_frames_completed'], 25500+5*expected_steps)
        self.assertEqual(self.check(self.fallback)['public_audit']['fits_recomputed'], 2)
        self.assertEqual(self.check(self.stopped)['public_audit']['fits_recomputed'], 1)

    def test_audit_does_not_execute_actor_environment_or_capsule(self):
        with patch.object(runtime, 'execute_reference', side_effect=AssertionError('actor forbidden')), patch.object(ProbeSession, '_step', side_effect=AssertionError('host forbidden')), patch.object(TinyEnv, 'step', side_effect=AssertionError('environment forbidden')), patch('src.analysis.paired_probe_host_v1.capture', side_effect=AssertionError('capture forbidden')), patch('src.analysis.paired_probe_host_v1.restore', side_effect=AssertionError('restore forbidden')):
            self.assertEqual(self.check(self.packets['NO_PROBE'])['controlled_steps'], 12)

    def test_factory_fees_cannot_be_omitted_relabelled_or_rewound(self):
        for mutation in ('fee', 'phase', 'count'):
            value = deepcopy(self.packets['NO_PROBE'])
            row = self.event(value, 'LIFECYCLE_RESET_COMPLETE')
            if mutation == 'fee':row['after']['counts']['simulation_frames_completed'] -= 1
            elif mutation == 'phase':row['phase'] = 'CONTROLLED_RESET'
            else:self.event(value, 'FACTORY_COMPLETE')['ledger']['counts']['reset_completed'] = 49
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):self.check(value)

    def test_private_noise_and_saved_action_consumption_cannot_be_substituted(self):
        for mutation in ('noise', 'command', 'reference', 'cursor'):
            value = deepcopy(self.packets['NO_PROBE']);row = self.event(value, 'STEP_COMPLETE')
            if mutation == 'noise':row['executed_action_oracle'][0] += .001
            elif mutation == 'command':row['command'][0] += .01
            elif mutation == 'reference':row['global_command_sequence'] -= 1
            else:row['noise_cursor_after'] += 1
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):self.check(value)

    def test_fixed_policy_raw_output_is_verified_independently(self):
        value = deepcopy(self.packets['NO_PROBE'])
        row = next(row for row in value['events'] if row['event'] == 'AGENT_EVENT' and row['agent_event'] == 'COMMAND')
        row['public_payload']['raw_policy'][0] = .2
        with self.assertRaises(ValueError):self.check(value)

    def test_execution_before_saved_intent_and_discontinuous_native_time_are_rejected(self):
        for mutation in ('time', 'native'):
            value = deepcopy(self.packets['NO_PROBE']);row = self.event(value, 'STEP_COMPLETE')
            if mutation == 'time':row['execution_started_ns'] = self.event(value, 'STEP_INTENT')['saved_ns']-1
            else:row['simulation_time_after'] += .0125
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):self.check(value)

    def test_physical_boundary_and_global_record_order_are_mandatory(self):
        for mutation in ('boundary', 'missing', 'sequence', 'public_time'):
            value = deepcopy(self.packets['DOPT4_UPDATE'])
            if mutation == 'boundary':self.event(value, 'PHYSICAL_BOUNDARY')['noise_past_sha256'] = '0'*64
            elif mutation == 'missing':value['events'].remove(self.event(value, 'PHYSICAL_BOUNDARY'))
            elif mutation == 'sequence':value['events'][1]['sequence'] = False
            else:self.event(value, 'AGENT_EVENT')['public_payload']['saved_ns'] = 0
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):self.check(value)

    def test_public_trace_host_receipts_and_endings_must_match_outer_journal(self):
        for mutation in ('trace', 'host', 'after', 'append', 'partial', 'extra'):
            value = deepcopy(self.packets['NO_PROBE'])
            if mutation == 'trace':value['public']['trace'][0]['after']['observation'][0] += .01
            elif mutation == 'host':value['host']['policy_query_attempts'] += 1
            elif mutation == 'after':self.event(value, 'STEP_COMPLETE')['after']['success'] = 1
            elif mutation == 'append':value['events'].append(deepcopy(value['events'][-1]));value['events'][-1]['sequence'] += 1
            elif mutation == 'partial':value['events'].pop()
            else:self.event(value, 'SHORT_REFERENCE_START')['future_result'] = 123
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):self.check(value)

    def test_prefix_comparison_uses_real_rows_and_reports_incomplete_prefix(self):
        a = self.check(self.packets['DOPT8_UPDATE']);b = self.check(self.packets['DOPT4_KEEP_AT8']);c = self.check(self.packets['DOPT4_UPDATE'])
        self.assertTrue(audit.physical_rows_equal(a['physical_rows'], b['physical_rows'], 8))
        self.assertTrue(audit.physical_rows_equal(a['physical_rows'], c['physical_rows'], 4))
        self.assertFalse(audit.physical_rows_equal(a['physical_rows'], c['physical_rows'], 8))
        self.assertFalse(audit.physical_rows_equal(a['physical_rows'], self.check(self.early)['physical_rows'], 4))
        changed = deepcopy(b['physical_rows']);changed[0]['executed_action_oracle'][0] += .01
        self.assertFalse(audit.physical_rows_equal(a['physical_rows'], changed, 4))

    def test_identity_prior_ledger_and_reserved_clock_cannot_be_forged(self):
        value = deepcopy(self.packets['NO_PROBE']);value['events'][0]['seed'] += 1
        with self.assertRaises(ValueError):self.check(value)
        with self.assertRaises(ValueError):self.check(self.packets['NO_PROBE'], previous_sequence=1)
        bad = {'counts':{'reset_completed':1}, 'by_phase':{}}
        with self.assertRaises(ValueError):self.check(self.packets['NO_PROBE'], initial_ledger=bad)


    def test_seven_method_initial_witnesses_and_conditional_fallback_prefix_are_matched(self):
        runs = {method:self.check(value) for method, value in self.packets.items()}
        result = audit.audit_matched_unit(runs)
        self.assertEqual(result['complete_prefix_pairs'], 4)
        self.assertFalse(result['fallback_probe_extension_observed'])
        runs['DOPT4_FALLBACK8'] = self.check(self.fallback)
        result = audit.audit_matched_unit(runs)
        self.assertEqual(result['complete_prefix_pairs'], 5)
        self.assertTrue(result['fallback_probe_extension_observed'])
        self.assertFalse(result['population_ownership_authenticated'])

    def test_initial_state_or_same_prefix_changes_and_missing_method_are_rejected(self):
        runs = {method:self.check(value) for method, value in self.packets.items()}
        for mutation in ('native', 'initial', 'prefix', 'missing'):
            value = deepcopy(runs)
            if mutation == 'native':value['NO_PROBE']['start_witness']['native_sha256'] = '0'*64
            elif mutation == 'initial':value['ORIGINAL8_UPDATE']['initial_observation'][0] += .01
            elif mutation == 'prefix':value['DOPT4_KEEP_AT8']['physical_rows'][5]['command'][0] += .01
            else:del value['NO_PROBE']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):audit.audit_matched_unit(value)


    def test_other_private_fault_families_and_saturated_actions_match_source_arithmetic(self):
        from src.rollout.chronological_faults import deterministic_action
        faults = [
            {'matrix_xy':[[1., .7], [.02, .6]], 'bias_xy':[.08, -.08], 'deadzone_xy':[0., 0.]},
            {'matrix_xy':[[1., .1], [-.1, 1.]], 'bias_xy':[.1, -.1], 'deadzone_xy':[.2, .18]}]
        for fault in faults:
            value = packet('DOPT4_UPDATE', self.model, self.design, fault_override=fault)
            with self.subTest(fault=fault):
                self.assertEqual(self.check(value)['controlled_steps'], 12)
                for command in ([1., -1., 1., 0.], [-1., 1., -1., .4], [0., 0., 0., 0.]):
                    noise = np.asarray([.2, -.2, .2], np.float32)
                    expected = deterministic_action(command, fault);expected[:3] += noise;expected = np.clip(expected, -1, 1)
                    self.assertEqual(audit.applied(command, fault, noise), expected.tolist())
