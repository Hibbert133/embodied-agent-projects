import copy,unittest
from unittest.mock import patch
import numpy as np
from src.probe import graybox_observer_v1 as m
from src.analysis import graybox_observer_independent_v1 as independent

def commands(n):
    return [np.asarray([(.4 if i%7<3 else -.4),(.4 if i%11<5 else -.4),0.,0.],np.float32).astype(float).tolist() for i in range(n)]

def trace(n=80,rho=.5,kappa=.2):
    # Constructed exact mean mechanics; it is not a real execution receipt.
    y=np.array([0.,.6]);target=y.copy();v=np.zeros(2);rows=[]
    for i,u in enumerate(commands(n)):
        target+=.01*np.array(u[:2]);v=rho*v+(1-rho)*kappa*(target-y);y+=v
        rows.append(dict(at_calls=i,command=u,after_xy=y.tolist()))
    return dict(initial_xy=[0.,.6],steps=rows)

class Graybox(unittest.TestCase):
    def observer(self,**kw):return m.Observer([0.,.6],[m.default_parameters()]*2,**kw)
    def test_noise_clipping_moments_match_independent_quadrature(self):
        for mu in (-2.,-1.02,-.99,-.2,0.,.99,1.02,2.):
            with self.subTest(mu=mu):np.testing.assert_allclose(m.moments(mu,.05),independent.clipped_moments(mu),atol=2e-12,rtol=2e-10)
    def test_zero_noise_and_outside_tail(self):
        self.assertEqual(m.moments(2.,0.),(1.,0.,0.));self.assertEqual(m.moments(.2,0.),(.2,0.,1.))
    def test_noise_must_precede_final_action_clipping(self):
        correct=m.moments(1.05,.05)[0];wrong=m.moments(1.,.05)[0]
        self.assertGreater(correct-wrong,.01)
    def test_affine_row_mapping_is_forward_not_inverse_or_transposed(self):
        b=m.initial_axis(0,0.);b['mean'][3:]=[.8,.2,-.1]
        _,d=m.advance(0,b,[.5,-.25,0.,0.],m.default_parameters())
        self.assertAlmostEqual(d['action_mean'],.25,places=11)
    def test_scalar_prediction_and_conditional_update_match_matrix_form(self):
        ob=self.observer(q_parameter=.001);ref=copy.deepcopy(ob.beliefs);ledger={}
        for i,row in enumerate(trace(24)['steps']):
            p=ob.plan(row['command'],i,ledger)
            for axis in range(2):
                rp=independent.predict(axis,ref[axis],row['command'],ob.plants[axis],ob.q_parameter)
                np.testing.assert_allclose(p['predicted_beliefs'][axis]['mean'],rp['mean'],atol=1e-11)
                np.testing.assert_allclose(p['predicted_beliefs'][axis]['covariance'],rp['covariance'],atol=1e-11)
                ref[axis],_=independent.update(rp,row['after_xy'][axis],ob.plants[axis])
            ob.consume(p,row['after_xy'],i+1,ledger)
            for a in range(2):np.testing.assert_allclose(ob.beliefs[a]['mean'],ref[a]['mean'],atol=1e-10)
        self.assertEqual(ledger,dict(axis_predictions=48,axis_observations=48))
    def test_independent_implementation_does_not_call_main_model(self):
        b=m.initial_axis(0,0.)
        with patch.object(m,'advance',side_effect=AssertionError('disabled')),patch.object(m,'moments',side_effect=AssertionError('disabled')):
            self.assertEqual(len(independent.predict(0,b,[.25,0.,0.,0.],m.default_parameters(),0.)['mean']),6)
    def test_exact_linear_mean_on_constructed_nominal_model(self):
        ob=self.observer(known_nominal=True)
        forecast=ob.forecast(commands(80));true=trace(80)['steps']
        np.testing.assert_allclose([r['position_xy'] for r in forecast],[r['after_xy'] for r in true],atol=2e-11)
    def test_forecast_branches_do_not_change_actual_filter_state(self):
        ob=self.observer();before=m.digest(ob.snapshot());a=ob.forecast([[.5,0.,0.,0.]]*4);b=ob.forecast([[-.5,0.,0.,0.]]*4)
        self.assertGreater(a[-1]['position_xy'][0],b[-1]['position_xy'][0]);self.assertEqual(before,m.digest(ob.snapshot()))
    def test_no_fake_earliest_displacement(self):
        ob=self.observer();self.assertEqual([b['mean'][2] for b in ob.beliefs],[0.,0.]);self.assertEqual([b['covariance'][2][2] for b in ob.beliefs],[1e-4]*2)
    def test_parameter_state_cross_covariance_is_retained(self):
        ob=self.observer();p=ob.plan([.5,.25,0.,0.],0)
        self.assertGreater(abs(p['predicted_beliefs'][0]['covariance'][0][3]),0.)
    def test_diagonal_and_cross_axis_parameter_priors_have_correct_orientation(self):
        a=m.initial_axis(0,0.)['covariance'];b=m.initial_axis(1,.6)['covariance']
        self.assertEqual(a[3][3],b[4][4]);self.assertEqual(a[4][4],b[3][3]);self.assertGreater(a[3][3],a[4][4])
    def test_invalid_observation_does_not_partially_update_state(self):
        ob=self.observer();p=ob.plan([0.,0.,0.,0.],0);before=m.digest(ob.snapshot())
        with self.assertRaises(ValueError):ob.consume(p,[0.,float('nan')],1)
        self.assertEqual(m.digest(ob.snapshot()),before);self.assertEqual(ob.pending,p)
    def test_nominal_declared_training_keeps_affine_parameters_fixed(self):
        ob=self.observer(known_nominal=True)
        for row in trace(8)['steps']:ob.consume(ob.plan(row['command'],row['at_calls']),row['after_xy'],row['at_calls']+1)
        for i,b in enumerate(ob.beliefs):self.assertEqual(b['mean'][3:],([1.,0.,0.] if i==0 else [0.,1.,0.]))
    def test_joint_filter_updates_parameters_from_public_innovation(self):
        ob=self.observer();p=ob.plan([.5,.25,0.,0.],0);ob.consume(p,[.001,.6],1)
        self.assertNotEqual(ob.beliefs[0]['mean'][3:],[1.,0.,0.])
    def test_duplicate_or_skipped_observation_rejected(self):
        for clock in (0,2,True):
            ob=self.observer();p=ob.plan([0.,0.,0.,0.],0)
            with self.subTest(clock=clock),self.assertRaises(ValueError):ob.consume(p,[0.,.6],clock)
    def test_new_plan_before_previous_observation_rejected(self):
        ob=self.observer();ob.plan([0.,0.,0.,0.],0)
        with self.assertRaises(ValueError):ob.plan([0.,0.,0.,0.],0)
    def test_modified_saved_command_or_state_rejected(self):
        ob=self.observer();p=ob.plan([0.,0.,0.,0.],0);p['command'][0]=.5
        with self.assertRaises(ValueError):ob.consume(p,[0.,.6],1)
        ob=self.observer();p=ob.plan([0.,0.,0.,0.],0);ob.beliefs[0]['mean'][0]=.01
        with self.assertRaises(ValueError):ob.consume(p,[0.,.6],1)
    def test_snapshot_is_a_copy(self):
        ob=self.observer();s=ob.snapshot();s['current_xy'][0]=4.;self.assertEqual(ob.current[0],0.)
    def test_policy_oracle_identity_and_future_fields_rejected(self):
        base=trace(2)
        for key in ('seed','matrix_xy','actual_noise','mocap_pos_oracle','future_result'):
            bad=copy.deepcopy(base);bad[key]=0
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_trace(bad)
    def test_unbounded_nonfloat32_or_boolean_command_rejected(self):
        for command in ([1.1,0.,0.,0.],[.1,0.,0.,0.],[True,0.,0.,0.]):
            with self.subTest(command=command),self.assertRaises(ValueError):self.observer().plan(command,0)
    def test_future_or_noncontiguous_trace_rejected(self):
        t=trace(2);t['steps'][1]['at_calls']=3
        with self.assertRaises(ValueError):m.validate_trace(t)
    def test_empty_training_or_zero_length_segment_rejected(self):
        for traces in ([],[dict(initial_xy=[0.,.6],steps=[])]):
            with self.subTest(traces=traces),self.assertRaises(ValueError):m.fit_nominal_grid(traces)
    def test_finite_grid_recovers_constructed_planted_response(self):
        ledger={};fit=m.fit_nominal_grid([trace(80)],ledger=ledger)
        self.assertEqual(fit['selected_grid_indices'],[4,4]);self.assertEqual(ledger['nominal_grid_candidate_evaluations'],9)
        self.assertEqual(ledger['axis_predictions'],1440);self.assertEqual(ledger['axis_observations'],1440)
        self.assertFalse(fit['physical_prediction_qualified']);self.assertFalse(fit['controller_or_task_qualified'])
    def test_model_mismatch_is_not_forced_to_zero_residual(self):
        ob=m.Observer([0.,.6],[m.default_parameters(0.,.8)]*2,known_nominal=True)
        predicted=ob.forecast(commands(40));actual=trace(40)['steps']
        error=np.array([r['position_xy'] for r in predicted])-np.array([r['after_xy'] for r in actual]);self.assertGreater(np.linalg.norm(error),.001)
    def test_workspace_clipping_changes_local_jacobian(self):
        b=m.initial_axis(0,.5);b['mean'][0]=.5
        p,d=m.advance(0,b,[1.,0.,0.,0.],m.default_parameters())
        self.assertEqual(p['mean'][0],.5);self.assertTrue(d['workspace_mean_clipped']);self.assertEqual(d['jacobian'][0],[0.]*6)
    def test_covariance_remains_psd_under_repeated_updates(self):
        ob=self.observer(q_parameter=.001)
        for row in trace(40)['steps']:
            ob.consume(ob.plan(row['command'],row['at_calls']),row['after_xy'],row['at_calls']+1)
            for b in ob.beliefs:self.assertGreaterEqual(np.linalg.eigvalsh(b['covariance']).min(),-1e-12)
    def test_500_step_budget_and_pending_forecast(self):
        ob=self.observer();ob.at_calls=499
        with self.assertRaises(ValueError):ob.forecast([[0.,0.,0.,0.]]*2)
        p=ob.plan([0.,0.,0.,0.],499)
        with self.assertRaises(ValueError):ob.forecast([[0.,0.,0.,0.]])
        ob.consume(p,[0.,.6],500)
        with self.assertRaises(ValueError):ob.plan([0.,0.,0.,0.],500)
    def test_invalid_parameter_covariance_and_weights_fail_closed(self):
        with self.assertRaises(ValueError):self.observer(q_parameter=True)
        with self.assertRaises(ValueError):m.parameters(dict(m.default_parameters(),rho=1.))
        b=m.initial_axis(0,0.);b['covariance'][0][0]=-1.
        with self.assertRaises(ValueError):m.advance(0,b,[0.,0.,0.,0.],m.default_parameters())
        with self.assertRaises(ValueError):m.fit_nominal_grid([trace(2)],weights=[0.])

if __name__=='__main__':unittest.main()
