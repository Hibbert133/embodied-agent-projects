"""Pure arithmetic host contracts; no environment construction/reset/advance."""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from src.analysis import task_passive_io_v1 as allocation
from src.analysis import task_passive_host_v1 as host
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.short_probe_journal_audit_v1 import ledger_add,simulation,applied
from src.probe import task_passive_program_v1 as actor
from src.probe.continuous import StepObservation


class ArrayJournal:
    def __init__(self): self.rows=[]
    def emit(self,event,payload):
        v=normalize({'event':event,'sequence':len(self.rows),'saved_ns':perf_counter_ns(),**payload}); self.rows.append(v); return deepcopy(v)


class ArithmeticLedger:
    def __init__(self,value=None): self.value=value or {'counts':{},'by_phase':{}}
    @property
    def counts(self): return self.value['counts']
    def snapshot(self): return deepcopy(self.value)


class NumericPolicy:
    def get_action(self,observation): return np.array([.2,-.1,.05,-1.],np.float32)


class ArraySession:
    """Arrays and counters only. respond() uses a declared algebraic sequence."""
    def __init__(self,spec,journal,budget=None,success_at=120,ledger=None):
        self.emit=journal.emit; self._local=0; self._map={}; self._pending=None; self.branch={}
        self.ledger=ledger or ArithmeticLedger(); self.run_budget=budget or {'completed':0,'maximum':10000}
        self.env=SimpleNamespace(unwrapped=SimpleNamespace(model=SimpleNamespace(_address=1),data=SimpleNamespace(_address=2,time=0.)))
        obs=np.zeros(39); obs[:3]=[0.,.65,.25]; obs[4:7]=[.15,.65,.02]; obs[-3:]=[.3,.75,.1]
        self.ctx={'calls':0,'initial_observation':obs.copy(),'observation':obs.copy(),'noise_rows':allocation.noise(spec['seed'],spec['noise_namespace']),
            'commands':[],'observations':[],'success':False}
        self.fault=allocation.initial_fault(); self.success_at=success_at
        self.attempts=self.completed=self.policy_queries=self.captures=self.restores=0; self._snapshots={}; self.last_rows=[]
    def public(self): return StepObservation(self.ctx['observation'],False,False,self.ctx['success'])
    def alive(self): return not self.ctx['success']
    def policy_query(self,observation): self.policy_queries+=1; return NumericPolicy().get_action(observation)
    def witness(self):
        h=allocation.io.digest([self.ctx['observation'].tolist(),self.ctx['calls']])
        return {'native_sha256':h,'python_semantic_sha256':h,'noise_past_sha256':allocation.io.digest(self.ctx['noise_rows'][:self.ctx['calls']].tolist()),'simulation_time':self.env.unwrapped.data.time}
    def _agent_emit(self,event,payload):
        local=normalize({'sequence':self._local,'saved_ns':perf_counter_ns(),**payload}); self._local+=1
        outer=self.emit('AGENT_EVENT',{'agent_event':event,'public_payload':local}); self._map[local['sequence']]=outer['sequence']
        if event=='COMMAND': self._pending=deepcopy(local)
        return local
    def _agent_step(self,saved):
        if saved!=self._pending or saved['at_calls']!=self.ctx['calls'] or saved['decision_sequence'] not in self._map: raise ValueError('stale array action')
        n=self.ctx['calls']; clock=self.env.unwrapped.data.time; before=self.ledger.snapshot()
        intent=self.emit('STEP_INTENT',{'logical_step':n,'global_command_sequence':self._map[saved['sequence']],
            'command':saved['command'],'phase':saved['phase'],'ledger_before':before})
        started=perf_counter_ns(); self.attempts+=1
        action=np.array(applied(saved['command'],self.fault,self.ctx['noise_rows'][n]),np.float32)
        self.ctx['observation']=self.ctx['observation'].copy(); self.ctx['observation'][:3]+=.002*action[:3]
        self.ctx['observation'][3]=action[3]; self.ctx['calls']+=1; self.completed+=1; self.run_budget['completed']+=1
        self.ctx['success']=self.success_at is not None and self.ctx['calls']>=self.success_at
        self.ledger.value=simulation(self.ledger.value,'CONTROL',1,5); self.env.unwrapped.data.time+=.0125
        if self.ctx['calls']<=8: self.ctx['commands'].append(np.array(saved['command'],np.float32)); self.ctx['observations'].append(self.ctx['observation'].copy())
        row=normalize({'logical_step':n,'phase':saved['phase'],'command':saved['command'],'executed_action_oracle':action,'raw_policy':saved['raw_policy'],
            'after':asdict(self.public()),'simulation_time_before':clock,'simulation_time_after':self.env.unwrapped.data.time,'noise_cursor_after':n+1,
            'reward':0.,'info':{'success':self.ctx['success']},'intent_sequence':intent['sequence'],'global_command_sequence':self._map[saved['sequence']],
            'execution_started_ns':started,'completed_ns':perf_counter_ns(),'ledger_before':before,'ledger_after':self.ledger.snapshot()})
        self.last_rows.append(row); self.emit('STEP_COMPLETE',row)
        if self.ctx['calls'] in (4,8): self.emit('PHYSICAL_BOUNDARY',{'logical_step':self.ctx['calls'],**self.witness()})
        self._pending=None; return self.public()


def spec(style='DIRECT_TASK_PI',ti=.5,context='CHANGED'):
    return next(s for s in allocation.population('DEV') if s['group']==0 and s['task']=='push-v3' and s['context']==context and s['style']==style and s['time_constant_s']==ti)


def fit_patches():
    fit={'valid':True,'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'nfev':0,'reason':'ARRAY_ONLY'}
    from contextlib import ExitStack
    stack=ExitStack(); stack.enter_context(patch.object(actor,'validate_model')); stack.enter_context(patch.object(actor,'infer_four',return_value=fit)); stack.enter_context(patch.object(actor,'infer_operator',return_value=fit)); return stack


def run_numeric(s,success_at=120,budget=None,mutate=None):
    j=ArrayJournal(); session=ArraySession(s,j,budget,success_at); labels=[]; syncs=[]
    def witness(label):
        w=session.witness(); labels.append((label,session.ctx['calls'])); return (w['native_sha256'],w['python_semantic_sha256'],w['noise_past_sha256'],w['simulation_time'])
    def sync():
        syncs.append(len(j.rows))
        if mutate: mutate(session)
    with fit_patches(): result=host.run_live(s,{'task':s['task']},session,witness,sync)
    return result,session,j,labels,syncs


class TaskHostTests(unittest.TestCase):
    def test_boundary_only_changes_private_coefficients_and_keeps_noise_past(self):
        r,s,j,labels,syncs=run_numeric(spec())
        changes=[e for e in j.rows if e['event']=='FAULT_BOUNDARY']; self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]['before'],changes[0]['after']); self.assertEqual(changes[0]['logical_step'],16)
        self.assertEqual(s.fault,allocation.destination(spec())); self.assertTrue(r['boundary_applied'])
        self.assertEqual(len(syncs),s.completed); self.assertEqual(s.policy_queries,r['policy_queries'])

    def test_early_success_cannot_force_a_change_or_late_movement(self):
        r,s,j,labels,_=run_numeric(spec('MOVE_KEEP_TASK_PI'),success_at=10)
        self.assertFalse(r['boundary_applied']); self.assertEqual(r['boundary_missing_reason'],'EARLY_SUCCESS')
        self.assertFalse(any(e['event']=='FAULT_BOUNDARY' for e in j.rows)); self.assertEqual(r['movement_steps'],0)

    def test_unchanged_context_still_has_auditable_continuous_boundary(self):
        r,s,j,_,_=run_numeric(spec(context='UNCHANGED'))
        e=next(e for e in j.rows if e['event']=='FAULT_BOUNDARY'); self.assertFalse(e['changed_oracle'])
        self.assertEqual(e['old_fault_oracle'],e['new_fault_oracle'])

    def test_raw_program_receives_no_nominal_source_or_fit(self):
        r,s,j,_,_=run_numeric(spec('RAW_TASK_PI'))
        self.assertEqual(r['c4_c8_fit_attempts'],0); self.assertEqual(r['pi_steps'],120)
        self.assertIsNone(next(e for e in j.rows if e['event']=='AGENT_EVENT')['public_payload']['nominal_sha256'])

    def test_global_budget_exhaustion_executes_no_extra_command(self):
        j=ArrayJournal(); s=ArraySession(spec(),j,{'completed':0,'maximum':2})
        with fit_patches(),self.assertRaisesRegex(ValueError,'unbudgeted'):
            host.run_live(spec(),{'task':'push-v3'},s,lambda _:None,lambda:None)
        self.assertEqual(s.completed,2)

    def test_runtime_noise_replacement_is_rejected(self):
        def replace(s): s.ctx['noise_rows']=s.ctx['noise_rows'].copy()
        with self.assertRaisesRegex(ValueError,'tape replaced'): run_numeric(spec(),mutate=replace)

    def test_runtime_clock_rewind_is_rejected(self):
        def rewind(s): s.env.unwrapped.data.time-=1.
        with self.assertRaisesRegex(ValueError,'clock'): run_numeric(spec(),mutate=rewind)

    def test_all_move_programs_keep_identical_prefix_through_actual_post_move(self):
        results=[run_numeric(spec(style,None if style in actor.CONTROLS else .5)) for style in ('MOVE_KEEP_C8','MOVE_INTEGRAL','MOVE_KEEP_TASK_PI','MOVE_INTEGRAL_TASK_PI')]
        ends=[next(e['public_payload']['at_calls'] for e in j.rows if e['event']=='AGENT_EVENT' and e['agent_event']=='POST_MOVE_TASK_ENTRY') for _,_,j,_,_ in results]
        self.assertEqual(len(set(ends)),1)
        from src.analysis.short_probe_journal_audit_v1 import physical_rows_equal
        self.assertTrue(all(physical_rows_equal(results[0][1].last_rows,v[1].last_rows,ends[0]) for v in results[1:]))


if __name__=='__main__': unittest.main()
