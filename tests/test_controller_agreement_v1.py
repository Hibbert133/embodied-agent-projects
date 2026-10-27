import unittest
from copy import deepcopy
from unittest.mock import patch
import numpy as np
from src.analysis import controller_agreement_v1 as main
from src.analysis import controller_agreement_independent_v1 as literal


def current(success=False, terminated=False, truncated=False):
    return dict(observation=[0.]*39, success=success, terminated=terminated, truncated=truncated)


def entry(step=16):
    return dict(schema='TASK_MEMORY_OPTION_V1', task='push-v3', completed_steps=step, current=current(),
        controller=dict(source='UNCORRECTED', matrix_xy=[[1.,0.],[0.,1.]], offset=[0.]*4), integral_xy=[0.,0.], time_constant_s=.5)


def rows(raws, start=16, final=None):
    state=current(); integral=[0.,0.]; out=[]
    for i, raw in enumerate(raws):
        raw=np.asarray(raw, np.float32).astype(float).tolist()
        sent, integral=literal.command(raw, integral, 'push-v3', .5)
        after=current() if i != len(raws)-1 or final is None else final
        out.append(dict(at_calls=start+i, before=state, raw_policy=raw, command=sent, after=after)); state=after
    return out


class ControllerAgreementTests(unittest.TestCase):
    def test_known_pi_numbers(self):
        data=rows([[.25,-.25,0.,1.]])
        self.assertEqual(main.replay(entry(), data, .5)['trace'][0]['proposed_command'], [float(np.float32(.25625)),float(np.float32(-.25625)),0.,1.])

    def test_literal_agrees_for_all_tasks_rates(self):
        for task in ('push-v3','reach-v3','door-open-v3'):
            for rate in main.RATES:
                e=entry(); e['task']=task
                data=rows([[4.,-3.,2.,-2.],[.1,-.125,0.,1.]])
                self.assertEqual(main.replay(e,data,rate), literal.reconstruct(e,data,rate))

    def test_first_command_agreement_not_full_equivalence(self):
        result=main.replay(entry(),rows([[4.,4.,0.,1.],[.1,.1,0.,1.]]),8.)
        self.assertEqual((result['status'],result['matched_steps'],result['first_disagreement_at_calls']), ('FIRST_DISAGREEMENT',1,17))

    def test_disagreement_does_not_read_its_response(self):
        data=rows([[.1,.1,0.,1.]])
        data[0]['after']=object()
        result=main.replay(entry(),data,8.)
        self.assertEqual(result['matched_steps'],0)
        self.assertIsNone(result['trace'][0]['integral_after_receipt'])

    def test_disagreement_does_not_read_next_row(self):
        def records():
            yield rows([[.1,.1,0.,1.]])[0]
            raise AssertionError('future row consumed')
        self.assertEqual(main.replay(entry(),records(),8.)['status'],'FIRST_DISAGREEMENT')

    def test_full_terminal_match(self):
        result=main.replay(entry(),rows([[4.,4.,0.,1.]],final=current(success=True)),8.)
        self.assertEqual(result['status'],'MATCHED_TO_TERMINAL')
        self.assertEqual(main.loss_interval(result,16,17),[0,0])

    def test_environment_termination_is_terminal(self):
        result=main.replay(entry(),rows([[4.,4.,0.,1.]],final=current(terminated=True)),8.)
        self.assertEqual(result['status'],'MATCHED_TO_TERMINAL')

    def test_deadline_is_terminal(self):
        result=main.replay(entry(499),rows([[4.,4.,0.,1.]],start=499),8.)
        self.assertEqual(result['status'],'MATCHED_TO_TERMINAL')

    def test_short_and_empty_record_are_censored(self):
        for data in ([],rows([[4.,4.,0.,1.]])):
            self.assertEqual(main.replay(entry(),data,8.)['status'],'RIGHT_CENSORED_RECORD')

    def test_unknown_private_and_future_fields_rejected(self):
        for name in ('seed','oracle','future_loss'):
            e=entry();e[name]=1
            with self.assertRaises(ValueError): main.replay(e,[],8.)
            data=rows([[.1,.1,0.,1.]]);data[0][name]=1
            with self.assertRaises(ValueError): main.replay(entry(),data,8.)

    def test_stale_and_skipped_rows_rejected(self):
        for kind in ('at_calls','before'):
            data=rows([[4.,4.,0.,1.]])
            if kind=='at_calls': data[0][kind]=18
            else: data[0][kind]['observation'][0]=1.
            with self.assertRaises(ValueError): main.replay(entry(),data,8.)

    def test_no_step_after_success(self):
        data=rows([[4.,4.,0.,1.]],final=current(success=True)); data += rows([[4.,4.,0.,1.]],start=17)
        with self.assertRaises(ValueError): main.replay(entry(),data,8.)

    def test_invalid_rates_and_nonidentity_base_rejected(self):
        for rate in (True,.1,float('nan')):
            with self.assertRaises(ValueError): main.replay(entry(),[],rate)
        e=entry();e['controller']['source']='ESTIMATED_AFFINE'
        with self.assertRaises(ValueError): main.replay(e,[],8.)

    def test_non_float32_policy_is_not_silently_changed(self):
        data=rows([[.1,.1,0.,1.]]);data[0]['raw_policy'][0]=.1
        with self.assertRaises(ValueError): main.replay(entry(),data,8.)

    def test_conservative_loss_interval(self):
        result=main.replay(entry(),rows([[4.,4.,0.,1.],[.1,.1,0.,1.]]),8.)
        self.assertEqual(main.loss_interval(result,16,100),[-82,400])

    def test_zero_denominators_not_filled(self):
        summary=main.aggregate([dict(group=0,missing_reason='NO_ENTRY',matched_steps=None)])
        self.assertEqual(summary['allocated_pairs'],1)
        self.assertIsNone(summary['metrics']['live_mean_matched']['mean'])

    def test_equal_group_weight_not_time_steps_or_rows(self):
        def item(g,m):return dict(group=g,missing_reason=None,matched_steps=m,status='RIGHT_CENSORED_RECORD',loss_delta_interval=[0,10])
        result=main.aggregate([item(0,0),item(0,0),item(1,20)])
        self.assertEqual(result['metrics']['live_mean_matched']['mean'],10.)

    def test_independent_formula_does_not_call_main(self):
        with patch.object(main,'replay',side_effect=AssertionError('main disabled')), patch.object(main.PIPlan if hasattr(main,'PIPlan') else main.TaskMemoryMachine,'plan',side_effect=AssertionError('main PI disabled')):
            self.assertEqual(literal.reconstruct(entry(),rows([[4.,4.,0.,1.]]),8.)['matched_steps'],1)

    def test_actual_paired_divergence_and_corruption(self):
        a=rows([[4.,4.,0.,1.],[.1,.1,0.,1.]])
        prediction=main.replay(entry(),a,8.); b=deepcopy(a); b[1]['command']=prediction['trace'][-1]['proposed_command']
        s=dict(entry=entry(),entry_witness={'native':'x'},rows=a,outcome=dict(deadline_loss=500,success=False))
        t=dict(entry=entry(),entry_witness={'native':'x'},rows=b,outcome=dict(deadline_loss=500,success=False))
        self.assertEqual(literal.paired_check(s,t,prediction)['paired_common_receipts'],1)
        t['rows'][0]['after']['observation'][0]=1.
        with self.assertRaises(ValueError):literal.paired_check(s,t,prediction)

    def test_no_adoption_outcome_check(self):
        s=dict(entry=None,outcome=dict(deadline_loss=9,success=True))
        self.assertTrue(literal.paired_check(s,deepcopy(s),None)['no_adoption_outcome_equal'])
        t=deepcopy(s);t['outcome']['deadline_loss']=10
        with self.assertRaises(ValueError):literal.paired_check(s,t,None)
