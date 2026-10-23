"""Array-only tests for causal prefix support, missingness and complete costs."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
from src.analysis import acquisition_support_v1 as a
from src.analysis.acquisition_support_sources_v1 import pid


def fixture(style='MOVE_KEEP_C8',length=24,pi_at=None,post=20,stop='SUCCESS'):
    obs=[0.]*39;initial={'observation':obs,'success':False,'terminated':False,'truncated':False}
    c={'case_id':style,'unit_id':'u','group':0,'task':'push-v3','context':'UNCHANGED','style':style,
        'time_constant_s':.5 if style in ('RAW_TASK_PI','DIRECT_TASK_PI','MOVE_KEEP_TASK_PI') else 2. if style=='MOVE_INTEGRAL_TASK_PI' else None,
        'planned_boundary':16,'initial':initial,'total_steps':length,'deadline_loss':length if stop=='SUCCESS' else 500,
        'success':stop=='SUCCESS','stop_reason':stop}
    events=[]
    for i in range(length):
        after=deepcopy(initial);after['observation'][0]=i*.001;after['success']=i==length-1 and c['success']
        events.append({'event':'STEP_COMPLETE','logical_step':i,'phase':'TASK','command':[.1,0.,0.,0.],'raw_policy':[.1,0.,0.,0.],
            'executed_action_oracle':[.1,0.,0.,0.],'after':after,'reward':0.,'info':{'episode':{'t':float(i)}},
            'simulation_time_before':i*.0125,'simulation_time_after':(i+1)*.0125,'noise_cursor_after':i+1})
    def public(kind,n):events.append({'event':'AGENT_EVENT','agent_event':kind,'public_payload':{'at_calls':n}})
    public('FIT_INTENT',4);public('FIT_INTENT',8)
    if style.startswith('MOVE_') and length>=16:
        public('MOVE_ENTRY',16)
        if post is not None:public('POST_MOVE_TASK_ENTRY',post)
    if pi_at is not None:public('PI_PLAN',pi_at)
    witness=[{'label':'INITIAL','witness':{'native_sha256':'a'*64,'comparison_python_sha256':'b'*64}}]
    return c,events,witness


class PrefixSupportTests(unittest.TestCase):
    def test_future_edit_does_not_change_earlier_prefix(self):
        c,e,w=fixture();left=a.trace(c,e,w);changed=deepcopy(e);changed[17]['executed_action_oracle'][0]=.2
        right=a.trace(c,changed,w)
        self.assertEqual(left['prefix_sha256'][16],right['prefix_sha256'][16]);self.assertNotEqual(left['prefix_sha256'][18],right['prefix_sha256'][18])
    def test_same_visible_observation_not_sufficient_for_physical_matching(self):
        c,e,w=fixture();left=a.trace(c,e,w);changed=deepcopy(e);changed[2]['executed_action_oracle'][0]=.4
        right=a.trace(c,changed,w);self.assertNotEqual(left['prefix_sha256'][8],right['prefix_sha256'][8])
    def test_initial_private_state_difference_rejected(self):
        c,e,w=fixture();changed=deepcopy(w);changed[0]['witness']['native_sha256']='c'*64
        self.assertNotEqual(a.trace(c,e,w)['prefix_sha256'][8],a.trace(c,e,changed)['prefix_sha256'][8])
    def test_phase_and_wall_timer_are_not_physical_differences(self):
        c,e,w=fixture();changed=deepcopy(e)
        for row in changed:
            if row['event']=='STEP_COMPLETE':row['phase']='APPROACH';row['raw_policy']=[1.,0.,0.,0.];row['info']['episode']['t']+=100
        self.assertEqual(a.trace(c,e,w)['prefix_sha256'],a.trace(c,changed,w)['prefix_sha256'])
    def test_early_success_invalid_fit_and_missing_movement_are_not_zeros(self):
        c,e,w=fixture(length=8,stop='INVALID_EIGHT',post=None);t=a.trace(c,e,w)
        self.assertEqual(a.availability(t,8),'INVALID_FIT_SOURCE_STOP')
        self.assertEqual(a.availability(t,16),'SOURCE_TRAJECTORY_ENDED_BEFORE_NODE')
        self.assertEqual(a.availability(t,None),'CANONICAL_MOVEMENT_NOT_EXECUTED')
        c,e,w=fixture(length=4,post=None);self.assertEqual(a.availability(a.trace(c,e,w),4),'SOURCE_ALREADY_ENDED_AT_NODE')
    def test_early_and_delayed_pi_are_not_the_same_suffix(self):
        c,e,w=fixture('DIRECT_TASK_PI',pi_at=8);t=a.trace(c,e,w)
        row={'matches_canonical_prefix':True,'at_control_steps':16}
        self.assertFalse(a.supports('BEGIN_C8_PI_0.5_NOW','BEFORE_MOVE',row,t))
        t['first_pi_at']=16;self.assertTrue(a.supports('BEGIN_C8_PI_0.5_NOW','BEFORE_MOVE',row,t))
    def test_initial_fit_and_task_steps_cannot_be_relabelled_as_acquisition(self):
        c,e,w=fixture();t=a.trace(c,e,w);row={'matches_canonical_prefix':True,'at_control_steps':20}
        self.assertFalse(a.supports('REIDENTIFY_AFTER_MOVE','AFTER_MOVE',row,t))
        self.assertFalse(a.supports('SHORT_VALIDATION_RETURN_OLD','AFTER_MOVE',row,t))
        e.append({'event':'AGENT_EVENT','agent_event':'VALIDATION_ENTRY','public_payload':{'at_calls':20}})
        with self.assertRaisesRegex(ValueError,'unqualified validation'):a.trace(c,e,w)
    def test_complete_and_remaining_losses_cancel_prefix_once(self):
        traces=[a.trace(*fixture()),a.trace(*fixture('DIRECT_C8',length=24,stop='ENVIRONMENT_ENDED')),a.trace(*fixture('RAW_TASK_PI',pi_at=0))]
        nodes=a.stage_rows('SYNTHETIC',traces);pairs=a.pairs(nodes)
        eligible=[r for r in pairs if r['both_match_canonical']]
        self.assertTrue(eligible)
        for row in eligible:self.assertEqual(row['actual_full_loss_difference'],row['remaining_loss_difference'])
        self.assertTrue(all(r['actual_full_loss_difference'] is None for r in pairs if not r['both_match_canonical']))
    def test_no_canonical_replacement_after_early_end(self):
        traces=[a.trace(*fixture(length=8,post=None)),a.trace(*fixture('DIRECT_C8')),a.trace(*fixture('RAW_TASK_PI',pi_at=0))]
        rows=a.stage_rows('SYNTHETIC',traces)
        self.assertTrue(all(not r['matches_canonical_prefix'] for r in rows if r['stage']=='BEFORE_MOVE'))
        self.assertTrue(all(r['missing_reason'] for r in rows if r['stage']=='BEFORE_MOVE'))
    def test_full_six_cell_portfolio_keeps_ties_and_future_label_warning(self):
        cases=[]
        for i in range(6):
            for style in ('RAW_TASK_PI','MOVE_KEEP_C8'):
                c,_,_=fixture(style,length=24);c.update(unit_id='u'+str(i),time_constant_s=.5 if style=='RAW_TASK_PI' else None)
                c['case_id']=c['unit_id']+'/'+pid(c);cases.append(c)
        rows=a.portfolio('SYNTHETIC',cases,1)
        self.assertEqual(len(rows),6)
        self.assertTrue(all(r['uses_future_outcomes'] and not r['deployable_method'] and not r['population_value_bound'] for r in rows))
        self.assertTrue(all(r['clairvoyant_gap_vs_RAW_PI']==0 and '|' in r['all_minimum_labels'] for r in rows))
    def test_raw_pi_history_requires_its_own_matching_movement_suffix(self):
        c,e,w=fixture('RAW_TASK_PI',pi_at=0);e[0]['command'][0]=.5;e[0]['executed_action_oracle'][0]=.5
        traces=[a.trace(*fixture()),a.trace(c,e,w)];nodes=a.stage_rows('SYNTHETIC',traces)
        support=a.support_rows('SYNTHETIC',traces,nodes)
        keep=next(r for r in support if r['stage']=='RAW_PI_BEFORE_MOVE' and r['requested_suffix']=='CONTINUE_RAW_PI_0.5')
        moving=next(r for r in support if r['stage']=='RAW_PI_BEFORE_MOVE' and r['requested_suffix']=='MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY')
        self.assertTrue(keep['supported']);self.assertFalse(moving['supported'])
    def test_independent_direct_prefix_comparison_does_not_call_main_helpers(self):
        from src.analysis import acquisition_support_audit_v1 as independent
        c,e,w=fixture();changed=deepcopy(e);changed[18]['executed_action_oracle'][0]=.2
        with patch.object(a,'trace',side_effect=AssertionError('main must not be used')),patch.object(a,'supports',side_effect=AssertionError('main must not be used')):
            left=independent.parse(c,e,w);right=independent.parse(c,changed,w)
            self.assertTrue(independent.equal(left,right,16));self.assertFalse(independent.equal(left,right,20))
    def test_independent_csv_check_rejects_zero_for_missing_value(self):
        from src.analysis import acquisition_support_audit_v1 as independent
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'x.csv').write_text('value\n0\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'missing is not zero'):independent.check_csv(folder,'x.csv',[{'value':None}])


if __name__=='__main__':unittest.main()
