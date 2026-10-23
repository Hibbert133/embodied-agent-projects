"""Pure arrays/synthetic saved records only; no simulator, policy or fit."""
from copy import deepcopy
import unittest
import numpy as np
from src.analysis import passive_response_diagnostic_v1 as core
from src.analysis import task_passive_diagnosis_v1 as pipeline
from src.probe.linear_command_preflight_v1 import LinearCommandModel,DIMENSIONS,COMMAND_SLICES,make_query,feature_vector
from tests.test_task_passive_pipeline_v1 import synthetic_record
from tests.test_task_passive_host_v1 import spec


def models(task='push-v3',bias=(0.,0.),full=False):
    result={}; j=np.array([[.001,.0002,.0003 if full else 0.,.0001 if full else 0.],[-.0001,.002,.0001 if full else 0.,-.0002 if full else 0.]])
    for f in ('H10','F20','F43'):
        size=DIMENSIONS[f]; coeff=np.zeros((size+1,2)); coeff[0]=bias; sl=COMMAND_SLICES[f]; scale=np.ones(size); scale[sl]=2.
        coeff[1+sl.start:1+sl.stop]=j.T*2.
        result['SYNTHETIC/'+f]=LinearCommandModel(task,f,np.zeros(size),scale,coeff)
    return result,j


def sequence(n=12,bias=(.0004,-.0002),vary=False,full=False):
    rng=np.random.default_rng(7); u=rng.uniform(-.6,.6,(n,4)).astype(np.float32).astype(float)
    if not full: u[:,2:]=0
    bank,j=models(bias=np.asarray(bias)+[.003,-.004],full=full)
    s=np.zeros((n+1,39)); s[:,4:7]=[.1,.7,.02]; s[:,-3:]=[.2,.8,.1]
    for i in range(n):
        s[i+1,:2]=s[i,:2]+j@u[i]+np.asarray(bias)+([i*.0001,0.] if vary else 0.)
    return s,u,bank,j


class IncrementDiagnosticTests(unittest.TestCase):
    def test_strict_query_real_history_and_unknown_future_fields(self):
        s,u,bank,_=sequence(); q=core.IncrementQuery('push-v3',3,(0,1,2,3),s[:4],u[2],u[3])
        for key in ('after','fault_oracle','seed','actual_noise','future_result'):
            d=q.to_dict(); d[key]=0
            with self.assertRaises(ValueError): core.IncrementQuery.from_dict(d)
        for steps in ((0,1,2,4),(1,2,3,4)):
            with self.assertRaises(ValueError): core.IncrementQuery('push-v3',3,steps,s[:4],u[2],u[3])
        with self.assertRaises(ValueError): core.IncrementQuery('push-v3',2,(0,1,2),s[:3],u[1],u[2])
    def test_query_is_immutable_snapshot_of_visible_arrays(self):
        s,u,bank,_=sequence(); q=core.IncrementQuery('push-v3',3,(0,1,2,3),s[:4],u[2],u[3]); before=core.forecast(q,bank)
        s[:4]=99.; u[:4]=0.
        for k,v in before.items(): np.testing.assert_array_equal(v,core.forecast(q,bank)[k])
    def test_known_constant_bias_error_is_removed_without_fitting(self):
        s,u,bank,j=sequence(); target,p=core.forecast_batch(s,u,bank)
        for f in ('H10','F20','F43'):
            np.testing.assert_allclose(p['SYNTHETIC/'+f+'/LAST_RESIDUAL'],target,atol=1e-17)
            np.testing.assert_allclose(p['SYNTHETIC/'+f+'/XY_INCREMENT'],target,atol=1e-17)
            np.testing.assert_allclose(p['SYNTHETIC/'+f+'/RAW']-target,np.tile([.003,-.004],(len(target),1)),atol=1e-17)
    def test_varying_unmodeled_bias_leaves_corresponding_increment_error(self):
        s,u,bank,_=sequence(vary=True); target,p=core.forecast_batch(s,u,bank)
        np.testing.assert_allclose(target-p['SYNTHETIC/F20/LAST_RESIDUAL'],np.tile([.0001,0.],(len(target),1)),atol=1e-17)
    def test_z_grip_increments_are_distinct_from_qualified_xy_contrasts(self):
        s,u,bank,j=sequence(full=True); target,p=core.forecast_batch(s,u,bank)
        np.testing.assert_allclose(p['SYNTHETIC/F20/ALL_INCREMENT'],target,atol=1e-17)
        np.testing.assert_allclose(target-p['SYNTHETIC/F20/XY_INCREMENT'],(u[3:,2:]-u[2:-1,2:])@j[:,2:].T,atol=1e-17)
    def test_batch_matches_original_single_feature_and_prediction_interfaces(self):
        s,u,bank,j=sequence()
        for f in ('H10','F20','F43'):
            x=core.feature_batch(s,u,f)
            for step in range(2,len(u)):
                old=make_query('push-v3',step,s[step-2:step+1],u[step])
                np.testing.assert_array_equal(x[step-2],feature_vector(old,f,u[step]))
        _,batch=core.forecast_batch(s,u,bank)
        for step in range(3,len(u)):
            q=core.IncrementQuery('push-v3',step,tuple(range(step-3,step+1)),s[step-3:step+1],u[step-1],u[step])
            for k,v in core.forecast(q,bank).items(): np.testing.assert_allclose(v,batch[k][step-3],rtol=0,atol=1e-17)
    def test_future_observation_and_command_changes_cannot_change_earlier_forecast(self):
        s,u,bank,j=sequence(); _,before=core.forecast_batch(s,u,bank)
        s[6:]+=100.; u[6:]*=-1.; _,after=core.forecast_batch(s,u,bank)
        for k in before: np.testing.assert_array_equal(before[k][:3],after[k][:3])
    def test_first_displacement_is_actual_not_fabricated_zero(self):
        s,u,bank,j=sequence(); q=core.IncrementQuery('push-v3',3,(0,1,2,3),s[:4],u[2],u[3]); p=core.forecast(q,bank)
        np.testing.assert_array_equal(p['PERSIST'],s[3,:2]-s[2,:2]); self.assertGreater(np.linalg.norm(p['PERSIST']),0)
    def test_target_normalization_is_not_applied_twice(self):
        s,u,bank,j=sequence(); model=bank['SYNTHETIC/F20']; np.testing.assert_array_equal(model.command_matrix(),j)
        _,p=core.forecast_batch(s,u,bank); np.testing.assert_allclose(p['SYNTHETIC/F20/RAW'],u[3:]@j.T+[.0034,-.0042],atol=1e-17)


class InputDiagnosticTests(unittest.TestCase):
    def test_float32_transform_then_noise_then_final_clip(self):
        fault={'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.4,0.],'deadzone_xy':[0.,0.]}
        v,_=core.apply32([.8,0.,0.,0.],fault,[-.3,0.,0.])
        expected=np.float32(np.float32(np.float32(.8)+np.float32(.4))+np.float32(-.3))
        self.assertEqual(v[0],expected); self.assertNotEqual(v[0],np.float32(1)+np.float32(-.3))
    def test_forward_map_is_not_the_inverse_parameter_map(self):
        fault={'matrix_xy':[[1.2,.1],[-.2,.8]],'bias_xy':[.1,-.1],'deadzone_xy':[0.,0.]}
        v,_=core.apply32([.2,.3,0.,0.],fault,[0.,0.,0.]); inverse=np.linalg.solve(fault['matrix_xy'],np.array([.2,.3])-fault['bias_xy'])
        self.assertGreater(np.linalg.norm(v[:2]-inverse),.01)
    def test_pi_can_increase_input_discrepancy_without_identifying_task_cause(self):
        truth={'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.1,0.],'deadzone_xy':[0.,0.]}
        r=core.input_discrepancy([.4,0,0,0],[.1,0,0,0],[.2,0,0,0],truth,[0.,0.,0.])
        self.assertGreater(r['ZERO_NOISE_INPUT_MAP']['pi_minus_base_mse'],0.)
    def test_compensating_pi_can_reduce_input_discrepancy(self):
        truth={'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.1,0.],'deadzone_xy':[0.,0.]}
        r=core.input_discrepancy([.1,0,0,0],[.2,0,0,0],[.2,0,0,0],truth,[0.,0.,0.])
        self.assertLess(r['ZERO_NOISE_INPUT_MAP']['pi_minus_base_mse'],0.)
    def test_zero_noise_map_and_same_saved_noise_are_not_equivalent(self):
        truth={'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.4,0.],'deadzone_xy':[0.,0.]}
        r=core.input_discrepancy([.8,0,0,0],[.5,0,0,0],[.7,0,0,0],truth,[-.3,0.,0.])
        self.assertNotEqual(r['ZERO_NOISE_INPUT_MAP'],r['SAME_SAVED_NOISE_INPUT_MAP'])
    def test_movement_buckets_and_fixed_policy_geometry(self):
        self.assertEqual([core.movement_segment(i) for i in (1,8,9,16,17,32,33,64)],['1-8','1-8','9-16','9-16','17-32','17-32','33-64','33-64'])
        for i in (0,65):
            with self.assertRaises(ValueError):core.movement_segment(i)
        o=np.zeros(39);o[4]=.005;self.assertEqual(core.policy_phase('push-v3',o),'PUSH_TO_GOAL')
        o[4]=.05;self.assertEqual(core.policy_phase('door-open-v3',o),'PUSH_HANDLE')


class ReplayDiagnosticTests(unittest.TestCase):
    def test_full_array_record_counts_noise_cursor_and_pi_are_reconstructable(self):
        s,c,e,w=synthetic_record(); bank,_=models(); result,rows=pipeline.describe_case(c,e,bank)
        self.assertEqual(len(rows),25);self.assertEqual(result['windows']['ALL']['prediction_steps'],22)
        self.assertEqual(result['windows']['ALL']['pi_steps'],17);self.assertTrue(all(r['prediction_mse_m2'] is None for r in rows[:3]))
    def test_wrong_noise_cursor_and_execution_order_are_detected(self):
        s,c,e,w=synthetic_record();bank,_=models();bad=deepcopy(e)
        next(v for v in bad if v['event']=='STEP_COMPLETE')['noise_cursor_after']+=1
        with self.assertRaisesRegex(ValueError,'cursor'):pipeline.describe_case(c,bad,bank)
        bad=deepcopy(e);next(v for v in bad if v['event']=='STEP_COMPLETE')['executed_action_oracle'][0]+=.01
        with self.assertRaisesRegex(ValueError,'input-map'):pipeline.describe_case(c,bad,bank)
    def test_early_success_has_missing_prediction_not_a_zero_error(self):
        s,c,e,w=synthetic_record(success_at=2);bank,_=models();result,rows=pipeline.describe_case(c,e,bank)
        self.assertEqual(result['windows']['ALL']['prediction_steps'],0);self.assertIsNone(result['windows']['ALL']['mean_prediction_mse_m2'])
        self.assertEqual(result['c8_missing_reason'],'SUCCESS')
    def test_raw_program_has_no_c8_parameter_and_no_fabricated_fit(self):
        s,c,e,w=synthetic_record(spec('RAW_TASK_PI'));bank,_=models();result,rows=pipeline.describe_case(c,e,bank)
        self.assertIsNone(result['c8_fit']);self.assertEqual(result['c8_missing_reason'],'PROGRAM_WITHOUT_C8')
    def test_zero_length_window_and_missing_pi_remain_null(self):
        acc=pipeline.finish(pipeline.new_acc(['ZERO','PERSIST']));self.assertIsNone(acc['mean_prediction_mse_m2']);self.assertIsNone(acc['mean_pi_minus_base_input_mse'])
    def test_group_weighting_is_not_time_step_weighting(self):
        ts=[]
        for group,n,error in ((0,500,1.),(0,10,9.),(1,10,3.)):
            a=pipeline.new_acc(['ZERO']);a['actual_steps']=a['prediction_steps']=n;a['mse_sum']['ZERO']=n*error
            ts.append({'cohort':'QUAL','group':group,'task':'push-v3','context':'UNCHANGED','style':'NO_PROBE','time_constant_s':None,'windows':{'ALL':pipeline.finish(a)}})
        rows=pipeline.summarize(ts);r=next(r for r in rows if r['cohort']=='QUAL' and r['task']==r['context']==r['window']=='ALL')
        self.assertEqual(r['group_mean_mse_m2']['ZERO'],4.);self.assertEqual(r['allocated_trajectories'],3)
        missing=next(r for r in rows if r['task']=='reach-v3' and r['context']=='UNCHANGED');self.assertIsNone(missing['group_mean_mse_m2'])


if __name__=='__main__':unittest.main()
