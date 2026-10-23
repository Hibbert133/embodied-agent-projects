"""Software-only design checks with artificial declared response matrices."""
import copy
import json
import random
import unittest

import numpy as np

from src.probe import short_probe_design_reference_v1 as design
from src.probe.cold_start_response import ColdPrefix
from src.probe.short_joint_reference_v1 import infer_four
from tests.test_short_joint_reference_v1 import model, observations


class ShortProbeDesignReferenceTest(unittest.TestCase):
    def test_complete_unique_balanced_float32_library_with_matched_norm_bound(self):
        programs = design.candidate_programs()
        self.assertEqual(len(programs), 144)
        self.assertEqual(len({tuple(p['direction_ids']) for p in programs}), 144)
        for program in programs:
            u = np.asarray(program['commands'])
            np.testing.assert_array_equal(u, u.astype(np.float32).astype(float))
            np.testing.assert_array_equal(u.sum(axis=0), np.zeros(4))
            self.assertEqual(np.linalg.matrix_rank(np.c_[u[:, :2], np.ones(4)]), 3)
            norms = np.linalg.norm(u[:, :2], axis=1)
            self.assertTrue(np.all(norms <= float(np.float32(.4))))
            self.assertLess(np.ptp(norms), 4e-8)
            self.assertLess(abs(program['total_squared_xy_norm']-4*float(np.float32(.4))**2), 1e-7)

    def test_every_saved_score_matches_independent_normal_equation_information(self):
        saved = model()
        g = np.asarray(saved['impulse']);g[:8, :8] *= np.arange(1, 9)[:, None]
        saved['impulse'] = g.tolist()
        saved['covariance'] = (1e-6*.35**np.abs(np.arange(16)[:, None]-np.arange(16))).tolist()
        result = design.design_four(saved)
        precision = np.linalg.inv(np.asarray(saved['covariance'])[:8, :8])
        scores = []
        for candidate in result['candidates']:
            u = np.asarray(candidate['commands'])[:, :2]
            # Identity commands remain far from clipping. This independent
            # block construction does not call the production Jacobian code.
            raw = np.zeros((8, 6))
            for t, (ux, uy) in enumerate(u):
                raw[2*t, :3] = [ux, uy, 1]
                raw[2*t+1, 3:] = [ux, uy, 1]
            j = g[:8, :8]@raw
            sign, score = np.linalg.slogdet(j.T@precision@j)
            self.assertEqual(sign, 1)
            self.assertEqual(candidate['whitened_design_rank'], 6)
            self.assertAlmostEqual(score, candidate['logdet_information'], places=10)
            scores.append(candidate['logdet_information'])
        self.assertEqual(result['selected_candidate_id'], result['candidates'][int(np.argmax(scores))]['candidate_id'])
        json.dumps(result, allow_nan=False)

    def test_selected_saved_program_is_consumable_by_four_step_estimator(self):
        saved = model();result = design.design_four(saved)
        selected = next(p for p in result['candidates'] if p['candidate_id'] == result['selected_candidate_id'])
        prefix = observations(saved, selected['commands'])
        self.assertIsInstance(prefix, ColdPrefix)
        fit = infer_four(saved, prefix)
        self.assertTrue(fit['valid'])
        np.testing.assert_allclose(fit['matrix_xy'], [[.9, .1], [-.1, 1.1]], atol=1e-7)
        np.testing.assert_allclose(fit['bias_xy'], [.05, -.04], atol=1e-7)

    def test_does_not_condition_on_future_model_rows_or_future_response_correlation(self):
        saved = model();other = copy.deepcopy(saved)
        other['offset'][8:] = [1e4]*8
        impulse = np.asarray(other['impulse']);impulse[8:, :] *= 100
        other['impulse'] = impulse.tolist()
        cov = np.asarray(other['covariance']);cov[:8, 8:] = cov[8:, :8] = .6e-6*np.eye(8)
        other['covariance'] = cov.tolist()
        self.assertEqual(design.design_four(saved), design.design_four(other))

    def test_unresponsive_nominal_model_cannot_silently_select_a_program(self):
        saved = model();saved['impulse'] = np.zeros((16, 16)).tolist()
        result = design.design_four(saved)
        self.assertIsNone(result['selected_candidate_id'])
        self.assertEqual(result['reason'], 'NO_IDENTIFIABLE_NOMINAL_DESIGN')
        self.assertTrue(all(p['logdet_information'] is None for p in result['candidates']))
        json.dumps(result, allow_nan=False)

    def test_numerically_unusable_model_cannot_return_infinite_score(self):
        saved = model();saved['covariance'] = (1e-300*np.eye(16)).tolist()
        saved['impulse'] = (np.asarray(saved['impulse'])*1e308).tolist()
        before = np.geterr()
        with self.assertRaises(ValueError):design.design_four(saved)
        self.assertEqual(np.geterr(), before)

    def test_strict_nominal_only_input_determinism_and_no_global_randomness(self):
        saved = model();before = copy.deepcopy(saved)
        numpy_before = np.random.get_state();python_before = random.getstate()
        first = design.design_four(saved);self.assertEqual(first, design.design_four(saved))
        self.assertEqual(saved, before)
        np.testing.assert_equal(np.random.get_state(), numpy_before);self.assertEqual(random.getstate(), python_before)
        for field in ('task_seed', 'fault_oracle', 'future_outcomes', 'selected_candidate_id'):
            with self.assertRaises(ValueError):design.design_four({**saved, field: 1})
        self.assertFalse(first['physical_response_qualified']);self.assertFalse(first['probability_guarantee'])
        self.assertFalse(first['task_utility_qualified'])


if __name__ == '__main__':
    unittest.main()
