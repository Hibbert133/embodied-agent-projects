"""Constructed fixtures only; never open an original scientific trajectory."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import sys
import contract_core_v1 as c
import contract_audit_v1 as a
import run_contract_v1 as run


def fixture(behavior='BLOCK_FIXED', rates=(.5,.5), early=False, terminal_return=False):
    s=dict(cohort='TRAIN',group=0,task='push-v3',seed=172100,context='UNCHANGED',
           planned_boundary=16,acquisition_action='CONTINUE',behavior=behavior)
    def state(i,end=False):return dict(observation=[float(i)]+[0.]*38,terminated=False,truncated=False,success=end)
    initial=state(0);n=8 if early else 17 if terminal_return else 33
    history=[dict(at_calls=i,before=state(i),command=[0.]*4,after=state(i+1,i+1==n)) for i in range(n)]
    events=[];local=0;stamp=0
    def outer(kind,**kw):
        nonlocal stamp
        stamp+=10;e=dict(event=kind,sequence=len(events),saved_ns=stamp,**kw);events.append(e);return e
    def actor(kind,at,**kw):
        nonlocal local
        e=outer('AGENT_EVENT',agent_event=kind,public_payload=dict(sequence=local,saved_ns=stamp+1,at_calls=at,**kw));local+=1;return e
    def physical(i,phase):
        row=history[i];actor('COMMAND',i,before=row['before'],command=row['command'],raw_policy=[0.]*4,phase=phase)
        outer('STEP_COMPLETE',logical_step=i,after=row['after'],executed_action_oracle=['NEVER_COPY'],noise_oracle=['NEVER_COPY'])
    def mem(i):return dict(schema='TASK_MEMORY_OPTION_V1',task=s['task'],completed_steps=i,current=deepcopy(history[i-1]['after']),
        controller=dict(source='UNCORRECTED',matrix_xy=[[1.,0.],[0.,1.]],offset=[0.]*4),integral_xy=[.25,-.125],time_constant_s=.5)
    actor('PROGRAM',0,task=s['task'],boundary=16,window_steps=16,acquisition_action='CONTINUE',bank_sha256='FUTURE_SCHEDULE')
    for i in range(min(16,n)):physical(i,'PREFIX_TASK')
    windows=[]
    if not early:
        actor('ACQUISITION_CHOICE',16,action='CONTINUE',before_memory=mem(16))
        if terminal_return:physical(16,'VALIDATION_TASK')
        at=17 if terminal_return else 16
        actor('TASK_MEMORY_RETURN',at,memory=mem(at))
        if not terminal_return:
            for index,start in enumerate((16,32)):
                q=dict(schema='OCCAM_PUBLIC_HISTORY_V1',task=s['task'],completed_steps=start,initial=initial,
                    history=deepcopy(history[:start]),integral_xy=mem(start)['integral_xy'],candidate_time_constant_s=.125,evaluation_steps=16)
                qe=actor('WINDOW_QUERY',start,value=q)['public_payload']
                de=actor('WINDOW_DECISION',start,input_sequence=qe['sequence'],declaration=dict(selected_rate=rates[index]))['public_payload']
                stop=min(start+16,n)
                for i in range(start,stop):physical(i,'TAIL_TASK')
                m=dict(start_at=start,end_at=stop,full_window=stop-start==16)
                actor('WINDOW_RESULT',stop,parent_sequence=de['sequence'],measurement=m)
                windows.append(dict(query=q,selected_rate=rates[index],measurement=m))
    actor('OUTCOME',n,final=history[-1]['after'],outcome=dict(total_steps=n,success=True,deadline_loss=n))
    p=dict(schema='OCCAM_PUBLIC_TRAIN_TRAJECTORY_V1',task=s['task'],initial=initial,history=history,windows=windows)
    return s,p,events


class ContractTests(TestCase):
    def test_fixed_factual_label(self):
        s,p,e=fixture();r=c.extract(s,p,e)
        self.assertEqual(r['labels']['before_remaining_loss'],17)
        self.assertTrue(r['labels']['static_TRAIN_supervised_label_admitted'])
        self.assertEqual([v['target_terminal_loss'] for v in r['labels']['static_targets']],[None,33,None,None])
    def test_independent_main_disabled(self):
        s,p,e=fixture();r=c.extract(s,p,e)
        def deny(*args,**kwargs):raise RuntimeError('disabled')
        funcs={n:deny for n,v in vars(c).items() if callable(v) and getattr(v,'__module__',None)==c.__name__}
        with mock.patch.multiple(c,**funcs):self.assertGreater(a.rebuild(s,p,e,r),33)
    def test_random_changed_not_first_T_label(self):
        s,p,e=fixture('RANDOM_WINDOW',(.5,2.));r=c.extract(s,p,e)
        self.assertEqual(r['labels']['static_targets'][1]['first_different_window'],1)
        self.assertTrue(all(v['target_terminal_loss'] is None for v in r['labels']['static_targets']))
    def test_constant_random_still_selected(self):
        s,p,e=fixture('RANDOM_WINDOW');r=c.extract(s,p,e)
        self.assertTrue(r['labels']['observed_constant_random_sequence'])
        self.assertFalse(r['labels']['static_TRAIN_supervised_label_admitted'])
    def test_fixed_change_rejected(self):
        with self.assertRaises(ValueError):c.extract(*fixture('BLOCK_FIXED',(.5,2.)))
    def test_early_no_fabricated_view(self):
        s,p,e=fixture(early=True);r=c.extract(s,p,e)
        self.assertIsNone(r['before']);self.assertIsNone(r['labels']['before_remaining_loss']);a.rebuild(s,p,e,r)
    def test_terminal_after_acquisition_no_gain(self):
        s,p,e=fixture(terminal_return=True);r=c.extract(s,p,e)
        self.assertFalse(r['after']['decision_required']);self.assertEqual(r['labels']['after_remaining_loss'],0);a.rebuild(s,p,e,r)
    def test_failed_terminal_penalty_not_steps(self):
        s,p,e=fixture(early=True)
        p['history'][-1]['after'].update(success=False,terminated=True)
        e[-1]['public_payload'].update(final=deepcopy(p['history'][-1]['after']),outcome=dict(total_steps=8,success=False,deadline_loss=500))
        for x in e:
            if x['event']=='STEP_COMPLETE' and x['logical_step']==7:x['after']=deepcopy(p['history'][-1]['after'])
        r=c.extract(s,p,e);self.assertEqual(r['deadline_loss'],500);self.assertEqual(r['total_steps'],8);a.rebuild(s,p,e,r)
    def test_native_never_trains(self):
        s,p,e=fixture();s['cohort']='NATIVE';r=c.extract(s,p,e)
        self.assertFalse(r['labels']['static_TRAIN_supervised_label_admitted']);a.rebuild(s,p,e,r)
    def test_private_event_bytes_not_view(self):
        s,p,e=fixture();r=c.extract(s,p,e)
        for x in e:
            x['secret_oracle']={'bias':[99,88]}
            if x['event']=='STEP_COMPLETE':x['noise_oracle']='DIFFERENT'
        self.assertEqual(r,c.extract(s,p,e))
    def test_future_schedule_not_view(self):
        s,p,e=fixture();r=c.extract(s,p,e)
        e[0]['public_payload']['bank_sha256']='OTHER_FUTURE';e[0]['public_payload']['acquisition_action']='OTHER_ASSIGNED_ARM'
        self.assertEqual(r,c.extract(s,p,e))
    def test_later_T_does_not_change_boundary_view(self):
        s,p,e=fixture('RANDOM_WINDOW',(.5,2.));r=c.extract(s,p,e)
        s2,p2,e2=fixture('RANDOM_WINDOW',(.5,8.));r2=c.extract(s2,p2,e2)
        self.assertEqual(r['before'],r2['before']);self.assertEqual(r['after'],r2['after'])
    def test_unknown_memory_rejected(self):
        s,p,e=fixture();next(x['public_payload']['before_memory'] for x in e if x.get('agent_event')=='ACQUISITION_CHOICE')['seed']=9
        with self.assertRaises(ValueError):c.extract(s,p,e)
    def test_stale_memory_rejected(self):
        s,p,e=fixture();next(x['public_payload']['memory'] for x in e if x.get('agent_event')=='TASK_MEMORY_RETURN')['current']=p['initial']
        with self.assertRaises(ValueError):c.extract(s,p,e)
    def test_future_query_rejected(self):
        s,p,e=fixture();p['windows'][0]['query']['history'].append(p['history'][16])
        with self.assertRaises(ValueError):c.extract(s,p,e)
    def test_controller_mapping_semantics_rejected(self):
        s,p,e=fixture();next(x['public_payload']['before_memory'] for x in e if x.get('agent_event')=='ACQUISITION_CHOICE')['controller']['matrix_xy'][0][0]=2.
        with self.assertRaises(ValueError):c.extract(s,p,e)
    def test_command_clip_and_float32_validation(self):
        for u in ([1.1,0.,0.,0.],[.1,0.,0.,0.]):
            with self.assertRaises(ValueError):c.command(u)
        c.command([1.,-1.,.125,0.])
    def test_no_undo_acquisition_receipt(self):
        s,p,e=fixture();r=c.extract(s,p,e)
        next(x for x in e if x['event']=='STEP_COMPLETE')['after']=p['initial']
        with self.assertRaises(ValueError):a.rebuild(s,p,e,r)
    def test_all_cells_and_alias_denominators(self):
        rs=[]
        for ctx in ('UNCHANGED','CHANGED'):
            for arm in ('CONTINUE','VALIDATE8','MOVE_MEASURE'):
                for behavior in ('RANDOM_WINDOW','BLOCK_FIXED'):
                    s,p,e=fixture(behavior);s.update(context=ctx,acquisition_action=arm)
                    for x in e:
                        if x.get('agent_event')=='ACQUISITION_CHOICE':x['public_payload']['action']=arm
                    rs.append(c.extract(s,p,e))
        result=c.summarize(rs);self.assertEqual(result['overall']['cases'],12);self.assertEqual(len(result['cells']),36)
        self.assertGreater(a.audit_summary(rs,result),100)
    def test_independent_rejects_invented_terminal(self):
        s,p,e=fixture();r=c.extract(s,p,e);r['labels']['static_targets'][0]['target_terminal_loss']=33
        with self.assertRaises(ValueError):a.rebuild(s,p,e,r)
    def test_guard_rejects_network_and_science(self):
        with TemporaryDirectory() as d:
            with run.record_only(Path(d),[]) as guard:
                with self.assertRaises(RuntimeError):sys.audit('socket.connect',None,None)
                with self.assertRaises(RuntimeError):sys.audit('import','numpy',None,None,None,None)
            self.assertEqual(guard['network_or_process_attempts'],1);self.assertEqual(guard['forbidden_imports'],1)
    def test_guard_rejects_QUAL_and_private_files(self):
        with TemporaryDirectory() as d:
            with run.record_only(Path(d),[]) as guard:
                with self.assertRaises(RuntimeError):open(run.ROOT/'QUAL_PRIVATE_FORBIDDEN','rb')
                with self.assertRaises(RuntimeError):open(run.BASE/'OUTSIDE_ANALYSIS_FORBIDDEN','wb')
            self.assertEqual(guard['undeclared_reads'],1);self.assertEqual(guard['outside_writes'],1)
