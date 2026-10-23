"""Saved float32 command-effect plans, not an inverse controller or task method."""
from dataclasses import dataclass
import hashlib
import json
import re
import numpy as np
from src.probe import linear_command_preflight_v1 as previous

BRANCHES = ('BASELINE','X_PLUS','X_MINUS','Y_PLUS','Y_MINUS')
TARGETS = ('COLD_STEP2','POST_MOVE_MEAS0','POST_MEASURE_TASK0')


def require(value,message):
    if not value: raise ValueError(message)


def sent32(command):
    return tuple(float(x) for x in np.asarray(previous.command(command),dtype=np.float32))


def physical_candidates(baseline):
    baseline=previous.command(baseline)
    require(sent32(baseline)==baseline,'baseline must already be an actual float32 sent command')
    return ((BRANCHES[0],baseline),*tuple((c.action_id,sent32(c.command)) for c in previous.fixed_candidates(baseline)))


@dataclass(frozen=True)
class PhysicalQuery:
    task: str
    decision_step: int
    observation_steps: tuple
    observations: tuple
    baseline_command: tuple
    candidates: tuple

    def __post_init__(self):
        # Preserve the frozen three-observation feature semantics. The previous
        # ideal-offset candidates are not predictions or commands of this version.
        require(isinstance(self.observation_steps,(list,tuple)),'real observation stamps required')
        legacy=previous.make_query(self.task,self.decision_step,self.observations,self.baseline_command)
        require(tuple(self.observation_steps)==legacy.observation_steps and all(type(x) is int for x in self.observation_steps),
                'future or nonconsecutive observations')
        expected=physical_candidates(legacy.baseline_command)
        require(isinstance(self.candidates,(list,tuple)),'candidate container required')
        actual=tuple((v[0],previous.command(v[1])) for v in self.candidates if isinstance(v,(list,tuple)) and len(v)==2)
        require(len(actual)==len(self.candidates) and actual==expected,'all five exact float32 candidate commands required')
        object.__setattr__(self,'observation_steps',legacy.observation_steps)
        object.__setattr__(self,'observations',legacy.observations)
        object.__setattr__(self,'baseline_command',legacy.baseline_command)
        object.__setattr__(self,'candidates',expected)

    @classmethod
    def create(cls,task,step,history,baseline):
        return cls(task,step,tuple(range(step-2,step+1)),history,baseline,physical_candidates(baseline))

    @classmethod
    def from_dict(cls,value):
        require(type(value) is dict and set(value)=={'schema','task','decision_step','observation_steps','observations','baseline_command','candidates'}
                and value['schema']=='PHYSICAL_COMMAND_QUERY_V1','unknown/oracle/future query fields')
        require(all(type(c) is dict and set(c)=={'action_id','sent_command'} for c in value['candidates']),'candidate fields rejected')
        return cls(value['task'],value['decision_step'],value['observation_steps'],value['observations'],value['baseline_command'],
                   tuple((c['action_id'],c['sent_command']) for c in value['candidates']))

    def to_dict(self):
        return {'schema':'PHYSICAL_COMMAND_QUERY_V1','task':self.task,'decision_step':self.decision_step,
                'observation_steps':list(self.observation_steps),'observations':[list(v) for v in self.observations],
                'baseline_command':list(self.baseline_command),
                'candidates':[{'action_id':name,'sent_command':list(command)} for name,command in self.candidates]}

    def legacy_features(self):
        return previous.make_query(self.task,self.decision_step,self.observations,self.baseline_command)


@dataclass(frozen=True)
class SavedPlan:
    query: PhysicalQuery
    # (model key, immutable source SHA, five physical-unit XY predictions)
    predictions: tuple

    def __post_init__(self):
        require(type(self.query) is PhysicalQuery,'strict physical query')
        expected={f'{s}/{self.query.task}/LINEAR_{f}' for s in ('FEEDBACK8','BALANCED8') for f in ('H10','F20','F43')}
        values=[]
        for key,sha,predictions in self.predictions:
            require(key in expected and type(sha) is str and re.fullmatch('[0-9a-f]{64}',sha) is not None,'model/source binding')
            require(len(predictions)==5,'all physical command predictions required')
            values.append((key,sha,tuple(previous.vector(p,2) for p in predictions)))
        require(len(values)==6 and {v[0] for v in values}==expected,'all six task-bound frozen linear references')
        object.__setattr__(self,'predictions',tuple(sorted(values)))

    @classmethod
    def build(cls,query,models):
        require(type(query) is PhysicalQuery,'strict query before prediction')
        require(type(models) is dict and len(models)==6,'all six frozen task models')
        legacy=query.legacy_features(); results=[]
        for key,(model,sha) in models.items():
            require(type(model) is previous.LinearCommandModel and model.task==query.task
                    and key.endswith('/LINEAR_'+model.feature),'only correctly mapped frozen linear responses')
            results.append((key,sha,tuple(tuple(model.predict(legacy,command)) for _,command in query.candidates)))
        return cls(query,tuple(results))

    @classmethod
    def from_dict(cls,value):
        require(type(value) is dict and set(value)=={'schema','query','models','physical_qualification','task_benefit'}
                and value['schema']=='SAVED_PHYSICAL_CONTRAST_PLAN_V1' and value['physical_qualification'] is False
                and value['task_benefit'] is False,'only predictive plans without qualification claims')
        query=PhysicalQuery.from_dict(value['query']); rows=[]
        for key,row in value['models'].items():
            require(type(row) is dict and set(row)=={'source_sha256','predictions_m'},'model fields rejected')
            rows.append((key,row['source_sha256'],row['predictions_m']))
        return cls(query,tuple(rows))

    def to_dict(self):
        return {'schema':'SAVED_PHYSICAL_CONTRAST_PLAN_V1','query':self.query.to_dict(),
                'models':{key:{'source_sha256':sha,'predictions_m':[list(p) for p in values]} for key,sha,values in self.predictions},
                'physical_qualification':False,'task_benefit':False}

    def digest(self):
        return hashlib.sha256(json.dumps(self.to_dict(),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class PlanConsumer:
    def __init__(self,plan):
        require(type(plan) is SavedPlan,'saved plan required')
        self.plan=plan; self.used=False

    def consume(self,current,action_id,remaining_budget):
        require(not self.used,'a branch plan is consumed at most once')
        require(type(current) is PhysicalQuery and current==self.plan.query,'actual current history differs from saved plan')
        require(type(remaining_budget) is int and remaining_budget>=1,'one actual control step must remain')
        require(type(action_id) is str and action_id in BRANCHES,'unregistered physical branch')
        command=dict(self.plan.query.candidates)[action_id]
        require(sent32(command)==command,'saved sent-command precision changed')
        self.used=True
        return {'plan_sha256':self.plan.digest(),'action_id':action_id,'sent_command':list(command),'decision_step':current.decision_step}


def reaches_target(target,payload):
    require(target in TARGETS,'registered intervention stage')
    if target=='COLD_STEP2': return payload['at_calls']==2 and payload['phase']=='FIXED_PROBE'
    if target=='POST_MOVE_MEAS0': return payload['phase'] in ('MEASURE_FEEDBACK','MEASURE_BALANCED')
    return payload['phase']=='TASK_AFTER_MEASUREMENT'
