"""No environment, network, estimator training, or selected old result fixtures."""
from copy import deepcopy
from dataclasses import replace
import unittest
import numpy as np

from src.probe import linear_command_preflight_v1 as core


def query(step=6, baseline=(.9, -.9, .3, -.2)):
    history = np.arange(117, dtype=float).reshape(3, 39)/1000
    return core.make_query("push-v3", step, history, baseline)


def model(feature="F20"):
    n = core.DIMENSIONS[feature]
    coefficient = np.arange((n+1)*2, dtype=float).reshape(n+1, 2)/100
    return core.LinearCommandModel("push-v3", feature, tuple(np.arange(n)/100),
                                   tuple(1+np.arange(n)/10), coefficient)


class CommandPreflightTests(unittest.TestCase):
    def test_three_real_observations_and_all_feature_mappings(self):
        q = query(); a, b, c = np.asarray(q.observations)
        f20 = np.r_[c[:3], c[:3]-b[:3], b[:3]-a[:3], q.baseline_command, c[3], c[4:7]-c[:3], c[-3:]-c[:3]]
        np.testing.assert_array_equal(core.feature_vector(q,"F20",q.baseline_command), f20)
        np.testing.assert_array_equal(core.feature_vector(q,"H10",q.baseline_command), f20[3:13])
        np.testing.assert_array_equal(core.feature_vector(q,"F43",q.baseline_command), np.r_[c,q.baseline_command])

    def test_missing_history_rejected_without_zero_fill(self):
        q = query()
        for history in (q.observations[:2], (), None):
            with self.assertRaises(ValueError): replace(q, observations=history)
        with self.assertRaises(ValueError): core.make_query("push-v3",1,q.observations,q.baseline_command)

    def test_future_time_and_nonconsecutive_history_rejected(self):
        q = query()
        for steps in ((4,5,7),(3,5,6),(4,5,5),(4,5,True)):
            with self.assertRaises(ValueError): replace(q,observation_steps=steps)
        with self.assertRaises(ValueError): replace(q,decision_step=500)

    def test_unknown_nested_oracle_and_future_fields_rejected(self):
        raw = query().to_dict()
        for field in ("seed","true_operator","next_observation","outcome","executed_action_oracle"):
            altered = deepcopy(raw); altered[field] = 0
            with self.assertRaises(ValueError): core.CausalCommandQuery.from_dict(altered)
            altered = deepcopy(raw); altered['candidates'][0][field] = 0
            with self.assertRaises(ValueError): core.CausalCommandQuery.from_dict(altered)

    def test_roundtrip_preserves_every_issued_query(self):
        q = query()
        self.assertEqual(core.CausalCommandQuery.from_dict(q.to_dict()),q)

    def test_offsets_are_clipped_only_in_xy_and_preserve_other_commands(self):
        q = query()
        expected = ((1.,-.9,.3,-.2),(.65,-.9,.3,-.2),(.9,-.65,.3,-.2),(.9,-1.,.3,-.2))
        for actual,want in zip(q.candidates,expected): np.testing.assert_allclose(actual.command,want,atol=1e-15)
        with self.assertRaises(ValueError): replace(q,candidates=q.candidates[::-1])
        with self.assertRaises(ValueError): replace(q,candidates=q.candidates[:3])
        candidate=replace(q.candidates[0],command=(*q.candidates[0].command[:3], .4))
        with self.assertRaises(ValueError): replace(q,candidates=(candidate,*q.candidates[1:]))

    def test_invalid_numbers_and_unknown_candidate_ids(self):
        for value in (np.nan,np.inf,True,".2"):
            with self.assertRaises(ValueError): core.fixed_candidates((value,0.,0.,0.))
        with self.assertRaises(ValueError): core.fixed_candidates((1.01,0.,0.,0.))
        for name in ("ORACLE",None,[]):
            with self.assertRaises(ValueError): core.CommandCandidate(name,(0.,0.,0.,0.))

    def test_finite_differences_match_unscaled_command_rows_all_features(self):
        q=query()
        for feature in core.FEATURES:
            m=model(feature); sl=core.COMMAND_SLICES[feature]
            jac=np.asarray(m.coefficient)[1+sl.start:1+sl.stop].T/np.asarray(m.scale)[sl]
            np.testing.assert_array_equal(m.command_matrix(),jac)
            for c in q.candidates:
                np.testing.assert_allclose(m.predict(q,c.command)-m.predict(q,q.baseline_command),
                                           jac@(np.asarray(c.command)-q.baseline_command),atol=1e-14)

    def test_command_contrasts_independent_of_state_for_fixed_commands(self):
        q=query(); history=np.asarray(q.observations)*4+.1
        other=replace(q, observations=history)
        for feature in core.FEATURES:
            m=model(feature)
            self.assertFalse(np.array_equal(m.predict(q,q.baseline_command),m.predict(other,other.baseline_command)))
            a,b=m.compare(q),m.compare(other)
            for x,y in zip(a['candidates'],b['candidates']):
                np.testing.assert_array_equal(x['predicted_difference_m'],y['predicted_difference_m'])

    def test_reversing_or_rescaling_command_coefficients_changes_query_predictions(self):
        q=query(); m=model(); altered=np.asarray(m.coefficient).copy(); altered[10:14]*=-3
        wrong=replace(m,coefficient=altered)
        self.assertFalse(np.allclose(m.command_matrix(),wrong.command_matrix()))
        self.assertFalse(np.allclose(m.compare(q)['candidates'][0]['predicted_difference_m'],
                                     wrong.compare(q)['candidates'][0]['predicted_difference_m']))

    def test_target_statistics_are_not_applied_twice_to_saved_linear_metres(self):
        m=model(); saved={"schema":"TRAINING_CONTROL_LINEAR_V1","task":m.task,"feature":"F20",
            "coefficient":m.coefficient,"ridge":.001,"weighted_design_rank":21,"parameter_count":42,"probability_guarantee":False,
            "stats":{"feature":"F20","loss":"ISO","input_mean":m.mean,"input_scale":m.scale,
                     "target_mean":[100.,-200.],"target_scale":[77.,77.],"training_trajectories":24,"training_responses":800}}
        loaded=core.LinearCommandModel.from_saved(saved)
        np.testing.assert_array_equal(loaded.predict(query(),query().baseline_command),m.predict(query(),query().baseline_command))
        saved['schema']='TRAINING_CONTROL_GRU_V1'
        with self.assertRaises(ValueError): core.LinearCommandModel.from_saved(saved)

    def test_wrong_task_and_parameter_mapping_rejected(self):
        with self.assertRaises(ValueError): model().predict(replace(query(),task='reach-v3'),query().baseline_command)
        with self.assertRaises(ValueError): replace(model(),scale=[0.]*20)
        with self.assertRaises(ValueError): replace(model(),coefficient=np.zeros((20,2)))

    def test_saturated_identical_query_is_retained_with_zero_contrast(self):
        q=query(baseline=(1.,-1.,.1,1.)); output=model().compare(q)
        self.assertEqual(len(output['candidates']),4)
        for i in (0,3):
            self.assertTrue(output['candidates'][i]['same_as_baseline'])
            np.testing.assert_array_equal(output['candidates'][i]['predicted_difference_m'],[0.,0.])
        self.assertFalse(output['physical_qualification'])
        self.assertFalse(output['executed_counterfactuals'])

    def test_full_rank_geometry_matches_known_inverse_information(self):
        a=np.diag([1.,2.,3.,4.,5.]); g=core.design_geometry(a,(1,2,3,4)); v=np.arange(5)/10
        self.assertEqual(g['rank'],5); self.assertEqual(g['conditional_command_rank'],4)
        actual=core.query_geometry(g,v)
        self.assertLess(actual['row_span_relative_residual'],1e-14)
        self.assertAlmostEqual(actual['weighted_design_leverage'],float(np.sum((v/np.diag(a))**2)))

    def test_closed_loop_command_columns_confounded_with_nuisance(self):
        nuisance=np.eye(5); commands=nuisance[:,:4]
        a=np.c_[nuisance,commands]; g=core.design_geometry(a,(5,6,7,8))
        self.assertEqual(g['rank'],5); self.assertEqual(g['conditional_command_rank'],0)
        v=np.zeros(9); v[5]=.25; result=core.query_geometry(g,v)
        self.assertGreater(result['row_span_relative_residual'],.5)
        self.assertIsNone(g['condition'])

    def test_zero_query_and_zero_design_do_not_invent_support(self):
        g=core.design_geometry(np.zeros((10,6)),(1,2,3,4))
        self.assertEqual(g['rank'],0); self.assertEqual(g['conditional_command_rank'],0)
        self.assertIsNone(core.query_geometry(g,np.zeros(6))['row_span_relative_residual'])
        self.assertEqual(core.query_geometry(g,np.ones(6))['row_span_relative_residual'],1.)

    def test_xy_projection_treats_other_command_coordinates_as_nuisance(self):
        g=core.design_geometry(np.eye(6),(2,3))
        self.assertEqual(g['conditional_command_rank'],2); self.assertEqual(g['nuisance_rank'],4)

    def test_output_predictions_are_not_synthetic_truth(self):
        q=query(); a=model().compare(q)
        opposite=replace(model(),coefficient=-np.asarray(model().coefficient))
        b=opposite.compare(q)
        self.assertFalse(a['task_benefit']); self.assertFalse(b['task_benefit'])
        np.testing.assert_allclose(a['candidates'][0]['predicted_difference_m'],
                                  -np.asarray(b['candidates'][0]['predicted_difference_m']))


if __name__ == '__main__':
    unittest.main()
