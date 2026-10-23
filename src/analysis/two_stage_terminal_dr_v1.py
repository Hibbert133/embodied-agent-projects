"""Standard two-stage DR full-cost reference, not a new algorithm or safety test.

Inputs are completed logged histories plus predictions made before decisions.
Only the actually observed terminal outcome enters the correction term.
"""
from dataclasses import dataclass,asdict
import math
from src.analysis.response_qualification_io_v1 import require,digest

ACTIONS=('CONTINUE','VALIDATE','MOVE_VALIDATE')
TAILS=('KEEP','UPDATE')


def finite_vector(value,n):
    require(type(value) in (tuple,list) and len(value)==n,'fixed finite vector')
    require(all(type(x) in (int,float) and math.isfinite(x) for x in value),'finite ordinary numbers, no booleans')
    return tuple(float(x) for x in value)


def probabilities(value,n):
    p=finite_vector(value,n);require(all(0<=x<=1 for x in p) and math.isclose(sum(p),1,rel_tol=0,abs_tol=1e-12),'complete probability distribution')
    return p


def supported(target,behavior):require(all(t==0 or b>0 for t,b in zip(target,behavior)),'target policy has unsupported logged action')


@dataclass(frozen=True)
class History1:
    completed_steps:int
    observed_code:int
    integral_xy:tuple
    time_constant_s:float

    def __post_init__(self):
        require(type(self.completed_steps) is int and 0<=self.completed_steps<500,'actual live prefix')
        require(type(self.observed_code) is int and self.observed_code in (0,1),'synthetic visible code, not a hidden context field')
        integral=finite_vector(self.integral_xy,2);require(max(abs(v) for v in integral)<=2,'public task-memory bounds')
        require(type(self.time_constant_s) in (float,int) and self.time_constant_s in (.125,.5,2.,8.),'known public controller rate')
        object.__setattr__(self,'integral_xy',integral);object.__setattr__(self,'time_constant_s',float(self.time_constant_s))

    def to_dict(self):return {'schema':'SYNTHETIC_BRANCH_HISTORY1_V1',**asdict(self),'integral_xy':list(self.integral_xy)}
    @property
    def sha256(self):return digest(self.to_dict())
    @classmethod
    def from_dict(cls,v):
        require(type(v) is dict and set(v)=={'schema','completed_steps','observed_code','integral_xy','time_constant_s'} and v['schema']=='SYNTHETIC_BRANCH_HISTORY1_V1','unknown/private/future prehistory fields')
        return cls(*(v[k] for k in ('completed_steps','observed_code','integral_xy','time_constant_s')))


@dataclass(frozen=True)
class History2:
    prehistory_sha256:str
    action:str
    completed_steps:int
    observed_position_bin:str
    measured_residual:float
    integral_xy:tuple

    def __post_init__(self):
        require(type(self.prehistory_sha256) is str and len(self.prehistory_sha256)==64 and all(x in '0123456789abcdef' for x in self.prehistory_sha256),'actual saved parent history')
        require(self.action in ACTIONS and self.observed_position_bin in ('NEAR','FAR'),'observed action/poststate, no applicability truth')
        require(type(self.completed_steps) is int and 0<=self.completed_steps<500,'live post-option budget')
        r=finite_vector((self.measured_residual,),1)[0];require(r>=0,'observed residual')
        integral=finite_vector(self.integral_xy,2);require(max(abs(v) for v in integral)<=2,'post-option task memory')
        object.__setattr__(self,'measured_residual',r);object.__setattr__(self,'integral_xy',integral)

    def to_dict(self):return {'schema':'SYNTHETIC_BRANCH_HISTORY2_V1',**asdict(self),'integral_xy':list(self.integral_xy)}
    @property
    def sha256(self):return digest(self.to_dict())
    @classmethod
    def from_dict(cls,v):
        require(type(v) is dict and set(v)=={'schema','prehistory_sha256','action','completed_steps','observed_position_bin','measured_residual','integral_xy'} and v['schema']=='SYNTHETIC_BRANCH_HISTORY2_V1','unknown/private/future posthistory fields')
        return cls(*(v[k] for k in ('prehistory_sha256','action','completed_steps','observed_position_bin','measured_residual','integral_xy')))


@dataclass(frozen=True)
class LoggedTerminal:
    before:History1
    action:str
    option_actual_steps:int
    option_ended:str
    after:object
    tail_action:object
    tail_actual_steps:object
    tail_success:object
    full_deadline_loss:int

    def __post_init__(self):
        require(type(self.before) is History1 and self.action in ACTIONS,'public causal first history/action')
        require(type(self.option_actual_steps) is int and self.option_actual_steps>=0 and self.before.completed_steps+self.option_actual_steps<=500,'actual option cost fits budget')
        require(self.option_ended in ('NONE','SUCCESS','FAILURE'),'known option termination status')
        t=self.before.completed_steps+self.option_actual_steps
        if self.option_ended!='NONE':
            require(all(v is None for v in (self.after,self.tail_action,self.tail_actual_steps,self.tail_success)),'terminal option has no fabricated second decision')
            expected=t if self.option_ended=='SUCCESS' else 500
        else:
            require(type(self.after) is History2 and self.after.prehistory_sha256==self.before.sha256 and self.after.action==self.action and self.after.completed_steps==t,'actual post-option parent/state/time')
            require(self.tail_action in TAILS and type(self.tail_actual_steps) is int and 0<=self.tail_actual_steps<=500-t and type(self.tail_success) is bool,'actual observed tail and its cost')
            expected=t+self.tail_actual_steps if self.tail_success else 500
        require(type(self.full_deadline_loss) is int and self.full_deadline_loss==expected,'full cutoff loss includes option once and failure penalty')

    def to_dict(self):return {'schema':'LOGGED_TERMINAL_BRANCH_V1','before':self.before.to_dict(),'action':self.action,'option_actual_steps':self.option_actual_steps,
        'option_ended':self.option_ended,'after':None if self.after is None else self.after.to_dict(),'tail_action':self.tail_action,'tail_actual_steps':self.tail_actual_steps,
        'tail_success':self.tail_success,'full_deadline_loss':self.full_deadline_loss}

    @classmethod
    def from_dict(cls,v):
        names=('before','action','option_actual_steps','option_ended','after','tail_action','tail_actual_steps','tail_success','full_deadline_loss')
        require(type(v) is dict and set(v)=={'schema',*names} and v['schema']=='LOGGED_TERMINAL_BRANCH_V1','unknown logged-terminal fields')
        return cls(History1.from_dict(v['before']),v['action'],v['option_actual_steps'],v['option_ended'],None if v['after'] is None else History2.from_dict(v['after']),
            v['tail_action'],v['tail_actual_steps'],v['tail_success'],v['full_deadline_loss'])


def estimate(row,*,behavior1,target1,q1,behavior2=None,target2=None,q2=None):
    require(type(row) is LoggedTerminal,'one complete observed branch, not fabricated other tails')
    b1=probabilities(behavior1,3);p1=probabilities(target1,3);v1=finite_vector(q1,3);supported(p1,b1)
    i=ACTIONS.index(row.action);require(b1[i]>0,'chosen first action must have positive logged probability')
    rho1=p1[i]/b1[i];prediction1=sum(p*q for p,q in zip(p1,v1))
    terminal_loss=row.full_deadline_loss-row.before.completed_steps-row.option_actual_steps
    if row.option_ended!='NONE':
        require(all(v is None for v in (behavior2,target2,q2)),'terminal branch must not invent second policy/model')
        rho2=prediction2=None;post_dr=float(terminal_loss);tail_is=float(terminal_loss)
    else:
        b2=probabilities(behavior2,2);p2=probabilities(target2,2);v2=finite_vector(q2,2);supported(p2,b2)
        j=TAILS.index(row.tail_action);require(b2[j]>0,'chosen tail must have positive logged probability')
        rho2=p2[j]/b2[j];prediction2=sum(p*q for p,q in zip(p2,v2))
        post_dr=prediction2+rho2*(terminal_loss-v2[j]);tail_is=rho2*terminal_loss
    remaining=prediction1+rho1*(row.option_actual_steps+post_dr-v1[i])
    result={'first_importance_ratio':rho1,'second_importance_ratio':rho2,'first_value_prediction':prediction1,'post_value_prediction':prediction2,
        'post_DR':post_dr,'remaining_DR':remaining,'whole_DR':row.before.completed_steps+remaining,
        'whole_IS':row.before.completed_steps+rho1*(row.option_actual_steps+tail_is),'whole_regression':row.before.completed_steps+prediction1,
        'logged_whole_loss':row.full_deadline_loss,'observed_terminal_remaining_loss':terminal_loss,
        'estimate_clipped':False,'conditional_safety_or_task_improvement_established':False}
    require(all(v is None or isinstance(v,bool) or math.isfinite(v) for v in result.values()),'finite reference estimate')
    return result
