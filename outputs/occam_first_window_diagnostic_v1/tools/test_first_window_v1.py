"""Constructed records and arrays only. Never creates an environment or model."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import importlib
import json
import socket
import unittest

import first_window_engine_v1 as e
import first_window_audit_v1 as a
import run_first_window_v1 as r


def fixture(*, short=False, absent=False):
    spec=dict(cohort='QUAL',group=0,task='push-v3',seed=175100,context='UNCHANGED',planned_boundary=16,program='META_ADAPT__CONTINUE')
    initial=dict(observation=[0.]*39,success=False,terminated=False,truncated=False)
    events=[]; history=[]; clock=0.; stamp=0; before=initial
    def outer(kind, **value):
        nonlocal stamp
        stamp+=10; row={**spec,'event':kind,'saved_ns':stamp,**value}; events.append(row); return row
    def public(kind,seq,at,**value):
        payload=dict(sequence=seq,saved_ns=stamp+1,at_calls=at,**value)
        outer('AGENT_EVENT',agent_event=kind,public_payload=payload); return payload
    def step(index, *, terminal=False):
        nonlocal before,clock
        after={**deepcopy(initial),'observation':[float(index+1)]*39,'success':terminal}
        row=outer('STEP_COMPLETE',logical_step=index,noise_cursor_after=index+1,simulation_time_before=clock,
                  simulation_time_after=clock+.0125,command=[0.,0.,0.,0.],raw_policy=[0.,0.,0.,0.],after=after,
                  executed_action_oracle=[0.,0.,0.,0.],reward=0.)
        history.append(dict(at_calls=index,before=before,command=row['command'],after=after)); before=after; clock+=.0125
    outer('CONTROLLED_INITIAL',simulation_time=clock,observation=initial['observation'])
    public('PROGRAM',0,0,bank_sha256='bank')
    prefix=2 if absent else 16
    for index in range(prefix): step(index,terminal=absent and index==prefix-1)
    memory=dict(schema='TASK_MEMORY_OPTION_V1',task='push-v3',completed_steps=prefix,current=before,
                controller=dict(source='identity',matrix_xy=[[1.,0.],[0.,1.]],offset=[0.,0.,0.,0.]),integral_xy=[0.,0.],time_constant_s=.5)
    if not absent:
        public('TASK_MEMORY_RETURN',1,prefix,memory=deepcopy(memory))
        query=dict(schema='OCCAM_PUBLIC_HISTORY_V1',task='push-v3',completed_steps=prefix,initial=initial,
                   history=deepcopy(history),integral_xy=[0.,0.],candidate_time_constant_s=.125,evaluation_steps=16)
        public('WINDOW_QUERY',2,prefix,value=query)
        declaration=dict(schema='OCCAM_PERFORMANCE_DECLARATION_V1',version=0,at_calls=prefix,evaluation_steps=16,
                         public_query_sha256=e.digest(query),rates=list(e.RATES),selected_index=0,selected_rate=.125,
                         predictions=[dict(mean=[float(i)]) for i in range(4)],beta=0.,reward_weights=[-1.])
        declaration['declaration_sha256']=e.digest(declaration)
        public('WINDOW_DECISION',3,prefix,input_sequence=2,declaration=declaration)
        public('RATE_PLAN',4,prefix,before_memory=memory,decision_sequence=3,rate=.125)
        outer('STEP_INTENT',logical_step=prefix)
        for index in range(1 if short else 16): step(prefix+index,terminal=short)
        actual=len(history)-prefix
        measured=dict(schema='OCCAM_WINDOW_COST_V1',start_at=prefix,end_at=len(history),planned_steps=16,actual_steps=actual,
                      full_window=not short,terminal=short,success=short,host_failure=False,cost=.1,
                      rows_sha256=e.digest(history[prefix:]))
        public('WINDOW_RESULT',5,len(history),measurement=measured,parent_sequence=3)
    def witness(label,n):
        return {**spec,'label':label,'logical_step':n,
                'witness':dict(native_sha256=str(n),comparison_python_sha256='python'+str(n)),
                'source_witness':dict(simulation_time=0. if n==0 else events[2+n-1]['simulation_time_after'],noise_past_sha256='noise'+str(n))}
    private=[witness('INITIAL',0)]
    if not absent: private += [witness(label,prefix) for label in ('POST_ACQUISITION','FIRST_RATE_PRE','FIRST_RATE_POST')]
    case={**spec,'completed':True,'environment_closed':True,'error':None,'close_error':None,'initial':initial,
          'total_steps':len(history),'success':short or absent,'deadline_loss':len(history) if short or absent else 500,
          'boundary_applied':not absent}
    return case,spec,events,private


def context():
    source=e.extract(*fixture()); result=[]
    for index,name in enumerate(e.FIXED+e.TARGETS):
        c=deepcopy(source); c['spec']['program']=name+'__CONTINUE'
        if index<4:
            c['declaration']['selected_index']=index; c['declaration']['selected_rate']=e.RATES[index]
            c['measurement']['cost']=float(index+1)
        else: c['measurement']['cost']=1.
        result.append(c)
    return result


class RankTests(unittest.TestCase):
    def test_exact_order(self): self.assertEqual(e.rank_errors([1,2,3,4],[1,2,3,4])['mean_error'],0.)
    def test_reversed_order(self): self.assertEqual(e.rank_errors([1,2,3,4],[4,3,2,1])['mean_error'],1.)
    def test_predicted_ties_half(self): self.assertEqual(e.rank_errors([1,1,1,1],[1,2,3,4])['mean_error'],.5)
    def test_actual_ties_missing(self): self.assertIsNone(e.rank_errors([1,2,3,4],[1,1,1,1])['mean_error'])
    def test_partial_tie_denominator(self): self.assertEqual(e.rank_errors([1,1,2,3],[1,1,2,3])['comparable_pairs'],5)
    def test_no_tolerance_selected_after_results(self): self.assertEqual(e.rank_errors([1.,1.0000000000000002,2,3],[1.,1.0000000000000002,2,3])['actual_ties'],0)
    def test_bad_missing_candidate(self):
        with self.assertRaises(ValueError): e.rank_errors([1,2,3],[1,2,3])
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError): e.rank_errors([1,2,3,float('nan')],[1,2,3,4])
    def test_scalar_metrics_and_independent_rank(self):
        metric=e.vector_metrics([1,2,3,4],[4,3,2,1],0,0.)
        self.assertEqual(metric['MSE'],5.); self.assertEqual(metric['first_window_choice_gap'],3.)
        self.assertEqual(metric['rank'],a.ranks([1,2,3,4],[4,3,2,1]))
    def test_empty_group_metric_is_missing(self):
        rows=e.context_diagnostics(context(),0.); rows['learned'][0]['metric']=None
        s=e.summary([rows],'META_ADAPT'); self.assertIsNone(s['equal_available_group_means']['MSE']['mean'])


class RecordTests(unittest.TestCase):
    def mutate(self,name,value):
        c,s,ev,p=fixture()
        row=next(x for x in ev if x['event']=='AGENT_EVENT' and x['agent_event']==name)
        value(row['public_payload']); return c,s,ev,p
    def test_full_literal_reader_agreement(self): self.assertEqual(e.extract(*fixture()),a.literal_extract(*fixture()))
    def test_terminal_short_retained(self):
        data=fixture(short=True); x=e.extract(*data); self.assertEqual(x,a.literal_extract(*data)); self.assertEqual(x['measurement']['actual_steps'],1)
    def test_before_boundary_early_end_retained(self):
        data=fixture(absent=True); x=e.extract(*data); self.assertEqual(x,a.literal_extract(*data)); self.assertEqual(x['missing_reason'],'BEFORE_INTERVENTION')
    def test_after_acquisition_early_end_retained(self):
        data=list(fixture(absent=True)); data[0]['boundary_applied']=True
        self.assertEqual(e.extract(*data)['missing_reason'],'AFTER_ACQUISITION_NO_WINDOW')
    def test_future_history_rejected(self):
        data=self.mutate('WINDOW_QUERY',lambda p:p['value']['history'].append({'future':True}))
        with self.assertRaises(ValueError): e.extract(*data)
        with self.assertRaises(ValueError): a.literal_extract(*data)
    def test_noise_cursor_shift_rejected(self):
        c,s,ev,p=fixture(); next(x for x in ev if x['event']=='STEP_COMPLETE')['noise_cursor_after']+=1
        with self.assertRaises(ValueError): e.extract(c,s,ev,p)
        with self.assertRaises(ValueError): a.literal_extract(c,s,ev,p)
    def test_clock_shift_rejected(self):
        c,s,ev,p=fixture(); next(x for x in ev if x['event']=='STEP_COMPLETE')['simulation_time_before']+=1
        with self.assertRaises(ValueError): e.extract(c,s,ev,p)
    def test_stale_parameter_version_rejected(self):
        data=self.mutate('WINDOW_DECISION',lambda p:p['declaration'].update(version=1))
        with self.assertRaises(ValueError): e.extract(*data)
    def test_unsaved_declaration_change_rejected(self):
        data=self.mutate('WINDOW_DECISION',lambda p:p['declaration']['predictions'][0]['mean'].__setitem__(0,55.))
        with self.assertRaises(ValueError): e.extract(*data)
    def test_command_trace_hash_rejected(self):
        data=self.mutate('WINDOW_RESULT',lambda p:p['measurement'].update(rows_sha256='bad'))
        with self.assertRaises(ValueError): e.extract(*data)
    def test_illegal_nonterminal_short_rejected(self):
        data=list(fixture(short=True)); data[2][-1]['public_payload']['measurement']['terminal']=False
        with self.assertRaises(ValueError): e.extract(*data)
    def test_incomplete_first_window_rejected(self):
        c,s,ev,p=fixture()
        with self.assertRaises(ValueError): e.extract(c,s,ev[:-1],p)
    def test_failed_task_loss_kept(self): self.assertEqual(e.extract(*fixture())['deadline_loss'],500)


class ContextTests(unittest.TestCase):
    def test_all_eight_aligned_and_independent_metrics(self):
        caps=context(); row=e.context_diagnostics(caps,0.); self.assertEqual(row['alignment_reasons'],[]); a.verify_context(caps,row,0.)
    def test_memory_mismatch_missing_not_zero(self):
        caps=context(); caps[-1]['before_memory_sha256']='wrong'; row=e.context_diagnostics(caps,0.)
        self.assertIn('MISMATCH_BEFORE_MEMORY_SHA256',row['alignment_reasons']); self.assertIsNone(row['learned'][0]['metric']); a.verify_context(caps,row,0.)
    def test_native_state_mismatch(self):
        caps=context(); caps[-1]['first_rate_witness']['native_sha256']='wrong'
        self.assertIn('MISMATCH_FIRST_RATE_WITNESS',e.context_diagnostics(caps,0.)['alignment_reasons'])
    def test_selected_window_mismatch(self):
        caps=context(); caps[-1]['measurement']['rows_sha256']='wrong'
        self.assertIn('SELECTED_FIRST_WINDOW_MISMATCH_ERM_FROZEN',e.context_diagnostics(caps,0.)['alignment_reasons'])
    def test_bank_adapt_frozen_first_declaration_check(self):
        caps=context(); caps[-1]['declaration']['predictions'][1]['mean'][0]=99.
        self.assertIn('FIRST_BANK_DECLARATION_MISMATCH_ERM',e.context_diagnostics(caps,0.)['alignment_reasons'])
    def test_all_no_window_preserved(self):
        caps=context()
        for c in caps: c['declaration']=c['measurement']=None
        row=e.context_diagnostics(caps,0.); self.assertIn('ALL_NO_FIRST_WINDOW',row['alignment_reasons']); self.assertIsNone(row['actual_first_costs'])
    def test_group_weighting_not_candidate_pairs(self):
        rows=[]
        for group,value,count in ((0,0.,2),(1,10.,1)):
            for _ in range(count):
                row=e.context_diagnostics(context(),0.); row['context']['group']=group
                row['learned'][0]['metric']['MSE']=value; rows.append(row)
        s=e.summary(rows,'META_ADAPT'); self.assertEqual(s['equal_available_group_means']['MSE']['mean'],5.); a.verify_summary(rows,'META_ADAPT',s)
    def test_independent_detects_metric_tampering(self):
        caps=context(); row=e.context_diagnostics(caps,0.); row['learned'][0]['metric']['MSE']+=1
        with self.assertRaises(ValueError): a.verify_context(caps,row,0.)
    def test_missing_context_census_rejected(self):
        with self.assertRaises(ValueError): e.all_statistics([])
    def test_complete_162_contexts_and_216_cells(self):
        contexts=[]; template=e.context_diagnostics(context(),0.)
        for group in range(9):
            for task in e.TASKS:
                for condition in e.CONDITIONS:
                    for arm in e.ARMS:
                        row=deepcopy(template); row['context'].update(group=group,task=task,context=condition,planned_boundary=(16,32,64)[group%3])
                        row['acquisition_action']=arm; contexts.append(row)
        stats=e.all_statistics(contexts); self.assertEqual(len(stats['cells']),216)
        for cell in stats['cells']:
            part=[c for c in contexts if c['context']['task']==cell['task'] and c['context']['context']==cell['context']
                  and c['context']['planned_boundary']==cell['boundary'] and c['acquisition_action']==cell['arm']]
            a.verify_summary(part,cell['target'],cell)
        contexts[-1]=contexts[0]
        with self.assertRaises(ValueError): e.all_statistics(contexts)
    def test_independent_reader_and_math_with_primary_disabled(self):
        data=fixture(); expected=e.extract(*data); caps=context(); row=e.context_diagnostics(caps,0.)
        with patch.multiple(e,extract=None,context_diagnostics=None,vector_metrics=None,rank_errors=None,summary=None,all_statistics=None):
            self.assertEqual(a.literal_extract(*data),expected); a.verify_context(caps,row,0.)
    def test_mixed_missing_first_window_never_imputed(self):
        caps=context(); caps[-1]['declaration']=caps[-1]['measurement']=None
        row=e.context_diagnostics(caps,0.); self.assertIn('MIXED_WINDOW_AVAILABILITY',row['alignment_reasons'])
        self.assertIsNone(row['actual_first_costs']); a.verify_context(caps,row,0.)


class AdmissionTests(unittest.TestCase):
    def metadata(self, root):
        m=dict(source_git_commit=r.SCIENCE,config={}); mid=e.digest(m); m['manifest_id']=mid
        for n in r.GATES: p=root/n; p.parent.mkdir(parents=True,exist_ok=True); p.touch()
        data={
            'manifest.json':m,
            'pipeline_v1/complete.json':dict(integrity='PASSED_COMPLETE_SEQUENCE',failure=None,report_returncode=0,manifest_id=mid),
            'qual/summary.json':dict(status='COLLECTED_FOR_INDEPENDENT_AUDIT',executions=1566,allocated_executions=1566,failure=None),
            'qual/completion.json':dict(status='COLLECTED_FOR_INDEPENDENT_AUDIT',artifact_sha256={'cases.jsonl.gz':'h'}),
            'qual/process_audit.json':dict(integrity='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY',executions=1566),
            'qual/audit.json':dict(integrity='PASSED',counts={'executions':1566},manifest_id=mid,prequential_windows_sha256='h'),
            'statistics_v1/statistics.json':dict(integrity='PASSED',manifest_id=mid,source_audit_sha256='h',bootstrap_indices_sha256='h',task_qualified=False,prediction={'qualified':False}),
            'statistics_v1/independent_audit.json':dict(integrity='PASSED',manifest_id=mid,all_executions=1566,production_statistics_disabled=True,source_statistics_sha256='h')}
        return data,mid
    def check(self, change=None, missing=None):
        with TemporaryDirectory() as name:
            root=Path(name); data,mid=self.metadata(root)
            if change: change(data)
            if missing: (root/missing).unlink()
            with patch.object(r,'MID',mid): return r.admit(root,reader=lambda p:data[p.relative_to(root).as_posix()],checksum=lambda p:'h')
    def test_live_population_rejected_before_read(self):
        with TemporaryDirectory() as name:
            with self.assertRaises(ValueError): r.admit(Path(name),reader=lambda p:self.fail('read outcome before terminal markers'))
    def test_missing_independent_statistics_rejected(self):
        with self.assertRaises(ValueError): self.check(missing='statistics_v1/independent_audit.json')
    def test_negative_scientific_gate_is_allowed(self): self.assertFalse(self.check()[2]['task_qualified'])
    def test_partial_population_rejected(self):
        with self.assertRaises(ValueError): self.check(lambda d:d['qual/summary.json'].update(executions=1565))
    def test_failed_record_audit_rejected(self):
        with self.assertRaises(ValueError): self.check(lambda d:d['qual/audit.json'].update(integrity='FAILED'))
    def test_stats_source_hash_change_rejected(self):
        with self.assertRaises(ValueError): self.check(lambda d:d['statistics_v1/statistics.json'].update(source_audit_sha256='bad'))
    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in ('{"x":1,"x":2}','{"x":NaN}'):
            with self.assertRaises(ValueError): r.loads(raw)
    def test_network_and_execution_imports_denied(self):
        with r.record_only():
            with self.assertRaises(RuntimeError): socket.socket()
            with self.assertRaises(RuntimeError): importlib.import_module('metaworld')


if __name__=='__main__': unittest.main()
