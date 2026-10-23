"""Artificial public records only; no native simulation or MetaWorld task seeds."""
import copy
import random
import unittest
from unittest.mock import patch

import numpy as np

from src.analysis.short_probe_public_audit_v1 import audit_public_run
from src.probe import short_probe_execution_reference_v1 as runtime
from src.probe.cold_start_response import clipped_normal_mean
from src.probe.continuous import StepObservation
from src.probe.operator_identification import encode_controller, identity_controller
from src.probe.short_probe_design_reference_v1 import design_four
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import CallbackHost


class GainHost(CallbackHost):
    """Fictional gain schedule used only to exercise real invalid/valid fits."""
    def __init__(self, saved, first=.1, later=.1, **kwargs):
        super().__init__(saved, **kwargs);self.first = first;self.later = later

    def step(self, saved):
        after = super().step(saved)
        if self.calls <= 8:
            n = self.calls;u = np.asarray(self.sent)[:, :2]
            gains = np.array([self.first if t < 4 else self.later for t in range(n)])
            mean = clipped_normal_mean(u*gains[:, None])[0]
            delta = (np.asarray(self.model['offset'])[:2*n]+
                np.asarray(self.model['impulse'])[:2*n, :2*n]@mean.ravel()).reshape(n, 2)
            obs = list(self.initial.observation);obs[:2] = np.asarray(obs[:2])+delta.sum(axis=0);obs[38] = n
            self.current = StepObservation(tuple(obs), after.terminated, after.truncated, after.success)
        return self.current


class ShortProbePublicAuditTest(unittest.TestCase):
    def setUp(self):
        self.model = model();self.design = design_four(self.model)

    def record(self, method='DOPT4_UPDATE', host=None, **kwargs):
        host = host or CallbackHost(self.model)
        return runtime.execute_reference(method, 'push-v3', host.initial,
            None if method == 'NO_PROBE' else self.model, host.policy, host.step, host.emit,
            design=self.design if method in runtime.DOPT_METHODS else None, **kwargs)

    def audit(self, record, **kwargs):
        return audit_public_run(record, 'push-v3', None if record['method'] == 'NO_PROBE' else self.model,
            design=self.design if record['method'] in runtime.DOPT_METHODS else None, **kwargs)

    def test_all_seven_public_records_are_reconstructed_without_running_actor(self):
        for method in runtime.METHODS:
            record = self.record(method)
            with self.subTest(method=method), patch.object(runtime, 'execute_reference', side_effect=AssertionError('audit must not execute actor')):
                result = self.audit(record)
            self.assertEqual(result['integrity'], 'PUBLIC_PROGRAM_CONSISTENT')
            self.assertEqual(result['public_commands'], 10)
            self.assertEqual(result['fits_recomputed'], int(method != 'NO_PROBE'))
            self.assertFalse(result['real_physics_and_journal_authenticity_qualified'])
            self.assertFalse(result['complete_population_statistics_audited'])

    def test_real_invalid_four_and_eight_fits_keep_failed_denominators_and_actual_costs(self):
        for method, steps in (('DOPT4_UPDATE', 4), ('DOPT4_KEEP_AT8', 8), ('DOPT4_FALLBACK8', 8)):
            record = self.record(method, GainHost(self.model))
            with self.subTest(method=method):
                result = self.audit(record)
                self.assertEqual(result['public_commands'], steps)
                self.assertTrue(record['outcome']['stopped'])
                self.assertEqual(record['outcome']['deadline_loss'], 500)

    def test_real_invalid_four_can_extend_to_valid_eight_without_using_future_prefix_data(self):
        record = self.record('DOPT4_FALLBACK8', GainHost(self.model, later=1.))
        self.assertFalse(record['fits'][0]['fit']['valid']);self.assertTrue(record['fits'][1]['fit']['valid'])
        result = self.audit(record)
        self.assertEqual(result['fits_recomputed'], 2)
        self.assertTrue(record['outcome']['success']);self.assertEqual(record['outcome']['fixed_probe_steps'], 8)

    def test_early_success_termination_and_late_probe_success_have_correct_fit_coverage(self):
        for status in ('success', 'terminated', 'truncated'):
            record = self.record('DOPT4_FALLBACK8', CallbackHost(self.model, finish=2, status=status))
            with self.subTest(status=status):
                self.assertEqual(self.audit(record)['fits_recomputed'], 0)
        late = self.record('DOPT4_KEEP_AT8', GainHost(self.model, finish=6))
        self.assertTrue(late['outcome']['success']);self.assertFalse(late['fits'][0]['fit']['valid'])
        self.assertEqual(self.audit(late)['fits_recomputed'], 1)

    def test_fixed_budget_exhaustion_passes_and_shorter_budget_cannot_enter_population(self):
        full = self.record('NO_PROBE', CallbackHost(self.model, finish=999))
        self.assertEqual(self.audit(full)['public_commands'], 500)
        short = self.record('NO_PROBE', CallbackHost(self.model, finish=999), remaining_budget=3)
        with self.assertRaises(ValueError):self.audit(short)

    def test_coherent_controller_and_policy_command_substitution_cannot_replace_saved_four_fit(self):
        record = self.record('DOPT4_KEEP_AT8')
        run = next(row['public_payload'] for row in record['events'] if row['event'] == 'CHOICE' and row['public_payload']['action'] == 'RUN_FITTED')
        run['controller'] = identity_controller()
        for event in record['events']:
            row = event['public_payload']
            if event['event'] == 'COMMAND' and row['phase'] == 'POLICY':
                row['command'] = encode_controller(run['controller'], row['raw_policy']).tolist()
                record['trace'][row['at_calls']]['command'] = copy.deepcopy(row['command'])
        with self.assertRaises(ValueError):self.audit(record)

    def test_forged_fitting_history_or_parameters_are_rejected_even_with_updated_checksums(self):
        original = self.record()
        for kind in ('observations', 'parameters'):
            record = copy.deepcopy(original)
            event = next(row['public_payload'] for row in record['events'] if row['event'] == 'FIT_RESULT')
            if kind == 'observations':
                event['prefix']['observations'][-1][0] += .1
                event['prefix_evidence_sha256'] = runtime.digest(event['prefix'])
            else:
                event['fit']['bias_xy'][0] += .01
            record['fits'][0] = copy.deepcopy(event)
            with self.subTest(kind=kind), self.assertRaises(ValueError):self.audit(record)

    def test_unknown_oracle_fields_future_fit_reference_and_noncausal_clocks_are_rejected(self):
        original = self.record()
        for kind in ('oracle', 'future_fit', 'clock', 'sequence'):
            record = copy.deepcopy(original)
            if kind == 'oracle':record['outcome']['fault_oracle'] = {'bias':1}
            if kind == 'future_fit':
                row = next(event['public_payload'] for event in record['events'] if event['event'] == 'CHOICE' and event['public_payload']['action'] == 'RUN_FITTED')
                row['fit_sequence'] = record['events'][-1]['public_payload']['sequence']
            if kind == 'clock':record['events'][1]['public_payload']['saved_ns'] = -1
            if kind == 'sequence':record['events'][0]['public_payload']['sequence'] = False
            with self.subTest(kind=kind), self.assertRaises(ValueError):self.audit(record)

    def test_illegal_probe_saved_design_incomplete_records_and_changed_failure_scores_fail_closed(self):
        record = self.record()
        damaged = copy.deepcopy(record)
        probe = next(row['public_payload'] for row in damaged['events'] if row['event'] == 'CHOICE')
        probe['program'][0][0] = .2
        with self.assertRaises(ValueError):self.audit(damaged)
        design = copy.deepcopy(self.design);design['future_outcomes'] = [1]
        with self.assertRaises(ValueError):audit_public_run(record, 'push-v3', self.model, design=design)
        missing = copy.deepcopy(record);missing['events'].pop()
        with self.assertRaises(ValueError):self.audit(missing)
        failed = self.record('DOPT4_UPDATE', GainHost(self.model))
        failed['outcome']['deadline_loss'] = 4
        with self.assertRaises(ValueError):self.audit(failed)

    def test_recomputation_costs_and_input_random_state_are_preserved(self):
        record = self.record();before = copy.deepcopy(record)
        np_before = np.random.get_state();py_before = random.getstate()
        result = self.audit(record)
        self.assertEqual(result['fit_optimizer_nfev_recomputed'], record['outcome']['optimizer_nfev'])
        self.assertEqual(result['design_candidates_recomputed'], 144)
        self.assertEqual(record, before)
        np.testing.assert_equal(np.random.get_state(), np_before);self.assertEqual(random.getstate(), py_before)


if __name__ == '__main__':
    unittest.main()
