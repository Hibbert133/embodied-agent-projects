"""Task-time integral reference in sent-command units; no learned forward plant.

The policy error is the current unbounded float32 policy output divided by
its fixed task P gain. A saved plan determines one bounded XY command. Integral
state is committed by the actor only after the physical receipt, never here.
"""
from dataclasses import dataclass
import hashlib
import json
import numpy as np
from src.probe.continuous import StepObservation
from src.probe.operator_identification import encode_controller

GAINS={'push-v3':10.,'reach-v3':5.,'door-open-v3':25.}
TIME_CONSTANTS=(.125,.5,2.,8.)
DT=.0125
INTEGRAL_LIMIT=2.


def require(ok,message):
    if not ok: raise ValueError(message)


def vector(value,size):
    require(isinstance(value,(tuple,list,np.ndarray)) and len(value)==size,'exact public vector size')
    require(all(not isinstance(x,(bool,np.bool_)) and isinstance(x,(int,float,np.number)) for x in value),'numeric vector, no booleans')
    a=np.asarray(value,float); require(a.shape==(size,) and np.isfinite(a).all(),'finite ordinary public vector')
    return tuple(float(x) for x in a)


def controller(value):
    require(type(value) is dict and set(value)=={'source','matrix_xy','offset'} and value['source'] in ('UNCORRECTED','ESTIMATED_AFFINE'),
            'only saved visible C8 or exact identity controller')
    m=value['matrix_xy']; require(isinstance(m,(tuple,list)) and len(m)==2,'controller matrix')
    m=tuple(vector(r,2) for r in m); o=vector(value['offset'],4)
    require(o[2:]==(0.,0.) and max(abs(x) for r in m for x in r)<=4.+1e-7,'numeric XY mapping, preserve Z/grip')
    require(abs(m[0][0]*m[1][1]-m[0][1]*m[1][0])>1e-12,'nonsingular saved numeric controller')
    if value['source']=='UNCORRECTED': require(m==((1.,0.),(0.,1.)) and o==(0.,0.,0.,0.),'identity cannot contain a correction')
    return (value['source'],m,o)


@dataclass(frozen=True)
class PIQuery:
    task: str
    step: int
    current: StepObservation
    raw_policy: tuple
    saved_controller: tuple
    integral_before: tuple
    time_constant_s: float

    def __post_init__(self):
        require(self.task in GAINS and type(self.step) is int and 0<=self.step<500,'registered task and current step')
        require(type(self.current) is StepObservation and len(self.current.observation)==39 and
                not any((self.current.success,self.current.terminated,self.current.truncated)),'live current public observation')
        raw=vector(self.raw_policy,4)
        require(tuple(float(x) for x in np.asarray(raw,np.float32))==raw,'original float32 policy query required')
        require(isinstance(self.saved_controller,(tuple,list)) and len(self.saved_controller)==3,'saved controller tuple required')
        source,m,o=self.saved_controller; c=controller({'source':source,'matrix_xy':m,'offset':o})
        state=vector(self.integral_before,2); require(max(abs(x) for x in state)<=INTEGRAL_LIMIT,'bounded integral state')
        require(type(self.time_constant_s) in (int,float) and self.time_constant_s in TIME_CONSTANTS,'frozen positive time constant, seconds')
        object.__setattr__(self,'raw_policy',raw); object.__setattr__(self,'saved_controller',c)
        object.__setattr__(self,'integral_before',state); object.__setattr__(self,'time_constant_s',float(self.time_constant_s))

    @classmethod
    def create(cls,task,step,current,raw,base,integral,time_constant):
        return cls(task,step,current,tuple(float(x) for x in np.asarray(vector(raw,4),np.float32)),controller(base),integral,time_constant)

    @classmethod
    def from_dict(cls,value):
        require(type(value) is dict and set(value)=={'schema','task','step','current','raw_policy','controller','integral_before','time_constant_s'}
                and value['schema']=='TASK_PI_QUERY_V1','unknown/oracle/future query fields')
        cur=value['current']; require(type(cur) is dict and set(cur)=={'observation','success','terminated','truncated'},'strict public state')
        return cls(value['task'],value['step'],StepObservation(**cur),value['raw_policy'],controller(value['controller']),
                   value['integral_before'],value['time_constant_s'])

    def base_controller(self):
        source,m,o=self.saved_controller
        return {'source':source,'matrix_xy':[list(r) for r in m],'offset':list(o)}

    def to_dict(self):
        return {'schema':'TASK_PI_QUERY_V1','task':self.task,'step':self.step,
            'current':{'observation':list(self.current.observation),'success':self.current.success,'terminated':self.current.terminated,'truncated':self.current.truncated},
            'raw_policy':list(self.raw_policy),'controller':self.base_controller(),'integral_before':list(self.integral_before),'time_constant_s':self.time_constant_s}


@dataclass(frozen=True)
class PIPlan:
    query: PIQuery

    def __post_init__(self): require(type(self.query) is PIQuery,'strict current query')

    def numbers(self):
        q=self.query; error=np.asarray(q.raw_policy[:2])/GAINS[q.task]
        base=encode_controller(q.base_controller(),q.raw_policy).astype(float)
        derivative=np.asarray(q.saved_controller[1])@(GAINS[q.task]*error)/q.time_constant_s
        proposed=np.asarray(q.integral_before)+DT*derivative
        bounded=np.clip(proposed,-INTEGRAL_LIMIT,INTEGRAL_LIMIT)
        unclipped=base[:2]+bounded
        clipped=np.clip(unclipped,-1.,1.)
        sent=base.copy(); sent[:2]=clipped; sent=sent.astype(np.float32).astype(float)
        # Projection anti-windup uses the actual rounded command and bounded
        # baseline. This is command limiting, not a physical safety guarantee.
        after=sent[:2]-base[:2]
        return {'position_error_xy_m':error.tolist(),'base_command':base.tolist(),
            'integral_rate_command_per_s':derivative.tolist(),'integral_proposed':proposed.tolist(),
            'integral_bounded':bounded.tolist(),'unclipped_xy_command':unclipped.tolist(),
            'sent_command':sent.tolist(),'integral_after_receipt':after.tolist(),
            'integral_limit_active':bool(np.any(proposed!=bounded)),
            'send_roundoff_xy':(sent[:2]-clipped).tolist(),
            'send_limit_active':bool(np.any(unclipped!=clipped))}

    def to_dict(self):
        return {'schema':'TASK_PI_SAVED_PLAN_V1','query':self.query.to_dict(),'dt_s':DT,'integral_limit_command':INTEGRAL_LIMIT,
            'antiwindup':'PROJECT_ACTUAL_FLOAT32_SEND_MINUS_BOUNDED_BASE','numbers':self.numbers(),
            'physical_response_qualified':False,'safety_guarantee':False,'task_benefit_established':False}

    @classmethod
    def from_dict(cls,value):
        require(type(value) is dict,'saved plan mapping'); require(set(value)=={'schema','query','dt_s','integral_limit_command','antiwindup','numbers',
            'physical_response_qualified','safety_guarantee','task_benefit_established'},'unknown saved-plan fields')
        expected=cls(PIQuery.from_dict(value['query']))
        require(digest(value)==digest(expected.to_dict()),'saved PI plan arithmetic or claims changed')
        return expected

    @property
    def sha256(self): return digest(self.to_dict())


def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class PlanConsumer:
    def __init__(self,plan):
        require(type(plan) is PIPlan,'immutable saved plan required'); self.plan=plan; self.used=False

    def consume(self,current,remaining_steps):
        require(not self.used,'PI plan already consumed')
        require(type(current) is PIQuery and current==self.plan.query,'stale policy/observation/integral state')
        require(type(remaining_steps) is int and 1<=remaining_steps<=500-current.step,'actual remaining budget required')
        self.used=True
        return {'at_calls':current.step,'plan_sha256':self.plan.sha256,'command':self.plan.numbers()['sent_command']}
