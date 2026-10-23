"""Fixed task controls and four task-time PI references; visible callbacks only."""
from copy import deepcopy
from dataclasses import dataclass,asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.cold_start_response import ColdPrefix,validate_model,infer_operator
from src.probe.continuous import StepObservation
from src.probe.short_joint_reference_v1 import infer_four
from src.probe.observable_history_behavior_v1 import PROBE
from src.probe.operator_identification import identity_controller,affine_controller,encode_controller
from src.probe.physical_reprobe_v1 import Start,StepReceipt
from src.probe.local_reprobe_v1 import selected_anchor,anchor_ready,control_update,relocation_evidence
from src.probe.task_passive_pi_v1 import PIQuery,PIPlan,PlanConsumer,TIME_CONSTANTS,digest,require,GAINS

CONTROLS=('NO_PROBE','DIRECT_C8','MOVE_KEEP_C8','MOVE_INTEGRAL')
PI_STYLES=('RAW_TASK_PI','DIRECT_TASK_PI','MOVE_KEEP_TASK_PI','MOVE_INTEGRAL_TASK_PI')
STYLES=CONTROLS+PI_STYLES


@dataclass(frozen=True)
class Program:
    style: str
    time_constant_s: object=None

    def __post_init__(self):
        require(self.style in STYLES,'fixed public program')
        if self.style in CONTROLS: require(self.time_constant_s is None,'non-PI program has no tuned time constant')
        else: require(type(self.time_constant_s) in (int,float) and self.time_constant_s in TIME_CONSTANTS,'registered PI time constant')

    @property
    def uses_c8(self): return self.style not in ('NO_PROBE','RAW_TASK_PI')

    @property
    def moves(self): return self.style.startswith('MOVE_')

    @property
    def uses_pi(self): return self.style in PI_STYLES

    def to_dict(self): return {'schema':'TASK_PASSIVE_PROGRAM_V1','style':self.style,'time_constant_s':self.time_constant_s}

    @classmethod
    def from_dict(cls,value):
        require(type(value) is dict and set(value)=={'schema','style','time_constant_s'} and value['schema']=='TASK_PASSIVE_PROGRAM_V1','strict public program')
        return cls(value['style'],value['time_constant_s'])


def ended(value): return value.success or value.terminated or value.truncated


def run(task,initial,nominal,boundary,program,policy,step,emit):
    require(task in GAINS and type(initial) is StepObservation and len(initial.observation)==39 and not ended(initial),'live visible initial')
    require(type(program) is Program and boundary in (16,32,64) and all(callable(f) for f in (policy,step,emit)),'frozen program/boundary/callbacks')
    if program.uses_c8:
        validate_model(nominal); require(nominal['task']==task,'matching frozen nominal C8 model')
    else: require(nominal is None,'raw controls must not receive or pay for a nominal model')
    events=[]; current=initial; calls=queries=fit_attempts=fit_results=nfev=move_count=task_steps=pi_count=0
    base=identity_controller() if not program.uses_c8 else None
    prefix_commands=[]; prefix_observations=[]; reason=None; at_anchor=None; task_integral=[0.,0.]

    def save(kind,payload):
        expected=normalize(payload); ack=emit(kind,deepcopy(expected))
        require(type(ack) is dict and set(ack)==set(expected)|{'sequence','saved_ns'} and ack['sequence']==len(events)
            and digest({k:ack[k] for k in expected})==digest(expected),'durable current acknowledgement differs')
        events.append({'kind':kind,'payload':deepcopy(ack)}); return ack

    def act(command,phase,decision,raw=None,pi_sha=None):
        nonlocal current,calls
        require(not ended(current) and calls<500,'ended or exhausted program')
        sent=np.asarray(command,np.float32); require(sent.shape==(4,) and np.isfinite(sent).all() and np.all(abs(sent)<=1),'bounded actual command')
        request=save('COMMAND',{'at_calls':calls,'phase':phase,'decision_sequence':decision['sequence'],
            'before':asdict(current),'command':sent.tolist(),'raw_policy':raw,'pi_plan_sha256':pi_sha})
        supplied=deepcopy(request); receipt=step(supplied)
        require(digest(supplied)==digest(request) and type(receipt) is StepReceipt and receipt.completed_steps==calls+1,'actual consecutive physical receipt required')
        current,calls=receipt.current,receipt.completed_steps
        save('STEP_RESULT',{'at_calls':calls,'command_sequence':request['sequence'],'after':asdict(current)})

    def action(phase,decision,with_pi=False):
        nonlocal queries,task_steps,task_integral,pi_count
        raw=np.asarray(policy(np.array(current.observation,dtype=float,copy=True)),np.float32).tolist(); queries+=1
        if with_pi:
            query=PIQuery.create(task,calls,current,raw,base,task_integral,program.time_constant_s)
            proposed=PIPlan(query); declared=save('PI_PLAN',{'at_calls':calls,'plan':proposed.to_dict(),'plan_sha256':proposed.sha256})
            # Read the durable acknowledged plan back, rather than an unsaved
            # local value. This also rejects changed arithmetic or extra fields.
            saved=PIPlan.from_dict(declared['plan']); require(saved.sha256==declared['plan_sha256'],'saved plan digest changed')
            consumed=PlanConsumer(saved).consume(query,500-calls); before=list(task_integral)
            act(consumed['command'],phase,declared,raw,consumed['plan_sha256'])
            task_integral=saved.numbers()['integral_after_receipt']; pi_count+=1
            save('PI_STATE_COMMIT',{'at_calls':calls,'plan_sequence':declared['sequence'],'plan_sha256':saved.sha256,
                'integral_before':before,'integral_after':task_integral})
        else: act(encode_controller(base,raw),'APPROACH' if phase=='APPROACH' else phase,decision,raw)
        task_steps+=1

    save('PROGRAM',{'at_calls':0,'task':task,'initial':asdict(initial),'program':program.to_dict(),'boundary':boundary,
        'maximum_total_steps':500,'maximum_movement_steps':64,'fixed_policy_queries_per_task_step':1,
        'nominal_sha256':None if nominal is None else digest(nominal),'new_response_predictor_training':0,'new_api_calls':0,
        'safety_guarantee':False})
    if program.uses_c8:
        for length in (4,8):
            selected=save('CHOICE',{'at_calls':calls,'action':'PROBE_FOUR','commands':PROBE})
            for u in PROBE:
                if ended(current): break
                act(u,'FIXED_PROBE',selected); prefix_commands.append(u); prefix_observations.append(current.observation)
            if ended(current): break
            prefix=ColdPrefix(task,initial.observation,prefix_commands,prefix_observations,True)
            intent=save('FIT_INTENT',{'at_calls':calls,'prefix':asdict(prefix),'prefix_sha256':digest(asdict(prefix))}); fit_attempts+=1
            fit=infer_four(nominal,prefix) if length==4 else infer_operator(nominal,prefix)
            fitted=save('FIT_RESULT',{'at_calls':calls,'intent_sequence':intent['sequence'],'fit':fit}); fit_results+=1; nfev+=int(fit.get('nfev',0))
            if not fitted['fit']['valid']: reason='INVALID_FOUR' if length==4 else 'INVALID_EIGHT'; break
            chosen=save('CHOICE',{'at_calls':calls,'action':'SAVE_C4_ONLY' if length==4 else 'RUN_C8',
                'fit_sequence':fitted['sequence'],'controller':affine_controller(fitted['fit']['matrix_xy'],fitted['fit']['bias_xy'])})
            if length==8: base=deepcopy(chosen['controller'])
    if base is not None and not ended(current):
        entry=save('TASK_ENTRY',{'at_calls':calls,'program':program.to_dict(),'controller':base,'integral_initial':[0.,0.],
            'task_pi_start':'AFTER_MOVEMENT' if program.moves and program.uses_pi else 'CURRENT' if program.uses_pi else 'DISABLED'})
        if program.moves:
            # Every MOVE program keeps C8 during approach and executes the same
            # old LOCAL_PID movement. New task PI begins only afterwards.
            while calls<boundary and not ended(current): action('APPROACH',entry)
            if not ended(current):
                require(500-calls>=164,'full old movement and task reserve')
                start=Start(task,calls,current,base['matrix_xy'],base['offset'][:2]); anchor=selected_anchor(start,'LOCAL_PID')
                movement=save('MOVE_ENTRY',{'at_calls':calls,'before':asdict(current),'controller':base,'anchor':list(anchor)})
                observations=[current.observation]; relocation_integral=[0.,0.]; lifted=current.observation[2]>=anchor[2]-.015
                while not ended(current) and move_count<64 and not anchor_ready(observations,anchor):
                    updated,u=control_update(start,observations,lifted,relocation_integral,'LOCAL_PID')
                    save('MOVE_INTEGRAL_UPDATE',{'at_calls':calls,'integral_before':relocation_integral,'integral_after':updated})
                    act(u,'REPOSITION',movement); move_count+=1; observations.append(current.observation); relocation_integral=updated
                    lifted=lifted or current.observation[2]>=anchor[2]-.015
                at_anchor=anchor_ready(observations,anchor)
                evidence=save('RELOCATION_EVIDENCE',{'at_calls':calls,**relocation_evidence(start,relocation_integral,at_anchor)})
                if program.style in ('MOVE_INTEGRAL','MOVE_INTEGRAL_TASK_PI'):
                    base={**deepcopy(evidence['controller']),'source':'ESTIMATED_AFFINE'}
                entry=save('POST_MOVE_TASK_ENTRY',{'at_calls':calls,'before':asdict(current),'controller':base,'integral_initial':[0.,0.],
                    'program':program.to_dict(),'movement_steps':move_count,'anchor_reached':at_anchor})
        while not ended(current) and calls<500: action('TASK',entry,program.uses_pi)
    if reason is None: reason='SUCCESS' if current.success else 'ENVIRONMENT_ENDED' if current.terminated or current.truncated else 'DEADLINE'
    outcome={'success':current.success,'terminated':current.terminated,'truncated':current.truncated,'total_steps':calls,
        'deadline_loss':calls if current.success else 500,'stop_reason':reason,'policy_queries':queries,'task_steps':task_steps,
        'movement_steps':move_count,'anchor_reached':at_anchor,'pi_steps':pi_count,'integral_final':task_integral,
        'c4_c8_fit_attempts':fit_attempts,'c4_c8_fit_results':fit_results,'c4_c8_optimizer_nfev':nfev,
        'new_response_predictor_training':0,'new_api_calls':0,'safety_guarantee':False}
    save('OUTCOME',{'at_calls':calls,'outcome':outcome,'final':asdict(current)})
    return {'events':events,'outcome':outcome}
