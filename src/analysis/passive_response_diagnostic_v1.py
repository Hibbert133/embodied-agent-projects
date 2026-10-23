"""Array-only post-hoc input/response diagnostics, never an online controller.

Actuator truth is accepted only by the evaluator functions. Forecast queries
contain completed visible history and already chosen sent commands, no outcome.
No parameter is fitted, inverted for control, or selected here.
"""
from dataclasses import dataclass,asdict
import numpy as np
from src.probe.linear_command_preflight_v1 import make_query,LinearCommandModel,vector,command,require,TASKS

GAINS={'push-v3':10.,'reach-v3':5.,'door-open-v3':25.}
VARIANTS=('RAW','XY_INCREMENT','ALL_INCREMENT','LAST_RESIDUAL')


@dataclass(frozen=True)
class IncrementQuery:
    task: str
    decision_step: int
    observation_steps: tuple
    observations: tuple
    previous_command: tuple
    current_command: tuple

    def __post_init__(self):
        require(self.task in TASKS and type(self.decision_step) is int and 3<=self.decision_step<500,'real four-observation history required')
        require(tuple(self.observation_steps)==tuple(range(self.decision_step-3,self.decision_step+1))
            and all(type(i) is int for i in self.observation_steps),'consecutive causal timestamps')
        require(len(self.observations)==4,'do not invent initial displacement history')
        object.__setattr__(self,'observation_steps',tuple(self.observation_steps))
        object.__setattr__(self,'observations',tuple(vector(v,39) for v in self.observations))
        for name in ('previous_command','current_command'):
            v=command(getattr(self,name)); require(tuple(np.asarray(v,np.float32).astype(float))==v,'actual float32 sent commands required')
            object.__setattr__(self,name,v)

    @classmethod
    def from_dict(cls,value):
        fields={'schema','task','decision_step','observation_steps','observations','previous_command','current_command'}
        require(type(value) is dict and set(value)==fields and value['schema']=='INCREMENT_DIAGNOSTIC_QUERY_V1','unknown/oracle/future query fields')
        return cls(**{k:value[k] for k in fields if k!='schema'})

    def to_dict(self): return {'schema':'INCREMENT_DIAGNOSTIC_QUERY_V1',**asdict(self)}


def forecast(query,models):
    require(type(query) is IncrementQuery,'strict causal diagnostic query')
    q=make_query(query.task,query.decision_step,query.observations[1:],query.current_command)
    previous=make_query(query.task,query.decision_step-1,query.observations[:-1],query.previous_command)
    past=np.asarray(query.observations[-1])[:2]-np.asarray(query.observations[-2])[:2]
    delta=np.asarray(query.current_command)-query.previous_command
    result={'ZERO':np.zeros(2),'PERSIST':past.copy()}
    for key,model in models.items():
        require(type(model) is LinearCommandModel and model.task==query.task,'matching frozen model')
        raw=model.predict(q,query.current_command); prior=model.predict(previous,query.previous_command); j=model.command_matrix()
        result[key+'/RAW']=raw
        result[key+'/XY_INCREMENT']=past+j[:,:2]@delta[:2]
        result[key+'/ALL_INCREMENT']=past+j@delta
        result[key+'/LAST_RESIDUAL']=raw+(past-prior)
    return result


def feature_batch(states,commands,feature):
    """Row n uses states <=n and command n; no observed outcome n+1."""
    s=np.asarray(states,float); u=np.asarray(commands,float)
    require(s.ndim==2 and s.shape[1]==39 and u.shape==(len(s)-1,4) and np.isfinite(s).all() and np.isfinite(u).all(),'real sequence shape')
    require(len(u)>=3 and feature in ('H10','F20','F43'),'raw model queries start at real step2')
    current,previous,older=s[2:-1],s[1:-2],s[:-3]
    d1=current[:,:3]-previous[:,:3]; d2=previous[:,:3]-older[:,:3]; sent=u[2:]
    if feature=='F43': return np.c_[current,sent]
    if feature=='H10': return np.c_[d1,d2,sent]
    return np.c_[current[:,:3],d1,d2,sent,current[:,3],current[:,4:7]-current[:,:3],current[:,-3:]-current[:,:3]]


def forecast_batch(states,commands,models):
    s=np.asarray(states,float); u=np.asarray(commands,float); n=len(u)
    require(n>=4,'common prediction population needs step3 or later')
    target=s[4:,:2]-s[3:-1,:2]; past=s[3:-1,:2]-s[2:-2,:2]; delta=u[3:]-u[2:-1]
    predictions={'ZERO':np.zeros_like(target),'PERSIST':past.copy()}; features={f:feature_batch(s,u,f) for f in ('H10','F20','F43')}
    for key,model in models.items():
        x=features[model.feature]; raw=np.c_[np.ones(len(x)),(x-model.mean)/model.scale]@np.asarray(model.coefficient)
        j=model.command_matrix(); predictions[key+'/RAW']=raw[1:]
        predictions[key+'/XY_INCREMENT']=past+delta[:,:2]@j[:,:2].T
        predictions[key+'/ALL_INCREMENT']=past+delta@j.T
        predictions[key+'/LAST_RESIDUAL']=raw[1:]+past-raw[:-1]
    return target,predictions


def apply32(sent,fault,noise):
    """Injected input map, not a prediction of physical robot motion."""
    u=np.asarray(sent,np.float32).copy(); require(u.shape==(4,) and np.isfinite(u).all() and np.all(abs(u)<=1),'bounded sent action')
    a=np.asarray(fault['matrix_xy'],np.float32); b=np.asarray(fault['bias_xy'],np.float32); z=np.asarray(fault['deadzone_xy'],np.float32)
    eta=np.asarray(noise,np.float32); require(a.shape==(2,2) and b.shape==z.shape==(2,) and eta.shape==(3,),'known evaluator input-map shapes')
    require(np.isfinite(a).all() and np.isfinite(b).all() and np.isfinite(z).all() and np.isfinite(eta).all() and np.all((z>=0)&(z<1)),'finite evaluator coefficients')
    latent=a@u[:2]+b; u[:2]=np.sign(latent)*np.maximum(abs(latent)-z,np.float32(0))/(np.float32(1)-z)
    u[:3]+=eta
    return np.clip(u,-1,1),bool(np.any(abs(u)>1))


def input_discrepancy(sent,base,raw,fault,noise):
    """Compare candidate input maps at one actual visited observation.

    Base/ref actions and zero-noise maps are unexecuted input arithmetic. Neither
    these errors nor their differences are physical-response or task outcomes.
    """
    ref=np.clip(np.asarray(raw,np.float32),-1,1)
    identity={'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'deadzone_xy':[0.,0.]}
    result={}
    for name,eta in (('ZERO_NOISE_INPUT_MAP',np.zeros(3,np.float32)),('SAME_SAVED_NOISE_INPUT_MAP',noise)):
        desired,_=apply32(ref,identity,eta); actual,_=apply32(sent,fault,eta); shadow,_=apply32(base,fault,eta)
        p=float(np.mean((actual[:2].astype(float)-desired[:2])**2)); b=float(np.mean((shadow[:2].astype(float)-desired[:2])**2))
        result[name]={'actual_sent_mse':p,'unexecuted_base_mse':b,'pi_minus_base_mse':p-b}
    return result


def encode_base(controller,raw):
    u=np.clip(np.asarray(raw,np.float32),-1,1).astype(float)
    xy=np.asarray(controller['matrix_xy'])@u[:2]+np.asarray(controller['offset'])[:2]
    u[:2]=xy
    return np.clip(u,-1,1).astype(np.float32),bool(np.any(abs(xy)>1))


def policy_phase(task,observation):
    o=np.asarray(observation); h=o[:3]; obj=o[4:7].copy()
    if task=='reach-v3': return 'REACH_GOAL'
    if task=='push-v3':
        obj[0]-=.005
        return 'ABOVE_OBJECT' if np.linalg.norm(h[:2]-obj[:2])>.02 else 'DESCEND_OBJECT' if abs(h[2]-obj[2])>.04 else 'PUSH_TO_GOAL'
    require(task=='door-open-v3','registered fixed policy'); obj[0]-=.05
    return 'ABOVE_HANDLE' if np.linalg.norm(h[:2]-obj[:2])>.12 else 'DESCEND_HANDLE' if abs(h[2]-obj[2])>.04 else 'PUSH_HANDLE'


def movement_segment(index):
    require(type(index) is int and 1<=index<=64,'actual movement step')
    return '1-8' if index<=8 else '9-16' if index<=16 else '17-32' if index<=32 else '33-64'
