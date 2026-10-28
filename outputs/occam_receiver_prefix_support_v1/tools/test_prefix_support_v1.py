"""Constructed public arrays only. No environment, fixed-policy query or API."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
import numpy as np
import prefix_engine_v1 as e
import prefix_audit_v1 as a
from src.probe import occam_performance_core_v1 as pc
from src.probe.occam_qualification_provider_v1 import TrainedProvider
from src.probe.occam_training_program_v1 import OccamProvider,constructed_bank


def fixture(indices=(0,0),short=False):
    used=[16]*len(indices)
    if short and used:used[-1]=9
    end=16+sum(used);initial=dict(observation=[0.]*39,success=False,terminated=False,truncated=False)
    history=[];before=deepcopy(initial)
    for n in range(end):
        after=deepcopy(initial);after['success']=n+1==end
        history.append(dict(at_calls=n,before=deepcopy(before),command=[0.]*4,after=after));before=after
    value=dict(schema='OCCAM_PUBLIC_TRAIN_TRAJECTORY_V1',task='push-v3',initial=initial,history=history,windows=[])
    cursor=16
    for j,(index,k) in enumerate(zip(indices,used)):
        terminal=j+1==len(indices)
        q=dict(schema='OCCAM_PUBLIC_HISTORY_V1',task='push-v3',completed_steps=cursor,initial=deepcopy(initial),
            history=deepcopy(history[:cursor]),integral_xy=[0.,0.],candidate_time_constant_s=.125,evaluation_steps=16)
        m=dict(schema='OCCAM_WINDOW_COST_V1',start_at=cursor,end_at=cursor+k,planned_steps=16,actual_steps=k,
            terminal=terminal,success=terminal,host_failure=False,deadline_charge_steps=k,unexecuted_failure_penalty_steps=0,
            potential_before=0.,potential_after=0.,cost=k/500.,full_window=k==16,rows_sha256='a'*64,
            terminal_short_label_is_known=True,no_future_observations_imputed=True)
        value['windows'].append(dict(query=q,selected_rate=pc.RATES[index],measurement=m));cursor+=k
    return value


class FakeProvider:
    def __init__(self,indices,adapt=True):self.indices=indices;self.calls=0;self.feedbacks=0;self.adapt=adapt
    def declare(self,q):
        index=self.indices[self.calls];self.calls+=1
        return dict(selected_index=index,selected_rate=pc.RATES[index],at_calls=q['completed_steps'],
            evaluation_steps=q['evaluation_steps'],public_query_sha256=pc.digest(q))
    def feedback(self,d,m,current):
        self.feedbacks+=1;return dict(update_applied=self.adapt and m['full_window'])


class PrefixTests(TestCase):
    def test_first_mismatch_stops_before_any_feedback_or_later_query(self):
        p=FakeProvider([3]);row,records=e.replay(fixture((0,0,0)),'META_ADAPT',p)
        self.assertEqual((p.calls,p.feedbacks),(1,0));self.assertEqual(row['first_divergence_window'],0)
        self.assertEqual(row['source_windows_not_used_as_feedback'],3)
        self.assertNotIn('measurement',records[0]);self.assertNotIn('current',records[0])

    def test_matched_prefix_then_mismatch_has_no_wrong_action_label(self):
        p=FakeProvider([0,3]);row,records=e.replay(fixture(),'META_ADAPT',p)
        self.assertEqual((p.calls,p.feedbacks),(2,1));self.assertEqual(row['matching_windows'],1)
        self.assertNotIn('feedback',records[-1]);self.assertEqual(row['matching_fraction'],.5)

    def test_all_choices_match_is_not_a_target_outcome(self):
        row,_=e.replay(fixture(),'META_ADAPT',FakeProvider([0,0]))
        self.assertEqual(row['status'],'ALL_OBSERVED_RATE_CHOICES_MATCH')
        self.assertIsNone(row['target_task_loss']);self.assertIsNone(row['target_task_success'])
        self.assertFalse(row['independent_deployment']);self.assertTrue(row['target_was_trained_on_this_source'])

    def test_no_window_never_queries_receiver(self):
        p=FakeProvider([]);row,records=e.replay(fixture(()),'META_ADAPT',p)
        self.assertEqual(p.calls,0);self.assertEqual(records,[]);self.assertIsNone(row['matching_fraction'])
        self.assertEqual(row['status'],'NO_RECEIVER_DECISION')

    def test_terminal_short_matched_window_does_not_update(self):
        row,_=e.replay(fixture((0,),short=True),'META_ADAPT',FakeProvider([0]))
        self.assertEqual(row['analysis_posterior_updates'],0);self.assertEqual(row['matching_windows'],1)

    def test_frozen_receiver_has_no_parameter_update(self):
        p=TrainedProvider(constructed_bank(1),adapt=False)
        row,records=e.replay(fixture((0,)),'META_FROZEN',p)
        self.assertEqual(row['analysis_posterior_updates'],0)
        np.testing.assert_array_equal(p.session.mean,p.delegate.bank['prior']['mean'])
        self.assertEqual(records[0]['feedback']['model_state_before_sha256'],records[0]['feedback']['model_state_after_sha256'])

    def test_real_provider_full_feedback_and_independent_scalar_reconstruction(self):
        bank=constructed_bank(1);value=fixture((0,));p=TrainedProvider(bank,adapt=True)
        row,records=e.replay(value,'META_ADAPT',p)
        self.assertEqual(row['analysis_posterior_updates'],1)
        self.assertEqual(a.verify_replay(value,'META_ADAPT',row,records,bank)['posterior_updates'],1)

    def test_real_provider_short_retains_prior(self):
        bank=constructed_bank(1);value=fixture((0,),short=True)
        row,records=e.replay(value,'META_ADAPT',TrainedProvider(bank,adapt=True))
        self.assertEqual(a.verify_replay(value,'META_ADAPT',row,records,bank)['posterior_updates'],0)

    def test_future_history_is_rejected(self):
        v=fixture();v['windows'][0]['query']['history'].append(v['history'][16])
        with self.assertRaises(ValueError):e.replay(v,'META_ADAPT',FakeProvider([0]))

    def test_private_query_field_is_rejected(self):
        v=fixture();v['windows'][0]['query']['true_fault']=1
        with self.assertRaises(ValueError):e.replay(v,'META_ADAPT',FakeProvider([0]))

    def test_window_order_error_is_rejected(self):
        v=fixture();v['windows'][1]['query']['completed_steps']=31
        with self.assertRaises(ValueError):e.replay(v,'META_ADAPT',FakeProvider([0,0]))

    def test_unchanged_query_contract(self):
        p=FakeProvider([0]);original=p.declare
        def bad(q):
            d=original(q);q['integral_xy'][0]=.1;return d
        p.declare=bad
        with self.assertRaises(ValueError):e.replay(fixture((0,)),'META_ADAPT',p)

    def test_illegal_selected_index_is_rejected(self):
        p=FakeProvider([0]);original=p.declare
        def bad(q):
            d=original(q);d['selected_index']=4;return d
        p.declare=bad
        with self.assertRaises(ValueError):e.replay(fixture((0,)),'META_ADAPT',p)

    def test_false_update_on_short_window_is_rejected(self):
        p=FakeProvider([0]);p.feedback=lambda *args:dict(update_applied=True)
        with self.assertRaises(ValueError):e.replay(fixture((0,),short=True),'META_ADAPT',p)

    def test_independent_audit_rejects_mismatch_feedback_and_later_queries(self):
        v=fixture((3,));bank=constructed_bank(1);row,records=e.replay(v,'META_ADAPT',TrainedProvider(bank,adapt=True))
        wrong=deepcopy(records);wrong[0]['feedback']={}
        with self.assertRaises(ValueError):a.verify_replay(v,'META_ADAPT',row,wrong,bank)
        wrong=deepcopy(records)+deepcopy(records)
        with self.assertRaises(ValueError):a.verify_replay(v,'META_ADAPT',row,wrong,bank)

    def test_independent_audit_runs_with_all_main_model_calls_disabled(self):
        v=fixture((0,));bank=constructed_bank(1);row,records=e.replay(v,'META_ADAPT',TrainedProvider(bank,adapt=True))
        def denied(*args,**kwargs):raise AssertionError('main arithmetic forbidden')
        with patch.multiple(pc,forecast=denied,update=denied,choose=denied,basis_forward=denied),\
             patch.object(TrainedProvider,'declare',denied),patch.object(TrainedProvider,'feedback',denied),\
             patch.object(OccamProvider,'declare',denied),patch.object(e,'replay',denied):
            self.assertEqual(a.verify_replay(v,'META_ADAPT',row,records,bank)['declarations'],1)

    def test_fresh_trajectory_has_independent_prior_and_bank_unchanged(self):
        v=fixture((0,));bank=constructed_bank(1);before=pc.digest(bank)
        one=e.replay(v,'META_ADAPT',TrainedProvider(bank,adapt=True))
        two=e.replay(v,'META_ADAPT',TrainedProvider(bank,adapt=True))
        self.assertEqual(one,two);self.assertEqual(pc.digest(bank),before)

    def test_empty_group_metric_is_missing(self):
        row,_=e.replay(fixture(()),'META_ADAPT',FakeProvider([]));row['spec']=dict(group=0)
        s=e.summarize([row]);self.assertIsNone(s['equal_group_matching_fraction']);a.verify_summary([row],s)

    def test_group_weights_do_not_treat_steps_as_independent(self):
        one,_=e.replay(fixture(),'META_ADAPT',FakeProvider([0,0]));one['spec']=dict(group=0)
        zero=deepcopy(one);zero['matching_fraction']=0.;other=deepcopy(zero);other['spec']['group']=1
        rows=[one,zero,other];s=e.summarize(rows)
        self.assertEqual(s['equal_group_matching_fraction'],.25);a.verify_summary(rows,s)

    def test_unknown_receiver_and_unknown_projection_field_are_rejected(self):
        with self.assertRaises(ValueError):e.replay(fixture(),'PRETRAIN',FakeProvider([0]))
        v=fixture();v['private_state']=1
        with self.assertRaises(ValueError):e.replay(v,'META_ADAPT',FakeProvider([0]))
