from copy import deepcopy
import unittest
import numpy as np
from src.probe import occam_performance_core_v1 as core
from src.probe import occam_public_history_v1 as public
from src.analysis.occam_performance_independent_v1 import batch_posterior


def query(n=0):
    initial=dict(observation=[0.]*39,success=False,terminated=False,truncated=False);history=[];current=initial
    for i in range(n):
        after=deepcopy(current);after['observation'][0]+=.01
        history.append(dict(at_calls=i,before=current,command=[.25,0.,0.,0.],after=after));current=after
    return dict(schema='OCCAM_PUBLIC_HISTORY_V1',task='push-v3',completed_steps=n,initial=initial,history=history,
        integral_xy=[0.,0.],candidate_time_constant_s=.5,evaluation_steps=8)


def session(start=0):return core.FeedbackSession([0.,0.],np.eye(2),.1*np.eye(2),[[.25]],completed_steps=start)
def declare(s,start=0):return s.declare(np.array([[[1.,0.]],[[0.,1.]],[[1.,1.]],[[2.,0.]]]),completed_steps=start,evaluation_steps=8,reward_weights=[1.],beta=0.,public_query_sha256='a'*64)


class PerformanceCoreTests(unittest.TestCase):
    def test_scalar_update_known_values(self):
        p=core.update([0.],[[1.]],[[1.]],[1.],[[.1]],[[.25]])
        self.assertAlmostEqual(p['mean'][0],1.1/1.35)
        self.assertAlmostEqual(p['covariance'][0,0],1.1*.25/1.35)

    def test_non_square_sequence_matches_whole_gaussian_conditioning(self):
        rng=np.random.default_rng(71);mean=rng.normal(size=3);P=np.eye(3);Q=np.diag([.1,.02,0.]);R=np.array([[.2,.04],[.04,.3]])
        H=rng.normal(size=(5,2,3));Y=rng.normal(size=(5,2));m,p=mean.copy(),P.copy()
        for h,y in zip(H,Y):v=core.update(m,p,h,y,Q,R);m,p=v['mean'],v['covariance']
        bm,bp=batch_posterior(mean,P,H,Y,Q,R);np.testing.assert_allclose(m,bm,atol=1e-11);np.testing.assert_allclose(p,bp,atol=1e-11)

    def test_zero_process_noise_and_rank_deficient_prior(self):
        P=np.diag([1.,0.]);H=np.array([[[1.,2.]],[[2.,3.]]]);Y=np.array([[1.],[2.]])
        m=np.zeros(2);p=P.copy()
        for h,y in zip(H,Y):r=core.update(m,p,h,y,np.zeros((2,2)),[[.1]]);m,p=r['mean'],r['covariance']
        b,c=batch_posterior(np.zeros(2),P,H,Y,np.zeros((2,2)),[[.1]]);np.testing.assert_allclose(m,b);np.testing.assert_allclose(p,c,atol=1e-12)

    def test_forecast_separates_latent_and_measurement_uncertainty(self):
        p=core.forecast([2.],[[3.]],[[2.]],[[.5]])
        self.assertEqual(p['mean'][0],4.);self.assertEqual(p['latent_covariance'][0,0],12.);self.assertEqual(p['observation_covariance'][0,0],12.5)

    def test_orientation_private_and_invalid_covariance_rejected(self):
        with self.assertRaises(ValueError):core.update([0.,0.,0.],np.eye(3),np.ones((3,2)),[0.,0.],np.eye(3),np.eye(2))
        for R in ([[0.]], [[-1.]], [[float('nan')]]):
            with self.assertRaises(ValueError):core.update([0.],[[1.]],[[1.]],[1.],[[0.]],R)
        with self.assertRaises(ValueError):core.update([0.,0.],[[1.,.2],[0.,1.]],[[1.,0.]],[1.],np.eye(2),[[1.]])

    def test_inputs_not_mutated(self):
        mean=np.array([.2]);P=np.array([[1.]]);before=(mean.copy(),P.copy())
        core.update(mean,P,[[1.]],[2.],[[.1]],[[.2]])
        np.testing.assert_array_equal(mean,before[0]);np.testing.assert_array_equal(P,before[1])

    def test_signed_confidence_score_changes_choice(self):
        p=[dict(mean=[0.],latent_covariance=[[.1]]),dict(mean=[.1],latent_covariance=[[4.]])]
        self.assertEqual(core.choose(p,[1.],1.)[0],1);self.assertEqual(core.choose(p,[1.],-1.)[0],0)

    def test_linear_reward_propagates_cross_covariance(self):
        p=[dict(mean=[1.,2.],latent_covariance=[[1.,.5],[.5,2.]])]
        self.assertAlmostEqual(core.choose(p,[1.,-1.],1.)[1][0],-1+np.sqrt(2.))

    def test_stable_ties_use_given_candidate_order(self):
        p=[dict(mean=[0.],latent_covariance=[[1.]])]*4
        self.assertEqual(core.choose(p,[1.],0.)[0],0)

    def test_declaration_used_once_and_basis_is_saved(self):
        s=session();p=declare(s);before=s.cov.copy();result=s.complete(p,completed_steps=8,observed_performance=[1.],executed_rate=p['selected_rate'])
        self.assertEqual(result['version'],1);self.assertFalse(np.array_equal(s.cov,before))
        with self.assertRaises(ValueError):s.complete(p,completed_steps=8,observed_performance=[1.],executed_rate=p['selected_rate'])

    def test_tamper_mismatched_gain_early_feedback_rejected(self):
        for kind in ('tamper','gain','early'):
            s=session();p=declare(s);mean=s.mean.copy()
            if kind=='tamper':p['bases'][0][0][0]=2.
            with self.assertRaises(ValueError):s.complete(p,completed_steps=7 if kind=='early' else 8,observed_performance=[1.],executed_rate=8. if kind=='gain' else p['selected_rate'])
            np.testing.assert_array_equal(s.mean,mean);self.assertEqual(s.version,0)

    def test_pending_and_budget_cannot_be_bypassed(self):
        s=session();declare(s)
        with self.assertRaises(ValueError):declare(s)
        with self.assertRaises(ValueError):declare(session(495),495)
        with self.assertRaises(ValueError):declare(session(1),0)

    def test_partial_end_keeps_posterior_and_elapsed_steps(self):
        s=session();p=declare(s);before=core.digest([s.mean,s.cov]);r=s.end_partial(p,completed_steps=3,reason='SUCCESS')
        self.assertEqual(r['status'],'NO_UPDATE_PARTIAL_WINDOW');self.assertEqual(s.completed_steps,3);self.assertEqual(before,core.digest([s.mean,s.cov]))
        with self.assertRaises(ValueError):declare(s,3)

    def test_public_empty_history_is_masked_with_real_initial(self):
        q=query();q['initial']['observation'][0]=.5;x,d=public.features(q,4)
        self.assertEqual(x.shape,(332,));self.assertEqual(d.shape,(87,));self.assertTrue((x==0).all());self.assertEqual(d[0],.5);self.assertEqual(d[39],.5)

    def test_real_history_masks_and_candidate_only_feature_difference(self):
        q=query(2);x,d=public.features(q,4);matrix=x.reshape(4,83)
        np.testing.assert_array_equal(matrix[:2],np.zeros((2,83)));np.testing.assert_array_equal(matrix[2:,-1],[1.,1.])
        z=deepcopy(q);z['candidate_time_constant_s']=2.;a,b=public.features(z,4)
        np.testing.assert_array_equal(x,a);self.assertEqual(np.flatnonzero(d!=b).tolist(),[83])

    def test_nested_oracle_future_unknown_fields_rejected(self):
        for location in ('top','state','row'):
            q=query(1)
            if location=='top':q['future_loss']=100
            elif location=='state':q['initial']['oracle']=1
            else:q['history'][0]['seed']=1
            with self.assertRaises(ValueError):public.features(q,4)

    def test_missing_history_and_terminal_feedback_rejected(self):
        q=query(2);q['history']=q['history'][1:]
        with self.assertRaises(ValueError):public.features(q,4)
        q=query(1);q['history'][-1]['after']['success']=True
        with self.assertRaises(ValueError):public.features(q,4)

    def test_stale_history_nonfloat32_send_and_budget_rejected(self):
        for kind in ('stale','nonfloat32','budget'):
            q=query(1)
            if kind=='stale':q['history'][0]['at_calls']=2
            elif kind=='nonfloat32':q['history'][0]['command'][0]=.1
            else:q['evaluation_steps']=500
            with self.assertRaises(ValueError):public.features(q,4)
