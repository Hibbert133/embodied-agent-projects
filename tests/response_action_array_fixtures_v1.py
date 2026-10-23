"""Pure array/counter fixtures, including arithmetic reset rows; no native Env/reset/step."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
from types import SimpleNamespace
import numpy as np
from src.analysis import response_action_io_v1 as allocation
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.short_probe_journal_audit_v1 import ledger_add,simulation,applied
from src.probe.continuous import StepObservation
from tests.test_task_passive_host_v1 import ArrayJournal,ArithmeticLedger,NumericPolicy,fit_patches
from tests.test_response_action_rank_v1 import fixture

class ArraySession:
    """Arrays and counters only. respond() uses a declared algebraic sequence."""
    def __init__(self,spec,journal,budget=None,success_at=120,ledger=None):
        self.emit=journal.emit; self._local=0; self._map={}; self._pending=None; self.branch={}
        self.ledger=ledger or ArithmeticLedger(); self.run_budget=budget or {'completed':0,'maximum':10000}
        self.env=SimpleNamespace(unwrapped=SimpleNamespace(action_scale=.01,model=SimpleNamespace(_address=1),data=SimpleNamespace(_address=2,time=0.)))
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


def synthetic_record(s=None,success_at=25):
    s=s or next(x for x in allocation.population('DEV') if x['task']=='push-v3' and x['group']==0 and x['context']=='CHANGED' and x['style']=='F20_RANK' and x['regularization_weight']==.1); journal=ArrayJournal(); private=ArrayJournal(); ledger=ArithmeticLedger()
    journal.emit('FACTORY_INTENT',{'ledger':ledger.snapshot()})
    for phase,count in (('GOAL_GENERATION',50),('CONTROLLED_RESET',1)):
        if phase=='CONTROLLED_RESET': journal.emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
        for _ in range(count):
            before=ledger.snapshot(); ledger.value=ledger_add(ledger.value,phase,'reset_attempts',1)
            intent=journal.emit('LIFECYCLE_RESET_INTENT',{'phase':phase,'before':before})
            ledger.value=simulation(ledger.value,phase,100,500); ledger.value=ledger_add(ledger.value,phase,'reset_completed',1)
            journal.emit('LIFECYCLE_RESET_COMPLETE',{'phase':phase,'intent_sequence':intent['sequence'],'after':ledger.snapshot()})
    session=ArraySession(s,journal,success_at=success_at,ledger=ledger); initial=asdict(session.public())
    journal.emit('CONTROLLED_INITIAL',{'task':s['task'],'observation':initial['observation'],'simulation_time':0.,'ledger':ledger.snapshot()})
    journal.emit('NOISE_COMMITMENT',{'at_calls':0,'noise_namespace_oracle':s['noise_namespace'],'tape_sha256_oracle':allocation.io.digest(session.ctx['noise_rows'].tolist())})
    refs=[]
    def witness(label):
        expected=session.witness(); anchor=journal.rows[-1]; start=perf_counter_ns(); w={'native_sha256':expected['native_sha256'],'comparison_python_sha256':expected['python_semantic_sha256']}
        saved=private.emit('STATE_WITNESS',{'label':label,'logical_step':session.ctx['calls'],'source_anchor_sequence':anchor['sequence'],
            'source_anchor_saved_ns':anchor['saved_ns'],'started_ns':start,'completed_ns':perf_counter_ns(),
            'ledger_before':ledger.snapshot(),'ledger_after':ledger.snapshot(),'source_witness':expected,'witness':w})
        refs.append({'label':label,'sequence':saved['sequence'],'logical_step':session.ctx['calls'],**w})
        return (w['native_sha256'],w['comparison_python_sha256'],expected['noise_past_sha256'],expected['simulation_time'])
    witness('INITIAL')
    from src.analysis.response_action_host_v1 import run_live
    model=fixture()[1] if s['style']=='F20_RANK' else None
    with fit_patches(): outcome=run_live(s,{'task':s['task']},model,session,witness,lambda:None)
    case={**s,**outcome,'completed':True,'error':None,'close_error':None,'environment_closed':True,'ledger_before':{'counts':{},'by_phase':{}},
        'initial_fault_oracle':allocation.initial_fault(),'destination_oracle':allocation.destination(s),
        'initial':initial,'final':asdict(session.public()),'captures':0,'restores':0,'physical_rows_count':session.completed,
        'host_attempts':session.completed,'host_returned':session.completed,'ledger_before_close':ledger.snapshot(),'ledger_after_close':ledger.snapshot(),
        'state_witness_refs':refs,'computation_counters_complete':True,
        'inference_accounting':{'intents':outcome['rank_steps'],'validated':outcome['rank_steps'],'response_planned':outcome['response_model_forward_evaluations'],'kinematic_planned':outcome['kinematic_proxy_evaluations']}}
    return s,case,journal.rows,private.rows
