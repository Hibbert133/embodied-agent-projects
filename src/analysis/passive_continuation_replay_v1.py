"""Saved public feedback only; stop before reading an outcome after divergence."""
from copy import deepcopy
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.response_qualification_io_v1 import require,digest
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt


def same(a,b,message):require(digest(normalize(a))==digest(normalize(b)),message)


def public_observation(value):
    require(type(value) is dict and set(value)=={'observation','success','terminated','truncated'},'strict public observation, no private/future fields')
    v=value['observation'];require(type(v) in (list,tuple) and len(v)==39 and np.isfinite(v).all(),'real39 public observation')
    require(all(type(value[k]) is bool for k in ('success','terminated','truncated')),'literal public end flags')
    return normalize(value)


def action(value):
    require(type(value) in (tuple,list) and len(value)==4 and all(type(v) in (float,int) for v in value),'public four-dimensional action')
    a=np.asarray(value,np.float32);require(np.isfinite(a).all() and a.astype(float).tolist()==list(value),'original finite float32 action')
    return a.tolist()


class Divergence(ValueError):
    def __init__(self,step,expected,proposed,outcomes_read):
        self.step=step;self.expected=expected;self.proposed=proposed;self.outcomes_read=outcomes_read
        super().__init__('Unexecuted continuation: reject before reading outcome at step '+str(step))


class SavedFeedback:
    def __init__(self,initial,steps):
        self.initial=public_observation(initial);require(type(steps) is list and len(steps)<=500,'bounded saved source trace')
        self.steps=deepcopy(steps)
        for i,row in enumerate(self.steps):
            require(type(row) is dict and set(row)=={'at_calls','before','after','command','raw_policy'},'strict public step only')
            require(type(row['at_calls']) is int and row['at_calls']==i,'real consecutive source step')
        self.current=deepcopy(self.initial);self.cursor=self.policy_reads=self.outcomes_read=0
        self.pending=None;self.query_pending=False;self.events=[];self.executed_commands=[]

    def policy(self,observation):
        require(not self.query_pending and self.pending is None and self.cursor<len(self.steps),'one saved policy action for current real state')
        same(public_observation(self.steps[self.cursor]['before']),self.current,'nonconsecutive public source history')
        require(not any(self.current[k] for k in ('success','terminated','truncated')),'source step after end')
        same(np.asarray(observation).tolist(),self.current['observation'],'policy queried at stale or future observation')
        self.policy_reads+=1;self.query_pending=True
        return np.asarray(action(self.steps[self.cursor]['raw_policy']),np.float32)

    def emit(self,kind,payload):
        p=normalize(payload);require(p['at_calls']==self.cursor,'replay logical time')
        if kind=='COMMAND':
            require(self.query_pending and self.pending is None and self.cursor<len(self.steps),'command without current saved policy action')
            same(p['before'],self.current,'command at different current state')
            same(p['raw_policy'],self.steps[self.cursor]['raw_policy'],'changed original raw policy')
            proposed=action(p['command']);expected=action(self.steps[self.cursor]['command'])
            if proposed!=expected:raise Divergence(self.cursor,expected,proposed,self.outcomes_read)
        p={**p,'sequence':len(self.events),'saved_ns':len(self.events)+1};self.events.append(dict(kind=kind,payload=deepcopy(p)))
        if kind=='COMMAND':self.pending=deepcopy(p)
        return p

    def step(self,saved):
        require(self.pending is not None,'no actual saved command')
        same(saved,self.pending,'changed or repeated saved command')
        self.executed_commands.append(deepcopy(saved['command']));self.current=public_observation(self.steps[self.cursor]['after'])
        self.cursor+=1;self.outcomes_read+=1;self.pending=None;self.query_pending=False
        return StepReceipt(StepObservation(**self.current),self.cursor)


def run(task,boundary,initial,steps,program):
    from src.probe.release_learning_actor_v1 import run as actual_actor
    source=SavedFeedback(initial,steps)
    def no_random(*args,**kwargs):raise RuntimeError('No physical randomization or new RNG is available in this saved-record analysis')
    result=actual_actor(task,StepObservation(**initial),boundary,program,None,source.policy,source.step,source.emit,
        runtime=dict(receiver=None,pre_bank=None,policy=None),draw_exposure=no_random)
    require(source.cursor==len(steps)==source.outcomes_read==source.policy_reads and source.pending is None,'complete actual source replay, no imputation')
    same(result['outcome']['final_memory']['current'],source.current,'source final observation')
    return result,source
