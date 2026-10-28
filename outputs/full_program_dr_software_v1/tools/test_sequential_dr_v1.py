"""Constructed finite trees and arrays only; no simulator or model fitting."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
from unittest.mock import patch
import unittest
import sequential_dr_v1 as m
import sequential_dr_audit_v1 as a


def sample(costs=(1,2),*,success=True,prefix=0):
    row=dict(schema=m.SCHEMA,episode_id='constructed_case',group_id='group_A',target_program_id='a'*64,
        source_prefix_id='b'*64,target_prefix_id='b'*64,target_fit_groups=['separate_training'],
        nuisance_fit_groups=['separate_Q_training'],nuisance_model_id='c'*64,
        Q_scope='REMAINING_TARGET_PROGRAM_CUTOFF_CHARGE',probability_scope='WORKING_CONDITIONAL_ACTION_KERNEL',
        support_scope='STRUCTURAL_FULL_SUPPORT_DECLARED',
        prefix=dict(actual_steps=prefix,loss_charge_steps=prefix,terminal=False,success=False),segments=[],declarations=[],
        deadline_loss=0,total_actual_steps=0,success=success)
    cursor=prefix
    for i,duration in enumerate(costs):
        terminal=i==len(costs)-1;charge=500-cursor if terminal and not success else duration
        h=format(i+1,'064x');after=format(i+2,'064x')
        row['segments'].append(dict(start_step=cursor,actual_steps=duration,loss_charge_steps=charge,terminal=terminal,
            success=success and terminal,before_history_sha256=h,after_history_sha256=after,choice_saved_ns=10+20*i,result_saved_ns=20+20*i))
        row['declarations'].append(dict(segment_index=i,feature_cutoff_step=cursor,source_history_sha256=h,computed_ns=1000000,
            actions=['A','B'],executed_index=i%2,behavior_probabilities=['1/2','1/2'],target_probabilities=['1/2','1/2'],Q_remaining_loss=[4,5]))
        cursor+=duration
    row['total_actual_steps']=cursor;row['deadline_loss']=cursor if success else 500
    if not costs:row['prefix'].update(terminal=True,success=success,loss_charge_steps=cursor if success else 500)
    return row


def census(*,correct_q,correct_mu):
    """16 exhaustive leaves of a constructed stochastic two-decision tree."""
    result=[]
    for x,y,z,w in product(range(2),repeat=4):
        source1=[F(1,2),F(1,2)];source2=[F(2,3),F(1,3)] if x==0 else [F(1,3),F(2,3)]
        target1=[F(1,3),F(2,3)];target2=[F(1,4),F(3,4)] if x==0 else [F(3,4),F(1,4)]
        row=sample((1+x+2*z,2+x+2*y+2*w));row['episode_id']='constructed_'+str((x,y,z,w))
        for i,(chosen,p,b) in enumerate(((x,target1,source1),(y,target2,source2))):
            d=row['declarations'][i];d['executed_index']=chosen;d['target_probabilities']=list(map(str,p))
            d['behavior_probabilities']=list(map(str,b if correct_mu else [F(3,5),F(2,5)]))
            d['Q_remaining_loss']=list(map(str,[F(13,2),F(15,2)] if i==0 else [F(3+x),F(5+x)])) if correct_q else [0,0]
        probability=source1[x]*source2[y]/4 # Two independent fair cost disturbances.
        result.append((probability,row))
    return result


class StandardDRTests(unittest.TestCase):
    def check(self,row):
        value=m.estimate(row);a.verify_episode(row,value);return value
    def test_independent_backward_matches_forward(self):self.check(sample())
    def test_Q_zero_exactly_equals_per_decision_IS(self):
        for _,row in census(correct_q=False,correct_mu=True):
            v=self.check(row);self.assertEqual(v['DR_exact'],v['PDIS_exact'])
    def test_correct_logger_unbiased_for_wrong_Q_on_entire_tree(self):
        total=sum((p*F(self.check(row)['DR_exact']) for p,row in census(correct_q=False,correct_mu=True)),F())
        self.assertEqual(total,F(43,6))
    def test_exact_Q_unbiased_for_wrong_weights_on_entire_tree(self):
        total=sum((p*F(self.check(row)['DR_exact']) for p,row in census(correct_q=True,correct_mu=False)),F())
        self.assertEqual(total,F(43,6))
    def test_both_nuisances_wrong_not_assumed_unbiased(self):
        total=sum((p*F(self.check(row)['DR_exact']) for p,row in census(correct_q=False,correct_mu=False)),F())
        self.assertNotEqual(total,F(43,6))
    def test_perfect_Q_still_has_noise_variance(self):
        values=[F(self.check(row)['DR_exact']) for _,row in census(correct_q=True,correct_mu=True)]
        self.assertGreater(len(set(values)),1)
    def test_deterministic_on_policy_path_equals_complete_cost(self):
        row=sample(prefix=8)
        for d in row['declarations']:
            p=['0','0'];p[d['executed_index']]='1';d['behavior_probabilities']=p;d['target_probabilities']=p.copy()
        self.assertEqual(F(self.check(row)['DR_exact']),row['deadline_loss'])
    def test_first_zero_stops_before_any_future_target_query(self):
        row=sample();row['declarations']=row['declarations'][:1]
        row['declarations'][0].update(target_probabilities=[0,1],Q_remaining_loss=[100,3])
        v=self.check(row);self.assertEqual(v['DR_exact'],'3');self.assertEqual(v['zero_weight_suffix_segments'],1)
    def test_first_zero_still_keeps_full_source_failure(self):
        row=sample(success=False);row['declarations']=row['declarations'][:1];row['declarations'][0]['target_probabilities']=[0,1]
        v=self.check(row);self.assertEqual(v['source_deadline_loss'],500);self.assertEqual(v['source_actual_steps'],3)
    def test_unused_future_target_declaration_rejected(self):
        row=sample();row['declarations'][0]['target_probabilities']=[0,1]
        with self.assertRaises(ValueError):m.estimate(row)
    def test_terminal_success_before_any_decision(self):self.assertEqual(self.check(sample((),prefix=8))['DR_exact'],'8')
    def test_terminal_failure_before_any_decision(self):self.assertEqual(self.check(sample((),prefix=8,success=False))['DR_exact'],'500')
    def test_failure_penalty_and_acquisition_not_double_charged(self):
        row=sample(success=False,prefix=8);row['segments'][-1]['loss_charge_steps']+=8
        with self.assertRaises(ValueError):m.estimate(row)
    def test_actual_short_terminal_segment_is_valid(self):self.check(sample((16,1)))
    def test_zero_duration_continue_option_is_valid(self):self.check(sample((0,3)))
    def test_future_feature_cutoff_rejected(self):
        row=sample();row['declarations'][0]['feature_cutoff_step']=1
        with self.assertRaises(ValueError):m.estimate(row)
    def test_offline_inference_wall_time_need_not_precede_historical_outcome(self):
        row=sample();self.assertGreater(row['declarations'][0]['computed_ns'],row['segments'][-1]['result_saved_ns']);self.check(row)
    def test_unsupported_action_not_imputed_or_clipped(self):
        row=sample();row['declarations'][0]['behavior_probabilities']=[1,0]
        v=self.check(row);self.assertEqual(v['status'],'NOT_ADMITTED_SUPPORT');self.assertIsNone(v['DR_exact'])
    def test_only_observed_support_is_not_a_global_certificate(self):
        row=sample();row['support_scope']='OBSERVED_ONLY';self.assertIsNone(self.check(row)['DR_exact'])
    def test_factual_zero_probability_is_corruption(self):
        row=sample();row['declarations'][0]['behavior_probabilities']=[0,1]
        with self.assertRaises(ValueError):m.estimate(row)
    def test_probability_renormalization_is_not_silent(self):
        row=sample();row['declarations'][0]['behavior_probabilities']=['1/4','1/4']
        with self.assertRaises(ValueError):m.estimate(row)
    def test_local_window_prediction_is_not_full_Q(self):
        row=sample();row['Q_scope']='NEXT_16_STEP_WINDOW'
        with self.assertRaises(ValueError):m.estimate(row)
    def test_same_evaluation_group_cannot_fit_target(self):
        row=sample();row['target_fit_groups']=['group_A']
        with self.assertRaises(ValueError):m.estimate(row)
    def test_same_evaluation_group_cannot_fit_nuisance(self):
        row=sample();row['nuisance_fit_groups']=['group_A']
        with self.assertRaises(ValueError):m.estimate(row)
    def test_common_prefix_cannot_be_assumed_for_legacy_control(self):
        row=sample();row['source_prefix_id']='d'*64
        with self.assertRaises(ValueError):m.estimate(row)
    def test_source_history_chain_mismatch_rejected(self):
        row=sample();row['segments'][1]['before_history_sha256']='e'*64
        with self.assertRaises(ValueError):m.estimate(row)
    def test_original_choice_result_clock_reversal_rejected(self):
        row=sample();row['segments'][0]['result_saved_ns']=0
        with self.assertRaises(ValueError):m.estimate(row)
    def test_extra_oracle_field_rejected(self):
        row=sample();row['perturbation_oracle']='not allowed'
        with self.assertRaises(ValueError):m.estimate(row)
    def test_no_automatic_clipping_to_loss_cap(self):
        row=sample((1,));row['declarations'][0].update(target_probabilities=[1,0],Q_remaining_loss=[2000,0])
        v=self.check(row);self.assertLess(F(v['DR_exact']),0);self.assertTrue(v['unbounded_DR_point_not_clipped'])
    def test_independent_recurrence_runs_with_main_functions_disabled(self):
        row=sample();saved=m.estimate(row)
        with patch.multiple(m,estimate=None,source_costs=None,probabilities=None,number=None):a.verify_episode(row,saved)
    def test_independent_recurrence_detects_result_tampering(self):
        row=sample();saved=m.estimate(row);saved['DR_exact']='999'
        with self.assertRaises(ValueError):a.verify_episode(row,saved)
    def test_group_mean_does_not_overweight_longer_group(self):
        values=[]
        for group,costs in (('A',(2,2)),('A',(2,2)),('B',(5,5))):
            row=sample(costs);row['group_id']=group;row['episode_id']=str(len(values));v=self.check(row);v['DR_exact']=str(sum(costs));values.append(v)
        s=m.group_summary(values);self.assertEqual(s['equal_group_DR_mean_exact'],'7');a.verify_groups(values,s)
    def test_missing_estimate_blocks_mean_without_removing_case(self):
        row=sample();row['support_scope']='UNVERIFIED';values=[self.check(row)];s=m.group_summary(values)
        self.assertEqual(s['allocated'],1);self.assertEqual(s['available'],0);self.assertIsNone(s['equal_group_DR_mean_exact']);a.verify_groups(values,s)
    def test_mixed_target_policy_versions_cannot_be_one_estimate(self):
        x=self.check(sample());y=deepcopy(x);y['episode_id']='other';y['target_program_id']='f'*64
        with self.assertRaises(ValueError):m.group_summary([x,y])


if __name__=='__main__':unittest.main()
