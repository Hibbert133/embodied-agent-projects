"""Public-array contracts; never create, reset, or advance an environment."""
from copy import deepcopy
import unittest
import numpy as np
from src.probe.occam_performance_core_v1 import basis_forward,forecast,update,digest
from src.probe.occam_window_cost_v1 import measure
from src.probe.occam_training_behavior_v1 import BehaviorProvider
from src.analysis import occam_training_data_v1 as data
from src.analysis import occam_reference_train_io_v1 as allocation


def trace(n=50):
    initial=dict(observation=[0.]*39,success=False,terminated=False,truncated=False);initial['observation'][2]=.25;initial['observation'][5]=.6;initial['observation'][36:39]=[.2,.8,.1]
    rows=[];current=deepcopy(initial)
    for i in range(n):
        after=deepcopy(current);after['observation'][0]+=.0005;after['observation'][4]+=.00025
        if i==n-1:after['success']=True
        rows.append(dict(at_calls=i,before=current,command=[.125,0.,0.,0.],after=after));current=after
    result=dict(schema='OCCAM_PUBLIC_TRAIN_TRAJECTORY_V1',task='push-v3',initial=initial,history=rows,windows=[])
    for at in range(16,n,16):
        q=dict(schema='OCCAM_PUBLIC_HISTORY_V1',task='push-v3',completed_steps=at,initial=initial,history=rows[:at],integral_xy=[0.,0.],candidate_time_constant_s=.125,evaluation_steps=min(16,500-at))
        m=measure('push-v3',at,rows[at-1]['after'],rows[at:min(at+16,n)],q['evaluation_steps'])
        result['windows'].append(dict(query=q,selected_rate=.5,measurement=m))
    return result


def bank():
    rng=np.random.default_rng(82)
    return dict(schema='OCCAM_PERFORMANCE_BASIS_V1',dimensions=dict(history=664,descriptor=87,outputs=1,bases=2),
        encoder=[dict(weight=rng.normal(0,.02,(3,664)).tolist(),bias=[.1,.2,-.1])],
        head=[dict(weight=rng.normal(0,.03,(4,90)).tolist(),bias=[.3,.1,.2,.4]),dict(weight=rng.normal(0,.04,(2,4)).tolist(),bias=[.2,-.3])],
        prior=dict(mean=[.2,-.1],covariance=[[1.,.2],[.2,.7]],process_covariance=[[.02,0.],[0.,.01]],measurement_covariance=[[.2]]))


class TrainingDataTests(unittest.TestCase):
    def test_full_actual_tail_and_known_terminal_short_label_retained(self):
        s=data.project(trace());self.assertEqual(s['history'].shape,(3,664));self.assertEqual(s['targets'].shape,(3,1))
        self.assertEqual(s['full_window'].tolist(),[True,True,False]);self.assertEqual(s['terminal'].tolist(),[False,False,True])

    def test_early_end_kept_as_empty_episode_with_reason(self):
        s=data.project(trace(8));self.assertEqual(s['history'].shape,(0,664));self.assertEqual(s['descriptor'].shape,(0,87));self.assertIsNotNone(s['missing_reason'])

    def test_oracle_registry_and_nested_noise_are_rejected(self):
        for mutate in (lambda t:t.update(seed=7),lambda t:t['windows'][0]['query'].update(true_fault={}),lambda t:t['history'][0].update(noise=[0,0,0])):
            t=trace();mutate(t)
            with self.assertRaises((ValueError,KeyError)):data.project(t)

    def test_future_omitted_and_repeated_query_history_rejected(self):
        for which in ('future','omitted','repeated'):
            t=trace();q=t['windows'][0]['query']
            if which=='future':q['history']=t['history'][:17]
            elif which=='omitted':q['history']=q['history'][1:]
            else:t['windows'].append(deepcopy(t['windows'][-1]))
            with self.assertRaises(ValueError):data.project(t)

    def test_changed_cost_or_missing_window_cannot_be_relabelled(self):
        t=trace();t['windows'][0]['measurement']['cost']+=.001
        with self.assertRaises(ValueError):data.project(t)
        t=trace();t['windows']=t['windows'][:-1]
        with self.assertRaises(ValueError):data.project(t)

    def test_real_history_must_start_from_true_initial(self):
        t=trace();t['history'][0]['before']=deepcopy(t['initial']);t['history'][0]['before']['observation'][0]=1.
        with self.assertRaises(ValueError):data.project(t)

    def test_no_future_label_enters_earlier_feature(self):
        left=trace();right=deepcopy(left)
        for i in range(32,len(right['history'])):
            row=right['history'][i];row['before']=deepcopy(right['history'][i-1]['after']);row['after']['observation'][0]+=.01
        for w in right['windows']:
            at=w['query']['completed_steps'];w['query']['history']=right['history'][:at]
            w['measurement']=measure('push-v3',at,right['history'][at-1]['after'],right['history'][at:min(at+16,50)],16)
        a=data.project(left);b=data.project(right)
        np.testing.assert_array_equal(a['history'][0],b['history'][0]);np.testing.assert_array_equal(a['descriptor'][0],b['descriptor'][0])

    def test_episode_weighting_does_not_favor_duplicate_long_windows(self):
        s=data.project(trace());empty=data.project(trace(8));long={**s}
        for k in ('history','descriptor','targets','full_window','terminal'):long[k]=np.concatenate([s[k],s[k]])
        a=data.weighted_stats([s,empty]);b=data.weighted_stats([long,empty])
        for k in ('history_mean','history_scale','descriptor_mean','descriptor_scale','target_mean','target_scale'):np.testing.assert_allclose(a[k],b[k],atol=1e-14)

    def test_padding_remains_zero_after_mean_subtraction(self):
        s=data.project(trace());stats=data.weighted_stats([s]);H=s['history'][:1].copy().reshape(1,8,83);H[:,:6]=0.
        nh,_,_=data.normalize(stats,H.reshape(1,664),s['descriptor'][:1]);np.testing.assert_array_equal(nh.reshape(1,8,83)[:,:6],0.)

    def test_task_indicators_unchanged_and_positive_scale_floor(self):
        s=data.project(trace());stats=data.weighted_stats([s]);_,x,y=data.normalize(stats,s['history'],s['descriptor'],s['targets'])
        np.testing.assert_array_equal(x[:,80:83],s['descriptor'][:,80:83]);self.assertGreaterEqual(stats['target_scale'],.05)
        self.assertTrue(np.isfinite(y).all())

    def test_empty_train_invalid_scale_and_extra_stats_fail(self):
        with self.assertRaises(ValueError):data.weighted_stats([data.project(trace(8))])
        s=data.project(trace());stats=data.weighted_stats([s])
        for bad in ({**stats,'target_scale':0.},{**stats,'oracle':1}):
            with self.assertRaises(ValueError):data.normalize(bad,s['history'],s['descriptor'])

    def test_export_folds_input_and_output_units_without_mutation(self):
        s=data.project(trace());stats=data.weighted_stats([s]);b=bank();old=digest(b);raw=data.export_raw(b,stats)
        nh,nx,_=data.normalize(stats,s['history'],s['descriptor']);p=basis_forward(b,nh,nx);q=basis_forward(raw,s['history'],s['descriptor'])
        np.testing.assert_allclose(q[:,:,:2],p*stats['target_scale'],atol=1e-13);np.testing.assert_allclose(q[:,:,2],stats['target_mean'],atol=1e-14)
        self.assertEqual(digest(b),old);self.assertEqual(raw['dimensions']['bases'],3)

    def test_folded_recursive_mean_covariance_and_constant_weight(self):
        s=data.project(trace());stats=data.weighted_stats([s]);b=bank();raw=data.export_raw(b,stats)
        nh,nx,ny=data.normalize(stats,s['history'],s['descriptor'],s['targets']);phi=basis_forward(b,nh,nx);rphi=basis_forward(raw,s['history'],s['descriptor'])
        p=b['prior'];r=raw['prior'];m,P=np.array(p['mean']),np.array(p['covariance']);rm,RP=np.array(r['mean']),np.array(r['covariance'])
        for i in range(3):
            a=forecast(m,P,phi[i],p['measurement_covariance']);z=forecast(rm,RP,rphi[i],r['measurement_covariance'])
            np.testing.assert_allclose(z['mean'],a['mean']*stats['target_scale']+stats['target_mean'],atol=1e-13)
            np.testing.assert_allclose(z['observation_covariance'],a['observation_covariance']*stats['target_scale']**2,atol=1e-13)
            a=update(m,P,phi[i],ny[i],p['process_covariance'],p['measurement_covariance']);z=update(rm,RP,rphi[i],s['targets'][i],r['process_covariance'],r['measurement_covariance'])
            m,P=a['mean'],a['covariance'];rm,RP=z['mean'],z['covariance'];self.assertEqual(rm[-1],1.);np.testing.assert_array_equal(RP[-1],0.)

    def test_export_rejects_hidden_fields_and_bad_covariances(self):
        s=data.project(trace());stats=data.weighted_stats([s]);b=bank();b['oracle']=1
        with self.assertRaises(ValueError):data.export_raw(b,stats)
        b=bank();b['prior']['process_covariance'][0][0]=-1.
        with self.assertRaises(ValueError):data.export_raw(b,stats)


class TrainingBehaviorTests(unittest.TestCase):
    def test_saved_schedule_consumes_actual_feedback_before_next_choice(self):
        t=trace();p=BehaviorProvider([0,1,2]+[3]*28);d=p.declare(t['windows'][0]['query'])
        with self.assertRaises(ValueError):p.declare(t['windows'][1]['query'])
        p.feedback(d,t['windows'][0]['measurement'],t['history'][31]['after']);second=p.declare(t['windows'][1]['query']);self.assertEqual(second['selected_rate'],.5)
        self.assertIsNone(p.session)

    def test_changed_or_repeated_feedback_rejected(self):
        t=trace();p=BehaviorProvider([0]*31);d=p.declare(t['windows'][0]['query']);bad=deepcopy(d);bad['selected_rate']=8.
        with self.assertRaises(ValueError):p.feedback(bad,t['windows'][0]['measurement'],t['history'][31]['after'])
        p.feedback(d,t['windows'][0]['measurement'],t['history'][31]['after'])
        with self.assertRaises(ValueError):p.feedback(d,t['windows'][0]['measurement'],t['history'][31]['after'])

    def test_short_terminal_is_label_only_and_closes_schedule(self):
        t=trace();p=BehaviorProvider([0]*31);w=t['windows'][-1];d=p.declare(w['query']);r=p.feedback(d,w['measurement'],t['history'][-1]['after'])
        self.assertEqual(r['online_filter_updates'],0);self.assertTrue(p.closed)
        with self.assertRaises(ValueError):p.declare(w['query'])

    def test_illegal_schedule_and_private_query_fail(self):
        for s in ([4]*31,[0]*30,[False]*31):
            with self.assertRaises(ValueError):BehaviorProvider(s)
        q=trace()['windows'][0]['query'];q['noise_state']={}
        with self.assertRaises(ValueError):BehaviorProvider([0]*31).declare(q)

    def test_full_allocation_cost_and_frozen_matched_first_gain(self):
        self.assertEqual(len(allocation.population('NATIVE')),36);self.assertEqual(len(allocation.population('TRAIN')),648)
        for a,b in zip(allocation.population('TRAIN')[::2],allocation.population('TRAIN')[1::2]):
            sa,sb=allocation.schedule(a),allocation.schedule(b);self.assertEqual(sa[0],sb[0]);self.assertEqual(len(set(sb)),1)
            np.testing.assert_array_equal(allocation.noise(a),allocation.noise(b));self.assertEqual(allocation.destination(a),allocation.destination(b))
        self.assertEqual(allocation.config()['complete_limits']['physical_frames'],684*28000)

    def test_actual_array_host_uses_behavior_provider_for_each_acquisition(self):
        from tests.test_learned_acquisition_native_v1 import FakeSession
        from src.analysis.occam_reference_train_host_v1 import run_live
        for action in allocation.ACTIONS:
            spec=next(s for s in allocation.population('NATIVE') if s['acquisition_action']==action);session=FakeSession(end=120)
            result=run_live(spec,session,lambda n:None,lambda:None)
            self.assertEqual(result['total_steps'],session.completed);self.assertEqual(result['full_feedback_windows'],0)


if __name__=='__main__':unittest.main()
