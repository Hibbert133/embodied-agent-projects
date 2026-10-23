"""Artificial callback trajectories only; no MetaWorld environment or task seeds."""
import copy
import random
import unittest
from unittest.mock import patch

import numpy as np

from src.probe import short_probe_execution_reference_v1 as runtime
from src.probe.continuous import StepObservation
from src.probe.short_probe_design_reference_v1 import design_four
from tests.test_short_joint_reference_v1 import model, observations


def fit(bias=(.05, -.04), nfev=1):
    return {'valid':True, 'matrix_xy':[[1., 0], [0, 1.]], 'bias_xy':list(bias), 'nfev':nfev}


class CallbackHost:
    def __init__(self, saved, finish=10, status='success'):
        self.model = saved;self.finish = finish;self.status = status
        self.initial = StepObservation(observations(saved).initial_observation, False, False, False)
        self.current = self.initial;self.calls = 0;self.events = [];self.sent = [];self.policy_inputs = []
        self.after_step = None

    def emit(self, event, payload):
        saved = {**copy.deepcopy(payload), 'sequence':len(self.events), 'saved_ns':100+len(self.events)}
        self.events.append((event, copy.deepcopy(saved)))
        return saved

    def step(self, saved):
        if saved['at_calls'] != self.calls or self.events[-1] != ('COMMAND', saved):
            raise ValueError('host refuses stale or unsaved public command')
        if self.events[saved['decision_sequence']][0] != 'CHOICE':
            raise ValueError('missing earlier saved choice')
        self.sent.append(copy.deepcopy(saved['command']));self.calls += 1
        if self.calls <= 8:
            obs = list(observations(self.model, self.sent).observations[-1])
        else:
            obs = list(self.current.observation)
        obs[38] = self.calls
        done = self.calls >= self.finish
        self.current = StepObservation(tuple(obs), done and self.status == 'terminated',
            done and self.status == 'truncated', done and self.status == 'success')
        if self.after_step is not None:
            self.after_step()
        return self.current

    def policy(self, obs):
        self.policy_inputs.append(obs.copy())
        return np.array([.3, -.2, 0, 0])


class ShortProbeExecutionReferenceTest(unittest.TestCase):
    def setUp(self):
        self.model = model();self.design = design_four(self.model)

    def execute(self, method, host=None, **kwargs):
        host = host or CallbackHost(self.model)
        result = runtime.execute_reference(method, 'push-v3', host.initial,
            None if method == 'NO_PROBE' else self.model, host.policy, host.step, host.emit,
            design=self.design if method in runtime.DOPT_METHODS else None, **kwargs)
        return host, result

    def test_all_seven_real_estimator_paths_have_registered_prefixes_and_live_handoff(self):
        expected = {'NO_PROBE':0, 'ORIGINAL8_UPDATE':8, 'BALANCED4_UPDATE':4,
            'DOPT4_UPDATE':4, 'DOPT8_UPDATE':8, 'DOPT4_KEEP_AT8':8, 'DOPT4_FALLBACK8':4}
        for method in runtime.METHODS:
            with self.subTest(method=method):
                host, result = self.execute(method)
                outcome = result['outcome']
                self.assertTrue(outcome['success']);self.assertEqual(outcome['total_steps'], 10)
                self.assertEqual(outcome['fixed_probe_steps'], expected[method])
                self.assertEqual(host.policy_inputs[0][38], expected[method])
                self.assertEqual(outcome['policy_queries'], len(host.policy_inputs))
                self.assertEqual(outcome['online_parameter_fits'], int(method != 'NO_PROBE'))
                self.assertEqual(outcome['design_verification_candidates'], 144 if method in runtime.DOPT_METHODS else 0)
                self.assertEqual(len(host.sent), 10)
                self.assertEqual(result['events'][-1]['event'], 'OUTCOME')

    def test_keep_at_eight_consumes_saved_four_fit_even_if_original_result_is_later_mutated(self):
        saved_four = fit();saved_eight = fit((-.15, .1))
        host = CallbackHost(self.model)
        def mutate_original():
            if host.calls == 5:
                saved_four['bias_xy'][0] = .29
        host.after_step = mutate_original
        with patch.object(runtime, 'infer_four', return_value=saved_four) as four, patch.object(runtime, 'infer_operator', return_value=saved_eight) as eight:
            _, kept = self.execute('DOPT4_KEEP_AT8', host)
        four.assert_called_once();eight.assert_not_called()
        with patch.object(runtime, 'infer_operator', return_value=saved_eight):
            other, updated = self.execute('DOPT8_UPDATE')
        self.assertEqual(host.sent[:8], other.sent[:8])
        np.testing.assert_allclose(host.sent[8], [.25, -.16, 0, 0], atol=1e-7)
        self.assertNotEqual(host.sent[8], other.sent[8])
        self.assertEqual(kept['fits'][0]['fit']['bias_xy'], [.05, -.04])
        choices = [row['public_payload'] for row in kept['events'] if row['event'] == 'CHOICE']
        applied = next(row for row in choices if row['action'] == 'RUN_FITTED')
        self.assertEqual(applied['at_calls'], 8);self.assertEqual(applied['fitted_prefix_steps'], 4)
        self.assertEqual(updated['fits'][0]['at_calls'], 8)

    def test_invalid_four_really_extends_same_program_and_uses_eight_actual_observations(self):
        invalid = {'valid':False, 'reason':'ARTIFICIAL_INVALID', 'nfev':7}
        with patch.object(runtime, 'infer_four', return_value=invalid) as four, patch.object(runtime, 'infer_operator', return_value=fit(nfev=11)) as eight:
            host, result = self.execute('DOPT4_FALLBACK8')
        self.assertEqual(len(four.call_args.args[1].commands), 4)
        self.assertEqual(len(eight.call_args.args[1].commands), 8)
        self.assertEqual(host.sent[:4], host.sent[4:8])
        self.assertEqual(result['outcome']['fixed_probe_steps'], 8)
        self.assertEqual(result['outcome']['online_parameter_fits'], 2)
        self.assertEqual(result['outcome']['optimizer_nfev'], 18)
        self.assertEqual(host.policy_inputs[0][38], 8)
        self.assertTrue(result['outcome']['success'])

    def test_two_invalid_fits_stop_at_eight_without_repeat_probe_or_substitution(self):
        invalid = {'valid':False, 'reason':'ARTIFICIAL_INVALID', 'nfev':1}
        with patch.object(runtime, 'infer_four', return_value=invalid), patch.object(runtime, 'infer_operator', return_value=invalid):
            host, result = self.execute('DOPT4_FALLBACK8')
        self.assertEqual(host.calls, 8);self.assertFalse(host.policy_inputs)
        self.assertTrue(result['outcome']['stopped']);self.assertEqual(result['outcome']['deadline_loss'], 500)
        self.assertEqual([row['at_calls'] for row in result['fits']], [4, 8])
        self.assertEqual(result['outcome']['fixed_probe_steps'], 8)

    def test_invalid_keep_control_and_direct_four_preserve_different_actual_costs(self):
        invalid = {'valid':False, 'reason':'ARTIFICIAL_INVALID', 'nfev':0}
        with patch.object(runtime, 'infer_four', return_value=invalid), patch.object(runtime, 'infer_operator') as eight:
            direct, first = self.execute('DOPT4_UPDATE')
            kept, second = self.execute('DOPT4_KEEP_AT8')
        eight.assert_not_called()
        self.assertEqual((direct.calls, kept.calls), (4, 8))
        self.assertEqual((first['outcome']['deadline_loss'], second['outcome']['deadline_loss']), (500, 500))
        self.assertTrue(first['outcome']['stopped']);self.assertTrue(second['outcome']['stopped'])

    def test_early_success_after_invalid_four_is_counted_without_applying_invalid_fit(self):
        invalid = {'valid':False, 'reason':'ARTIFICIAL_INVALID', 'nfev':0}
        with patch.object(runtime, 'infer_four', return_value=invalid), patch.object(runtime, 'infer_operator') as eight:
            host, result = self.execute('DOPT4_KEEP_AT8', CallbackHost(self.model, finish=6))
        eight.assert_not_called();self.assertEqual(host.calls, 6)
        self.assertTrue(result['outcome']['success']);self.assertFalse(result['outcome']['stopped'])
        self.assertEqual(result['outcome']['deadline_loss'], 6)
        self.assertFalse(result['outcome']['applied_fitted_controller'])

    def test_early_probe_success_termination_and_truncation_do_not_fabricate_estimates(self):
        for status in ('success', 'terminated', 'truncated'):
            with self.subTest(status=status), patch.object(runtime, 'infer_four') as four, patch.object(runtime, 'infer_operator') as eight:
                host, result = self.execute('DOPT4_FALLBACK8', CallbackHost(self.model, finish=2, status=status))
                four.assert_not_called();eight.assert_not_called()
                self.assertEqual(host.calls, 2);self.assertFalse(host.policy_inputs)
                self.assertEqual(result['outcome']['deadline_loss'], 2 if status == 'success' else 500)
                self.assertEqual(result['outcome']['end_reason'], status.upper())

    def test_budget_rejection_precedes_steps_and_exhaustion_charges_only_actual_steps(self):
        for method, budget in (('DOPT4_UPDATE', 35), ('DOPT8_UPDATE', 39), ('DOPT4_FALLBACK8', 39), ('NO_PROBE', True), ('NO_PROBE', 501)):
            host = CallbackHost(self.model)
            with self.assertRaises(ValueError):self.execute(method, host, remaining_budget=budget)
            self.assertFalse(host.events);self.assertEqual(host.calls, 0)
        host, result = self.execute('NO_PROBE', CallbackHost(self.model, finish=999), remaining_budget=3)
        self.assertEqual(host.calls, 3);self.assertEqual(result['outcome']['deadline_loss'], 500)
        self.assertEqual(result['outcome']['end_reason'], 'BUDGET_EXHAUSTED')
        host, result = self.execute('DOPT4_UPDATE', CallbackHost(self.model, finish=999))
        self.assertEqual(host.calls, 500);self.assertEqual(result['outcome']['policy_steps'], 496)

    def test_mutated_and_oracle_acknowledgements_are_rejected_before_execution(self):
        for kind in ('extra', 'inplace', 'sequence', 'clock', 'command'):
            host = CallbackHost(self.model)
            def emit(event, payload):
                if kind == 'inplace':payload['method'] = 'SUBSTITUTED'
                if kind == 'command' and event == 'COMMAND':payload['command'][0] = .7
                saved = host.emit(event, payload)
                if kind == 'extra':saved['fault_oracle'] = 1
                if kind == 'sequence':saved['sequence'] = True
                if kind == 'clock':saved['saved_ns'] = 1.5
                return saved
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                runtime.execute_reference('DOPT4_UPDATE', 'push-v3', host.initial, self.model, host.policy, host.step, emit, design=self.design)
            self.assertEqual(host.calls, 0)

    def test_fitted_controller_cannot_be_rewritten_by_persistence_callback(self):
        host = CallbackHost(self.model)
        def emit(event, payload):
            if event == 'FIT_RESULT':payload['fit']['bias_xy'][0] = .29
            return host.emit(event, payload)
        with patch.object(runtime, 'infer_four', return_value=fit()), self.assertRaises(ValueError):
            runtime.execute_reference('DOPT4_UPDATE', 'push-v3', host.initial, self.model, host.policy, host.step, emit, design=self.design)
        self.assertEqual(host.calls, 4);self.assertFalse(host.policy_inputs)

    def test_unknown_inputs_and_tampered_nominal_design_fail_before_steps(self):
        for kind in ('unknown_field', 'substituted_choice', 'boolean_type'):
            damaged = copy.deepcopy(self.design)
            if kind == 'unknown_field':damaged['future_outcomes'] = [1]
            if kind == 'substituted_choice':damaged['selected_candidate_id'] = 'FOUR_999'
            if kind == 'boolean_type':damaged['physical_response_qualified'] = 0
            host = CallbackHost(self.model)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                runtime.execute_reference('DOPT4_UPDATE', 'push-v3', host.initial, self.model, host.policy, host.step, host.emit, design=damaged)
            self.assertEqual(host.calls, 0);self.assertFalse(host.events)
        host = CallbackHost(self.model)
        with self.assertRaises(ValueError):runtime.execute_reference('UNREGISTERED', 'push-v3', host.initial, self.model, host.policy, host.step, host.emit)
        with self.assertRaises(ValueError):runtime.execute_reference('BALANCED4_UPDATE', 'reach-v3', host.initial, self.model, host.policy, host.step, host.emit)
        with self.assertRaises(ValueError):runtime.execute_reference('BALANCED4_UPDATE', 'push-v3', host.initial, {**self.model, 'seed':1}, host.policy, host.step, host.emit)
        with self.assertRaises(ValueError):runtime.execute_reference('NO_PROBE', 'push-v3', host.initial, self.model, host.policy, host.step, host.emit)
        with self.assertRaises(ValueError):runtime.execute_reference('NO_PROBE', 'push-v3', StepObservation((0, 0, 0), False, False, False), None, host.policy, host.step, host.emit)
        self.assertEqual(host.calls, 0)

    def test_bad_step_result_and_saved_command_mutation_are_detected_after_actual_callback(self):
        for kind in ('bad_observation', 'mutated_command', 'mutated_type'):
            host = CallbackHost(self.model)
            def step(saved):
                current = host.step(saved)
                if kind == 'bad_observation':return StepObservation((0, 0, 0), False, False, False)
                if kind == 'mutated_command':saved['command'][0] = .7
                if kind == 'mutated_type':saved['command'][2] = False
                return current
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                runtime.execute_reference('NO_PROBE', 'push-v3', host.initial, None, host.policy, step, host.emit)
            self.assertEqual(host.calls, 1)

    def test_model_is_bound_to_its_entry_payload_before_callback_mutation(self):
        physical = copy.deepcopy(self.model);host = CallbackHost(physical)
        mutable = copy.deepcopy(self.model);before = copy.deepcopy(mutable)
        def emit(event, payload):
            if event == 'PROGRAM':mutable['initial_hand_lower'][0] = .8
            return host.emit(event, payload)
        result = runtime.execute_reference('DOPT4_UPDATE', 'push-v3', host.initial, mutable,
            host.policy, host.step, emit, design=self.design)
        self.assertTrue(result['outcome']['success'])
        self.assertNotEqual(mutable, before)
        declared = result['events'][0]['public_payload']['nominal_model_payload_sha256']
        self.assertEqual(declared, runtime.digest(before))

    def test_raw_policy_is_saved_and_existing_clip_before_inverse_semantics_are_preserved(self):
        host = CallbackHost(self.model)
        def raw_policy(obs):return np.array([3., -5., 0, 0])
        with patch.object(runtime, 'infer_four', return_value=fit((.1, -.1))):
            result = runtime.execute_reference('DOPT4_UPDATE', 'push-v3', host.initial, self.model, raw_policy, host.step, host.emit, design=self.design)
        policy_row = next(row for row in result['trace'] if row['phase'] == 'POLICY')
        self.assertEqual(policy_row['raw_policy'], [3., -5., 0, 0])
        np.testing.assert_allclose(policy_row['command'], [.9, -.9, 0, 0], atol=1e-7)

    def test_execution_is_deterministic_and_does_not_consume_global_randomness_or_mutate_inputs(self):
        numpy_before = np.random.get_state();python_before = random.getstate()
        model_before = copy.deepcopy(self.model);design_before = copy.deepcopy(self.design)
        _, first = self.execute('DOPT4_FALLBACK8');_, second = self.execute('DOPT4_FALLBACK8')
        self.assertEqual(first, second);self.assertEqual(self.model, model_before);self.assertEqual(self.design, design_before)
        np.testing.assert_equal(np.random.get_state(), numpy_before);self.assertEqual(random.getstate(), python_before)


if __name__ == '__main__':
    unittest.main()
