"""Strict causal initial-state queries for a known eight-command packet."""
from dataclasses import dataclass,asdict
import numpy as np
from src.probe.nominal_command_target_v1 import finite_vector,PublicNominalTarget

TASKS=('push-v3','reach-v3','door-open-v3');HORIZON=8;HISTORY=16;CONTEXT_DIM=723
METHODS=('SS_SENT','SS_NO_SENT','SS_CURRENT_SENT','DIRECT_MLP_H8','DIRECT_RIDGE_H8','PERSIST_ZERO','HISTORY_LINEAR10','QUADRATIC_STATE20')


def require(ok,message):
    if not ok:raise ValueError(message)


@dataclass(frozen=True)
class ForecastQuery:
    task:str
    completed_steps:int
    observations:tuple
    previous_commands:tuple
    has_previous:tuple
    nominal_offset:tuple
    planned_commands:tuple

    def __post_init__(self):
        require(self.task in TASKS and type(self.completed_steps) is int and 0<=self.completed_steps<=500,'public task and actual completed clock')
        obs=tuple(finite_vector(o,39) for o in self.observations);cmd=tuple(finite_vector(u,4) for u in self.previous_commands)
        require(1<=len(obs)<=16 and len(cmd)==len(obs)==len(self.has_previous),'actual history length')
        require(all(type(x) is int and x in (0,1) for x in self.has_previous),'explicit previous-input availability')
        start=self.completed_steps-len(obs)+1;require(start>=0,'no fabricated earlier state')
        require(tuple(self.has_previous)==tuple(int(start+i>0) for i in range(len(obs))),'true initial previous-action mask')
        require(all(max(abs(x) for x in u)<=1 for u in cmd),'bounded past sent commands')
        require(self.has_previous[0] or cmd[0]==(0.,0.,0.,0.),'initial previous input is an explicitly absent placeholder')
        planned=tuple(finite_vector(u,4) for u in self.planned_commands)
        require(len(planned)==8 and all(max(abs(u[0]),abs(u[1]))<=float(np.float32(.8)) and u[2:]==(0.,0.) for u in planned),'eight predeclared XY commands, zero Z/grip')
        require(all(tuple(float(x) for x in np.asarray(u,np.float32))==u for u in planned),'actual float32 planned command representation')
        object.__setattr__(self,'observations',obs);object.__setattr__(self,'previous_commands',cmd)
        object.__setattr__(self,'has_previous',tuple(self.has_previous));object.__setattr__(self,'planned_commands',planned)
        object.__setattr__(self,'nominal_offset',finite_vector(self.nominal_offset,3))

    def to_dict(self):return {'schema':'PUBLIC_LATENT_PACKET_QUERY_V1',**asdict(self)}

    @classmethod
    def from_dict(cls,value):
        require(type(value) is dict and set(value)=={'schema','task','completed_steps','observations','previous_commands','has_previous','nominal_offset','planned_commands'},'no oracle/seed/future-outcome fields')
        require(value['schema']=='PUBLIC_LATENT_PACKET_QUERY_V1','public packet query version');return cls(**{k:v for k,v in value.items() if k!='schema'})


def make_query(trajectory,at,planned_commands):
    from src.analysis.native_command_witness_host_v1 import public_prefix
    p=public_prefix(trajectory,at);all_obs=[p['initial_observation'],*p['past_observations']];start=max(0,at-15)
    obs=all_obs[start:at+1];previous=[p['past_commands'][j-1] if j else [0.,0.,0.,0.] for j in range(start,at+1)]
    offset=(np.asarray(p['nominal_reference']['target'])-np.asarray(p['current_observation'][:3])).tolist()
    return ForecastQuery(p['task'],at,tuple(obs),tuple(previous),tuple(int(j>0) for j in range(start,at+1)),tuple(offset),tuple(planned_commands))


def raw_frames(q):
    require(type(q) is ForecastQuery,'strict causal query required')
    return np.c_[np.asarray(q.observations),np.asarray(q.previous_commands)]


def context(q,normalization,method):
    require(method in METHODS,'registered representation');x=raw_frames(q);n=len(x)
    z=(x-np.asarray(normalization['history_mean']))/normalization['history_scale']
    result=np.zeros((16,45),float);result[-n:,:43]=z;result[-n:,43]=q.has_previous;result[-n:,44]=1.
    if method=='SS_CURRENT_SENT':result[:-1]=0.
    off=(np.asarray(q.nominal_offset)-normalization['offset_mean'])/normalization['offset_scale']
    if method=='SS_NO_SENT':off=np.zeros(3)
    return np.r_[result.ravel(),off]


def baseline20(q):
    require(type(q) is ForecastQuery and len(q.observations)>=3,'two real historical displacements required')
    s=np.asarray(q.observations);p=s[-1,:3]
    return np.r_[p,p-s[-2,:3],s[-2,:3]-s[-3,:3],q.planned_commands[0],s[-1,3],s[-1,4:7]-p,s[-1,-3:]-p]


def assert_public_training_window(value):
    require(type(value) is dict and set(value)=={'query','targets','mask'},'strict supervised window, no private labels')
    q=ForecastQuery.from_dict(value['query']);target=np.asarray(value['targets'],float);mask=value['mask']
    require(target.shape==(8,2) and np.isfinite(target).all() and type(mask) is list and len(mask)==8 and all(type(v) is bool for v in mask),'finite masked public responses')
    require(any(mask) and mask==sorted(mask,reverse=True),'actual contiguous partial response prefix')
    require(np.all(target[np.logical_not(mask)]==0.),'explicit unused target storage; masked out of every loss')
    return q,target,np.array(mask,bool)
