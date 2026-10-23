"""Eight unchanged task references and a separately versioned finite-command ranker."""
from copy import deepcopy
from dataclasses import dataclass,asdict
import numpy as np
from src.probe import task_passive_program_v1 as old
from src.probe.response_action_rank_v1 import RankQuery,RankPlan,RankConsumer,KINDS,WEIGHTS,digest,require
from src.analysis.capsule_record_json_v2 import normalize

CONTROLS=old.CONTROLS;PI_STYLES=old.PI_STYLES
LOCKED_PI={'RAW_TASK_PI':.5,'DIRECT_TASK_PI':.5,'MOVE_KEEP_TASK_PI':.5,'MOVE_INTEGRAL_TASK_PI':2.}


@dataclass(frozen=True)
class Program:
    style: str
    time_constant_s: object=None
    regularization_weight: object=None
    def __post_init__(self):
        if self.style in KINDS:
            require(self.time_constant_s is None and type(self.regularization_weight) in (int,float) and self.regularization_weight in WEIGHTS,'registered rank weight')
            if self.style=='KINEMATIC_RANK':require(self.regularization_weight==1.,'fixed kinematic comparator weight')
        else:
            old.Program(self.style,self.time_constant_s);require(self.regularization_weight is None,'old references have no rank weight')
            if self.style in PI_STYLES:require(self.time_constant_s==LOCKED_PI[self.style],'all four old locked PI references')
    @property
    def uses_c8(self):return self.style not in ('NO_PROBE','RAW_TASK_PI')
    @property
    def uses_pi(self):return self.style in PI_STYLES
    @property
    def moves(self):return self.style.startswith('MOVE_')
    @property
    def uses_rank(self):return self.style in KINDS
    def to_dict(self):
        return {'schema':'RESPONSE_ACTION_RANK_PROGRAM_V1','style':self.style,'regularization_weight':float(self.regularization_weight)} if self.uses_rank else old.Program(self.style,self.time_constant_s).to_dict()


def from_spec(spec):return Program(spec['style'],spec['time_constant_s'],spec['regularization_weight'])


def run(task,initial,nominal,boundary,program,policy,step,emit,model=None):
    require(type(program) is Program,'versioned reference program')
    if not program.uses_rank:
        require(model is None,'unchanged baselines do not receive a learned response predictor')
        result=old.run(task,initial,nominal,boundary,old.Program(program.style,program.time_constant_s),policy,step,emit)
        result['outcome'].update(rank_steps=0,response_model_forward_evaluations=0,kinematic_proxy_evaluations=0)
        return result
    require(task in old.GAINS and type(initial) is old.StepObservation and not old.ended(initial),'live public initial state')
    old.validate_model(nominal);require(nominal['task']==task and boundary in (16,32,64),'matching frozen nominal C8 source and boundary')
    current=initial;history=[initial.observation];calls=queries=fits=fit_results=nfev=rank_steps=0
    prefix_commands=[];prefix_observations=[];events=[];base=None;reason=None
    def save(kind,payload):
        expected=normalize(payload);ack=emit(kind,deepcopy(expected))
        require(type(ack) is dict and set(ack)==set(expected)|{'sequence','saved_ns'} and ack['sequence']==len(events)
            and digest({k:ack[k] for k in expected})==digest(expected),'durable public acknowledgement differs')
        events.append({'kind':kind,'payload':deepcopy(ack)});return ack
    def act(command,phase,decision,raw=None,rank_sha=None):
        nonlocal current,calls
        require(not old.ended(current) and calls<500,'live budget required')
        sent=np.asarray(command,np.float32);require(sent.shape==(4,) and np.isfinite(sent).all() and np.all(abs(sent)<=1),'bounded sent command')
        request=save('COMMAND',{'at_calls':calls,'phase':phase,'decision_sequence':decision['sequence'],'before':asdict(current),
            'command':sent.tolist(),'raw_policy':raw,'pi_plan_sha256':None,'rank_plan_sha256':rank_sha})
        copy=deepcopy(request);receipt=step(copy)
        require(digest(copy)==digest(request) and type(receipt) is old.StepReceipt and receipt.completed_steps==calls+1,'actual continuous receipt')
        current,calls=receipt.current,receipt.completed_steps;history.append(current.observation)
        save('STEP_RESULT',{'at_calls':calls,'command_sequence':request['sequence'],'after':asdict(current)})
    save('PROGRAM',{'at_calls':0,'task':task,'initial':asdict(initial),'program':program.to_dict(),'boundary':boundary,
        'maximum_total_steps':500,'fixed_policy_queries_per_task_step':1,'nominal_sha256':digest(nominal),
        'new_response_predictor_training':0,'new_api_calls':0,'safety_guarantee':False})
    for length in (4,8):
        selected=save('CHOICE',{'at_calls':calls,'action':'PROBE_FOUR','commands':old.PROBE})
        for u in old.PROBE:
            if old.ended(current):break
            act(u,'FIXED_PROBE',selected);prefix_commands.append(u);prefix_observations.append(current.observation)
        if old.ended(current):break
        prefix=old.ColdPrefix(task,initial.observation,prefix_commands,prefix_observations,True)
        intent=save('FIT_INTENT',{'at_calls':calls,'prefix':asdict(prefix),'prefix_sha256':digest(asdict(prefix))});fits+=1
        fit=old.infer_four(nominal,prefix) if length==4 else old.infer_operator(nominal,prefix)
        fitted=save('FIT_RESULT',{'at_calls':calls,'intent_sequence':intent['sequence'],'fit':fit});fit_results+=1;nfev+=int(fit.get('nfev',0))
        if not fitted['fit']['valid']:reason='INVALID_FOUR' if length==4 else 'INVALID_EIGHT';break
        chosen=save('CHOICE',{'at_calls':calls,'action':'SAVE_C4_ONLY' if length==4 else 'RUN_C8',
            'fit_sequence':fitted['sequence'],'controller':old.affine_controller(fitted['fit']['matrix_xy'],fitted['fit']['bias_xy'])})
        if length==8:base=deepcopy(chosen['controller'])
    if base is not None and not old.ended(current):
        save('RANK_TASK_ENTRY',{'at_calls':calls,'controller':base,'program':program.to_dict(),'model_key':None if model is None else model[0],
            'model_sha256':None if model is None else model[1],'no_history_reset_at_hidden_change':True})
        while calls<500 and not old.ended(current):
            raw=np.asarray(policy(np.array(current.observation,copy=True)),np.float32).tolist();queries+=1
            query=RankQuery.create(task,calls,current,history[-3:],raw,base,program.regularization_weight)
            intent=save('RANK_INTENT',{'at_calls':calls,'query':query.to_dict(),'kind':program.style,'forward_evaluations_planned':10 if model is not None else 0,
                'kinematic_evaluations_planned':10 if model is None else 0})
            proposed=RankPlan.build(query,program.style,model)
            declared=save('RANK_PLAN',{'at_calls':calls,'intent_sequence':intent['sequence'],'plan':proposed.to_dict(),'plan_sha256':proposed.sha256})
            saved=RankPlan.from_dict(declared['plan'],model);require(saved.sha256==declared['plan_sha256'],'saved plan changed')
            save('RANK_VALIDATED',{'at_calls':calls,'plan_sequence':declared['sequence'],'plan_sha256':saved.sha256,
                'response_model_forward_evaluations':10 if model is not None else 0,'kinematic_proxy_evaluations':10 if model is None else 0})
            consumed=RankConsumer(saved).consume(query,500-calls)
            act(consumed['command'],'TASK',declared,raw,consumed['plan_sha256']);rank_steps+=1
    if reason is None:reason='SUCCESS' if current.success else 'ENVIRONMENT_ENDED' if current.terminated or current.truncated else 'DEADLINE'
    outcome={'success':current.success,'terminated':current.terminated,'truncated':current.truncated,'total_steps':calls,
        'deadline_loss':calls if current.success else 500,'stop_reason':reason,'policy_queries':queries,'task_steps':queries,'movement_steps':0,
        'anchor_reached':None,'pi_steps':0,'integral_final':[0.,0.],'c4_c8_fit_attempts':fits,'c4_c8_fit_results':fit_results,'c4_c8_optimizer_nfev':nfev,
        'new_response_predictor_training':0,'new_api_calls':0,'safety_guarantee':False,'rank_steps':rank_steps,
        'response_model_forward_evaluations':10*rank_steps if model is not None else 0,'kinematic_proxy_evaluations':10*rank_steps if model is None else 0}
    save('OUTCOME',{'at_calls':calls,'outcome':outcome,'final':asdict(current)});return {'events':events,'outcome':outcome}
