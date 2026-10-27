"""Evaluator host for same-state continuations. Private world never enters actor."""
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.state_capsule_v1 import capture,restore,native_hash,state_signature,python_state,layers
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.continuous import StepObservation
from src.probe.probe_effect_program_v1 import execute_warm,execute_cold
from src.rollout.chronological_faults import deterministic_action


def original_noise(seed):
    key=int(np.random.SeedSequence([seed,47001]).generate_state(1)[0])
    return np.random.default_rng(key).normal(0,.05,(500,3)).astype('<f4')


def fresh_tail(seed,future):
    if type(future) is not int or future<1:raise ValueError('fresh evaluation future required')
    rng=np.random.default_rng(np.random.SeedSequence([seed,65001,future]))
    return rng.normal(0,.05,(496,3)).astype('<f4')


def physical_comparison(row):
    out=normalize({k:v for k,v in row.items() if k not in ('intent_sequence','global_command_sequence','execution_started_ns','completed_ns','ledger_before','ledger_after')})
    if 'episode' in out.get('info',{}):out['info']['episode'].pop('t',None)
    return out


class ProbeSession:
    def __init__(self,env,policy,initial,task,seed,fault,emit,ledger,run_budget):
        self.env,self.policy,self.task,self.seed,self.fault=env,policy,task,seed,fault
        self.emit,self.ledger,self.run_budget=emit,ledger,run_budget
        tape=original_noise(seed);tape.flags.writeable=False
        self.ctx={'initial_observation':np.asarray(initial).copy(),'observation':np.asarray(initial).copy(),
            'terminated':False,'truncated':False,'success':False,'calls':0,'commands':[],'observations':[],'noise_rows':tape}
        self.attempts=0;self.completed=0;self.policy_queries=0;self.restores=0;self.captures=0
        self.capture_ns=0;self.restore_ns=0;self.last_rows=[];self.branch={};self.boundaries={}
        self._pending=None;self._local=0;self._map={};self.choice_refs=[]
        self._snapshots={}
        self.emit('CONTROLLED_INITIAL',{'task':task,'observation':initial,'simulation_time':float(env.unwrapped.data.time),'ledger':ledger.snapshot()})

    def public(self):
        c=self.ctx
        return StepObservation(tuple(c['observation']),bool(c['terminated']),bool(c['truncated']),bool(c['success']))

    def policy_query(self,observation):
        self.policy_queries+=1
        return np.asarray(self.policy.get_action(np.asarray(observation).copy()),np.float32)

    def alive(self):
        current=self.public();return not(current.success or current.terminated or current.truncated)

    def _step(self,command,phase,raw,global_command):
        if not self.alive() or self.ctx['calls']>=500:raise ValueError('ended/exhausted host stepped')
        if self.run_budget['completed']>=self.run_budget['maximum']:raise ValueError('whole-study step cap')
        sent=np.asarray(command,np.float32)
        if sent.shape!=(4,) or not np.isfinite(sent).all() or np.any(abs(sent)>1):raise ValueError('bounded finite host command required')
        cursor=self.ctx['calls'];before=self.ledger.snapshot();base=self.env.unwrapped
        intent=self.emit('STEP_INTENT',{**self.branch,'logical_step':cursor,'global_command_sequence':global_command,
            'phase':phase,'command':sent.tolist(),'ledger_before':before})
        action=deterministic_action(intent['command'],self.fault);action[:3]+=self.ctx['noise_rows'][cursor];action=np.clip(action,-1,1)
        started=perf_counter_ns();time_before=float(base.data.time);self.attempts+=1
        with self.ledger.scope('CONTROL'):obs,reward,term,trunc,info=self.env.step(action)
        self.completed+=1;self.run_budget['completed']+=1;self.ctx['calls']+=1
        self.ctx.update(observation=np.asarray(obs).copy(),terminated=bool(term),truncated=bool(trunc),success=bool(info.get('success',False)))
        if self.ctx['calls']<=8:
            self.ctx['commands'].append(sent.copy());self.ctx['observations'].append(np.asarray(obs).copy())
        after=self.ledger.snapshot();time_after=float(base.data.time)
        if (not np.isclose(time_after-time_before,.0125,atol=1e-10,rtol=0) or
            after['counts'].get('reset_attempts',0)!=before['counts'].get('reset_attempts',0) or
            after['counts'].get('simulation_frames_completed',0)-before['counts'].get('simulation_frames_completed',0)!=5):
            raise ValueError('five-frame continuous physical step violated')
        row=normalize({'logical_step':cursor,'phase':phase,'command':sent,'raw_policy':raw,'executed_action_oracle':action,
            'after':asdict(self.public()),'reward':reward,'info':info,'simulation_time_before':time_before,'simulation_time_after':time_after,
            'noise_cursor_after':self.ctx['calls'],'intent_sequence':intent['sequence'],'global_command_sequence':global_command,
            'execution_started_ns':started,'completed_ns':perf_counter_ns(),'ledger_before':before,'ledger_after':after})
        self.emit('STEP_COMPLETE',{**self.branch,**row});self.last_rows.append(row)
        if self.ctx['calls'] in (4,8):
            witness=self.witness();self.boundaries[self.ctx['calls']]=witness
            self.emit('PHYSICAL_BOUNDARY',{**self.branch,'logical_step':self.ctx['calls'],**witness})
        return self.public()

    def prefix4(self,block4):
        self.branch={'role':'WARM_PREFIX','future':0,'program':'BLOCK4'};self.last_rows=[];self.boundaries={}
        declaration=self.emit('PREFIX_CHOICE',{**self.branch,'program_commands':[list(v) for v in block4]})
        for index,command in enumerate(declaration['program_commands']):
            if not self.alive():break
            saved=self.emit('PREFIX_COMMAND',{**self.branch,'program_sequence':declaration['sequence'],'program_index':index,
                'logical_step':self.ctx['calls'],'command':command,'before':asdict(self.public())})
            self._step(saved['command'],'FIXED_PROBE',None,saved['sequence'])

    def witness(self):
        base=self.env.unwrapped
        return {'native_sha256':native_hash(base.model,base.data),
            'python_semantic_sha256':state_signature(python_state(layers(self.env),self.policy,self.ctx),base.model,base.data),
            'noise_past_sha256':digest(self.ctx['noise_rows'][:self.ctx['calls']].tolist()),
            'simulation_time':float(base.data.time)}

    def snapshot(self,purpose):
        before=self.ledger.snapshot();event=self.emit('SNAPSHOT_INTENT',{'purpose':purpose,'logical_step':self.ctx['calls'],'ledger':before})
        started=perf_counter_ns();value=capture(self.env,self.policy,self.ctx);elapsed=perf_counter_ns()-started
        self.captures+=1;self.capture_ns+=elapsed
        if self.ledger.snapshot()!=before:raise ValueError('snapshot performed environment interaction')
        expected=self.witness()
        if expected['native_sha256']!=value.native_sha256:raise ValueError('snapshot native copy differs')
        self._snapshots[id(value)]=(value,expected)
        self.emit('SNAPSHOT_COMPLETE',{'purpose':purpose,'intent_sequence':event['sequence'],'logical_step':self.ctx['calls'],
            'native_sha256':value.native_sha256,'python_payload_sha256':value.python_sha256,
            'python_semantic_sha256':expected['python_semantic_sha256'],'ledger':before,'wall_ns':elapsed,
            'model_address':self.env.unwrapped.model._address,'data_address':self.env.unwrapped.data._address})
        return value

    def recover(self,snapshot,purpose):
        if id(snapshot) not in self._snapshots or self._snapshots[id(snapshot)][0] is not snapshot:raise ValueError('foreign snapshot')
        before=self.ledger.snapshot();event=self.emit('RESTORE_INTENT',{'purpose':purpose,'ledger':before})
        started=perf_counter_ns();self.ctx=restore(snapshot,self.env,self.policy);elapsed=perf_counter_ns()-started
        self.restores+=1;self.restore_ns+=elapsed
        if self.ledger.snapshot()!=before:raise ValueError('restore rewound physical costs')
        actual=self.witness()
        if actual!=self._snapshots[id(snapshot)][1]:raise ValueError('restored registered state differs')
        self._pending=None
        self.emit('RESTORE_COMPLETE',{'purpose':purpose,'intent_sequence':event['sequence'],'logical_step':self.ctx['calls'],
            **actual,'ledger':before,'wall_ns':elapsed,'model_address':self.env.unwrapped.model._address,'data_address':self.env.unwrapped.data._address})

    def replace_future(self,future):
        if self.ctx['calls']!=4:raise ValueError('future replacement only at registered four-step boundary')
        rows=self.ctx['noise_rows'].copy();past=rows[:4].copy();rows[4:]=fresh_tail(self.seed,future);rows.flags.writeable=False
        self.ctx['noise_rows']=rows
        if not np.array_equal(rows[:4],past):raise ValueError('past noise changed')
        self.emit('FRESH_FUTURE_INSTALLED',{'future':future,'namespace':65001,'logical_step':4,
            'past_sha256':digest(rows[:4].tolist()),'full_sha256':digest(rows.tolist()),**self.witness()})

    def _agent_emit(self,event,payload):
        local={'sequence':self._local,'saved_ns':perf_counter_ns(),**normalize(payload)};self._local+=1
        outer=self.emit('AGENT_EVENT',{**self.branch,'agent_event':event,'public_payload':local})
        self._map[local['sequence']]=outer['sequence']
        # Returned acknowledgement is public and contains no outer evaluator keys.
        if event=='COMMAND':self._pending=normalize(local)
        else:self.choice_refs.append(outer['sequence'])
        return local

    def _agent_step(self,saved):
        if self._pending!=normalize(saved) or saved['at_calls']!=self.ctx['calls']:raise ValueError('unsaved/stale agent command')
        if saved['decision_sequence'] not in self._map:raise ValueError('missing earlier saved choice')
        current=self._step(saved['command'],saved['phase'],saved['raw_policy'],self._map[saved['sequence']]);self._pending=None
        return current

    def execute(self,program,model,evidence=None,*,role,future):
        self.branch={'role':role,'future':future,'program':program};self._local=0;self._map={};self._pending=None
        self.choice_refs=[];self.last_rows=[];self.boundaries={}
        start=self.emit('PROGRAM_START',{**self.branch,'logical_step':self.ctx['calls'],**self.witness()})
        before_queries=self.policy_queries
        if program=='COLD8':
            result=execute_cold(self.task,self.public(),model,self.policy_query,self._agent_step,self._agent_emit)
        else:
            result=execute_warm(program,evidence,self.public(),model,self.policy_query,self._agent_step,self._agent_emit)
        if result['outcome']['total_steps']!=self.ctx['calls'] or result['outcome']['suffix_steps']!=len(self.last_rows):
            raise ValueError('actor/host actual execution differs')
        if result['outcome']['policy_queries']!=self.policy_queries-before_queries:raise ValueError('policy computation count differs')
        summary={**self.branch,'start_sequence':start['sequence'],'outcome':result['outcome'],'fit':result['fit'],
            'fit_prefix':None if result['fit_prefix'] is None else asdict(result['fit_prefix']),
            'choice_global_sequences':list(self.choice_refs),'boundary8':self.boundaries.get(8),
            'final_observation':asdict(self.public()),'end_witness':self.witness()}
        end=self.emit('PROGRAM_COMPLETE',summary);summary['end_sequence']=end['sequence']
        return normalize(summary),result
