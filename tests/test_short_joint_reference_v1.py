"""Artificial deterministic responses only; no MetaWorld or task seeds."""
import copy
from dataclasses import asdict
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from src.probe import short_joint_reference_v1 as short
from src.probe.cold_start_response import ColdPrefix,clipped_normal_mean,infer_operator,RIDGE,SCOPE


BALANCED=((.4,0,0,0),(-.4,0,0,0),(0,.4,0,0),(0,-.4,0,0))


def model():
    g=np.zeros((16,16))
    for t in range(8):
        for k in range(t+1):g[2*t:2*t+2,2*k:2*k+2]=.01*.4**(t-k)*np.eye(2)
    return {'schema':'cold_response_v1','task':'push-v3','scope':SCOPE,'training_trajectories':128,'sigma':.05,'ridge':RIDGE,
        'offset':np.tile([1e-5,-2e-5],8).tolist(),'impulse':g.tolist(),'covariance':(1e-6*np.eye(16)).tolist(),
        'initial_hand_lower':[-.01,.59,.19],'initial_hand_upper':[.01,.61,.21],'minimum_initial_object_distance':.08,
        'training_joint_rmse_m':0.,'physical_response_qualified':False,'probability_guarantee':False}


def observations(saved,commands=BALANCED,matrix=((.9,.1),(-.1,1.1)),bias=(.05,-.04)):
    u=np.asarray(commands);n=len(u);a=np.asarray(matrix);b=np.asarray(bias)
    mean=clipped_normal_mean(u[:,:2]@a.T+b)[0]
    delta=(np.asarray(saved['offset'])[:2*n]+np.asarray(saved['impulse'])[:2*n,:2*n]@mean.ravel()).reshape(n,2)
    initial=np.zeros(39);initial[:3]=[0,.6,.2];initial[4:7]=[.1,.7,.02]
    states=[];now=initial.copy()
    for step in delta:
        now=now.copy();now[:2]+=step;states.append(now.copy())
    return ColdPrefix('push-v3',initial,tuple(map(tuple,u)),tuple(map(tuple,states)),True)


class ShortJointReferenceTest(unittest.TestCase):
    def test_rich_four_step_data_recovers_six_parameters_without_truth_input(self):
        saved=model();prefix=observations(saved);before_model=copy.deepcopy(saved);before_prefix=asdict(prefix)
        fit=short.infer_four(saved,prefix)
        self.assertTrue(fit['valid']);self.assertFalse(fit['physical_response_qualified']);self.assertFalse(fit['probability_guarantee'])
        np.testing.assert_allclose(fit['matrix_xy'],[[.9,.1],[-.1,1.1]],atol=1e-7)
        np.testing.assert_allclose(fit['bias_xy'],[.05,-.04],atol=1e-7)
        self.assertEqual(fit['observed_rows_used'],4);self.assertEqual(fit['fitted_jacobian_rank'],6)
        np.linalg.cholesky(fit['working_covariance'])
        self.assertEqual(saved,before_model);self.assertEqual(asdict(prefix),before_prefix)

    def test_clipped_gaussian_response_requires_and_uses_nonlinear_fit(self):
        saved=model();a=[[1.9,.1],[.1,1.3]];b=[.29,-.28]
        fit=short.infer_four(saved,observations(saved,matrix=a,bias=b))
        self.assertTrue(fit['valid']);self.assertGreater(fit['nfev'],1)
        np.testing.assert_allclose(fit['matrix_xy'],a,atol=1e-6);np.testing.assert_allclose(fit['bias_xy'],b,atol=1e-6)

    def test_x_only_or_unresponsive_prefix_is_rejected_before_optimizer(self):
        saved=model();x_only=((.4,0,0,0),)*2+((-.4,0,0,0),)*2
        with patch.object(short,'least_squares') as optimize:
            fit=short.infer_four(saved,observations(saved,x_only));self.assertFalse(fit['valid']);self.assertEqual(fit['input_design_rank'],2)
            optimize.assert_not_called()
        silent=copy.deepcopy(saved);silent['impulse'][:8]=np.zeros((8,16)).tolist()
        with patch.object(short,'least_squares') as optimize:
            fit=short.infer_four(silent,observations(silent));self.assertEqual(fit['reason'],'MARGINAL_RESPONSE_UNIDENTIFIABLE');optimize.assert_not_called()

    def test_future_model_rows_and_cross_covariance_are_not_conditioned_on(self):
        saved=model();prefix=observations(saved);other=copy.deepcopy(saved)
        other['offset'][8:]=[1000.]*8
        cov=np.asarray(other['covariance']);cov[:8,8:]=.6e-6*np.eye(8);cov[8:,:8]=.6e-6*np.eye(8);other['covariance']=cov.tolist()
        # This would change the first block of the full precision, but not the
        # correct marginal likelihood of the four observed responses.
        self.assertFalse(np.array_equal(np.linalg.inv(cov)[:8,:8],np.linalg.inv(np.asarray(saved['covariance']))[:8,:8]))
        self.assertEqual(short.infer_four(saved,prefix),short.infer_four(other,prefix))

    def test_old_eight_step_interface_is_preserved_and_no_silent_truncation(self):
        saved=model();four=observations(saved);eight=observations(saved,BALANCED*2)
        self.assertEqual(infer_operator(saved,four)['reason'],'INCOMPLETE_EIGHT_STEP_PREFIX')
        self.assertTrue(infer_operator(saved,eight)['valid'])
        rejected=short.infer_four(saved,eight)
        self.assertEqual(rejected['reason'],'EXACT_FOUR_STEP_PREFIX_REQUIRED')
        self.assertEqual(rejected['observed_prefix_steps'],8);self.assertEqual(rejected['observed_rows_used'],0)

    def test_outside_inverse_domain_does_not_produce_an_approved_controller(self):
        saved=model();fit=short.infer_four(saved,observations(saved,matrix=[[.1,0],[0,.1]],bias=[0,0]))
        self.assertFalse(fit['valid']);self.assertIsNone(fit['working_covariance'])
        self.assertEqual(fit['reason'],'OPTIMIZER_OR_INVERSE_DOMAIN_FAILURE')

    def test_unsuccessful_optimizer_does_not_approve_even_in_domain_parameters(self):
        saved=model();failed=SimpleNamespace(x=np.array([1.,0,0,0,1.,0]),nfev=64,success=False)
        with patch.object(short,'least_squares',return_value=failed):fit=short.infer_four(saved,observations(saved))
        self.assertFalse(fit['valid']);self.assertIsNone(fit['working_covariance']);self.assertEqual(fit['nfev'],64)

    def test_schema_task_and_controlled_reset_scope_fail_closed(self):
        saved=model();prefix=observations(saved);data=asdict(prefix)
        for field in ('seed','fault_oracle','future_observations','executed_action_oracle'):
            with self.assertRaises(ValueError):ColdPrefix.from_dict({**data,field:1})
        with self.assertRaises(ValueError):short.infer_four({**saved,'fault_oracle':{}},prefix)
        with self.assertRaises(ValueError):short.infer_four(saved,data)
        other=copy.deepcopy(saved);other['task']='reach-v3'
        with self.assertRaises(ValueError):short.infer_four(other,prefix)
        data['initial_observation']=list(data['initial_observation']);data['initial_observation'][0]=.2
        self.assertEqual(short.infer_four(saved,ColdPrefix.from_dict(data))['reason'],'OUTSIDE_CONTROLLED_RESET_SCOPE')

    def test_estimation_does_not_consume_global_randomness(self):
        saved=model();prefix=observations(saved);numpy_before=np.random.get_state();python_before=random.getstate()
        self.assertTrue(short.infer_four(saved,prefix)['valid'])
        np.testing.assert_equal(np.random.get_state(),numpy_before);self.assertEqual(random.getstate(),python_before)


if __name__=='__main__':unittest.main()
