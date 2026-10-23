"""One-step finite-command reference; no plant inversion, fit or safety claim."""
from dataclasses import dataclass
import hashlib
import json
import re
import numpy as np
from src.probe.continuous import StepObservation
from src.probe.operator_identification import encode_controller
from src.probe.task_passive_pi_v1 import controller,vector,require
from src.probe.command_contrast_v1 import physical_candidates
from src.probe.linear_command_preflight_v1 import LinearCommandModel,make_query

WEIGHTS=(.1,1.,10.)
KINEMATIC_SCALE_M=.01
KINDS=('F20_RANK','KINEMATIC_RANK')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class RankQuery:
    task: str
    step: int
    current: StepObservation
    observation_steps: tuple
    observations: tuple
    raw_policy: tuple
    saved_controller: tuple
    weight: float

    def __post_init__(self):
        require(type(self.current) is StepObservation and not any((self.current.success,self.current.terminated,self.current.truncated)),'live public current observation')
        require(type(self.step) is int and 2<=self.step<500,'real two-displacement history and remaining step')
        stamps=tuple(self.observation_steps)
        require(stamps==tuple(range(self.step-2,self.step+1)) and all(type(i) is int for i in stamps),'causal consecutive observation stamps')
        require(len(self.observations)==3,'three real observations; never fabricate missing displacement')
        states=tuple(vector(o,39) for o in self.observations)
        require(states[-1]==self.current.observation,'history must end at exact current public observation')
        raw=vector(self.raw_policy,4)
        require(tuple(np.asarray(raw,np.float32).astype(float))==raw,'one original float32 policy query')
        require(len(self.saved_controller)==3,'saved public C8 controller')
        source,m,o=self.saved_controller;c=controller({'source':source,'matrix_xy':m,'offset':o})
        require(type(self.weight) in (float,int) and self.weight in WEIGHTS,'frozen dimensionless regularization')
        baseline=encode_controller({'source':c[0],'matrix_xy':[list(row) for row in c[1]],'offset':list(c[2])},raw)
        make_query(self.task,self.step,states,baseline)
        object.__setattr__(self,'observation_steps',stamps);object.__setattr__(self,'observations',states)
        object.__setattr__(self,'raw_policy',raw);object.__setattr__(self,'saved_controller',c);object.__setattr__(self,'weight',float(self.weight))

    @classmethod
    def create(cls,task,step,current,history,raw,base,weight):
        return cls(task,step,current,tuple(range(step-2,step+1)),history,tuple(np.asarray(raw,np.float32).astype(float)),controller(base),weight)

    def base_controller(self):
        source,m,o=self.saved_controller;return {'source':source,'matrix_xy':[list(r) for r in m],'offset':list(o)}

    def baseline(self):return tuple(encode_controller(self.base_controller(),self.raw_policy).astype(float))

    def to_dict(self):
        return {'schema':'RESPONSE_ACTION_RANK_QUERY_V1','task':self.task,'step':self.step,
            'current':{'observation':list(self.current.observation),'success':self.current.success,'terminated':self.current.terminated,'truncated':self.current.truncated},
            'observation_steps':list(self.observation_steps),'observations':[list(o) for o in self.observations],
            'raw_policy':list(self.raw_policy),'controller':self.base_controller(),'regularization_weight':self.weight}

    @classmethod
    def from_dict(cls,value):
        require(type(value) is dict and set(value)=={'schema','task','step','current','observation_steps','observations','raw_policy','controller','regularization_weight'}
            and value['schema']=='RESPONSE_ACTION_RANK_QUERY_V1','unknown/oracle/future query fields')
        c=value['current'];require(type(c) is dict and set(c)=={'observation','success','terminated','truncated'},'strict public current state')
        return cls(value['task'],value['step'],StepObservation(**c),value['observation_steps'],value['observations'],value['raw_policy'],controller(value['controller']),value['regularization_weight'])


@dataclass(frozen=True)
class RankPlan:
    query: RankQuery
    kind: str
    model_key: str
    model_sha256: object
    predictions: tuple

    def __post_init__(self):
        require(type(self.query) is RankQuery and self.kind in KINDS,'strict bounded-action reference')
        if self.kind=='F20_RANK':
            require(self.model_key==f'FEEDBACK8/{self.query.task}/LINEAR_F20' and type(self.model_sha256) is str
                and re.fullmatch('[0-9a-f]{64}',self.model_sha256) is not None,'frozen task/source F20 reference')
        else:require(self.model_key=='KINEMATIC_PROXY_0.01_M_PER_COMMAND' and self.model_sha256 is None,'untrained kinematic proxy descriptor')
        require(len(self.predictions)==5,'all five candidates retained, including duplicate clipped labels')
        object.__setattr__(self,'predictions',tuple(vector(v,2) for v in self.predictions))

    @classmethod
    def build(cls,query,kind,model=None):
        require(type(query) is RankQuery and kind in KINDS,'current causal query')
        candidates=physical_candidates(query.baseline())
        if kind=='F20_RANK':
            require(type(model) is tuple and len(model)==3,'frozen response model descriptor')
            key,sha,predictor=model
            require(type(predictor) is LinearCommandModel and predictor.task==query.task and predictor.feature=='F20','full conditional F20; no rescaling or inverse')
            legacy=make_query(query.task,query.step,query.observations,query.baseline())
            predictions=tuple(tuple(predictor.predict(legacy,u)) for _,u in candidates)
        else:
            require(model is None,'kinematic reference cannot receive a learned model')
            key,sha='KINEMATIC_PROXY_0.01_M_PER_COMMAND',None
            predictions=tuple(tuple(KINEMATIC_SCALE_M*np.asarray(u[:2])) for _,u in candidates)
        return cls(query,kind,key,sha,predictions)

    def numbers(self):
        q=self.query;base=np.asarray(q.baseline());candidates=physical_candidates(base)
        # This is a deliberately provisional mocap-shaped tracking reference,
        # not a measured nominal hand response or the final task target.
        target=KINEMATIC_SCALE_M*np.clip(np.asarray(q.raw_policy),-1,1)[:2]
        rows=[]
        for (name,u),pred in zip(candidates,self.predictions):
            error=np.asarray(pred)-target;delta=np.asarray(u[:2])-base[:2]
            tracking=float(error@error);regularization=float(q.weight*KINEMATIC_SCALE_M**2*(delta@delta))
            rows.append({'action_id':name,'sent_command':list(u),'predicted_displacement_xy_m':list(pred),
                'tracking_squared_m2':tracking,'regularization_m2':regularization,'score_m2':tracking+regularization})
        chosen=min(range(5),key=lambda i:(rows[i]['score_m2'],i))
        return {'reference_displacement_xy_m':target.tolist(),'baseline_command':base.tolist(),'candidates':rows,
            'selected_action_id':rows[chosen]['action_id'],'selected_command':rows[chosen]['sent_command'],
            'tie_rule':'FIRST_LABEL_BASELINE_X_PLUS_X_MINUS_Y_PLUS_Y_MINUS','mocap_shaped_reference_is_physical_hand_response':False}

    def to_dict(self):
        return {'schema':'RESPONSE_ACTION_RANK_SAVED_PLAN_V1','query':self.query.to_dict(),'kind':self.kind,
            'model_key':self.model_key,'model_sha256':self.model_sha256,'predictions_xy_m':[list(v) for v in self.predictions],
            'numbers':self.numbers(),'new_model_fits':0,'physical_inverse_qualified':False,'task_benefit_established':False,'safety_guarantee':False}

    @property
    def sha256(self):return digest(self.to_dict())

    @classmethod
    def from_dict(cls,value,model=None):
        require(type(value) is dict and set(value)=={'schema','query','kind','model_key','model_sha256','predictions_xy_m','numbers','new_model_fits',
            'physical_inverse_qualified','task_benefit_established','safety_guarantee'},'unknown saved-plan fields')
        query=RankQuery.from_dict(value['query']);expected=cls.build(query,value['kind'],model)
        require(digest(value)==expected.sha256,'saved model predictions/score/choice or claims changed')
        return expected


class RankConsumer:
    def __init__(self,plan):require(type(plan) is RankPlan,'saved immutable rank plan');self.plan=plan;self.used=False
    def consume(self,current,remaining_steps):
        require(not self.used and type(current) is RankQuery and current==self.plan.query,'reused or stale rank plan')
        require(type(remaining_steps) is int and 1<=remaining_steps<=500-current.step,'actual step budget')
        self.used=True;n=self.plan.numbers()
        return {'at_calls':current.step,'plan_sha256':self.plan.sha256,'action_id':n['selected_action_id'],'command':n['selected_command']}
