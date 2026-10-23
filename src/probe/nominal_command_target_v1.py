"""Public sent-command summary, not an observed or qualified actuator state.

The reset target, workspace and input scale are declared installed-environment
priors. Unknown perturbations and execution noise are deliberately absent.
No Env, simulator, private state, fitted parameter or future result is accepted.
"""
from dataclasses import dataclass
import hashlib,json
import numpy as np

TASKS=('push-v3','reach-v3','door-open-v3')
INITIAL=(0.,.6,.2)
LOW=(-.5,.4,.05)
HIGH=(.5,1.,.5)
SCALE=.01
SCHEMA='PUBLIC_NOMINAL_COMMAND_TARGET_V1'


def require(value,message):
    if not value:raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def finite_vector(value,n):
    require(type(value) in (tuple,list) and len(value)==n,'ordinary finite vector required')
    require(all(type(x) in (int,float) and np.isfinite(x) for x in value),'private, boolean or nonfinite vector element')
    return tuple(float(x) for x in value)


def public_command(value):
    result=finite_vector(value,4)
    require(max(abs(x) for x in result)<=1.,'bounded public sent command required')
    return tuple(float(x) for x in np.asarray(result,dtype=np.float32))


def target_update(before,command):
    """Declared float32 command scale, then float64 target addition/workspace clip."""
    target=np.asarray(finite_vector(before,3),dtype=np.float64)
    action=np.asarray(public_command(command)[:3],dtype=np.float32)
    requested=target+np.clip(action,-1,1)*SCALE
    after=np.clip(requested,np.asarray(LOW),np.asarray(HIGH))
    return {'target':after.tolist(),'requested_target':requested.tolist(),
        'workspace_clip_axes':(requested!=after).tolist()}


@dataclass(frozen=True)
class PublicNominalTarget:
    task: str
    completed_commands: int
    target: tuple

    def __post_init__(self):
        require(self.task in TASKS and type(self.completed_commands) is int and 0<=self.completed_commands<=500,'registered public task and command clock')
        target=finite_vector(self.target,3)
        require(all(lo<=x<=hi for lo,x,hi in zip(LOW,target,HIGH)),'public working target outside workspace')
        object.__setattr__(self,'target',target)

    @classmethod
    def initial(cls,task,*,controlled_reset_declared):
        require(controlled_reset_declared is True,'explicit initial reset contract required')
        return cls(task,0,INITIAL)

    def to_dict(self):
        return {'schema':SCHEMA,'task':self.task,'completed_commands':self.completed_commands,'target':list(self.target),
            'source':'DECLARED_RESET_PRIOR_AND_PAST_SENT_COMMANDS','assumption':'IDENTITY_INPUT_ZERO_EXECUTION_NOISE',
            'is_observed_private_state':False,'physical_state_qualified':False,'probability_or_safety_guarantee':False}

    @classmethod
    def from_dict(cls,value):
        require(type(value) is dict and set(value)==set(cls('push-v3',0,INITIAL).to_dict()),'strict public state fields; private/future extras rejected')
        result=cls(value['task'],value['completed_commands'],tuple(value['target']))
        require(digest(value)==digest(result.to_dict()),'working reference cannot gain unearned qualification')
        return result

    def propose(self,command):
        require(self.completed_commands<500,'public command budget exhausted')
        sent=public_command(command);numbers=target_update(self.target,sent)
        after=PublicNominalTarget(self.task,self.completed_commands+1,tuple(numbers['target']))
        return {'schema':'PUBLIC_NOMINAL_TARGET_PLAN_V1','before_sha256':digest(self.to_dict()),'command':list(sent),
            'numbers':numbers,'after':after.to_dict()}

    def consume(self,saved):
        require(type(saved) is dict and 'command' in saved,'saved public target plan required')
        expected=self.propose(saved['command']);require(digest(saved)==digest(expected),'changed, stale or private-field plan')
        return PublicNominalTarget.from_dict(saved['after'])
