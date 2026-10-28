"""Fixed-reference actual deployment, not a new acquisition algorithm."""
from copy import deepcopy
from dataclasses import asdict,replace
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.occam_performance_core_v1 import require,digest,RATES
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.physical_reprobe_v1 import Start,StepReceipt
from src.probe import acquisition_reference_operation_v1 as macro
from src.probe import occam_window_cost_v1 as cost
from src.probe import task_passive_program_v1 as legacy

ACQUISITIONS=('CONTINUE','VALIDATE8','MOVE_MEASURE')
CONTROLLERS=('PI_0125','PI_0500','PI_2000','PI_8000','META_ADAPT','META_FROZEN','ERM_ADAPT','ERM_FROZEN')
GLOBAL_FIXED=('GLOBAL_PI_0125','GLOBAL_PI_2000','GLOBAL_PI_8000')
PROGRAM_ALIASES={'GLOBAL_PI_0500':'PI_0500__CONTINUE'}
PROGRAMS=tuple(c+'__'+a for a in ACQUISITIONS for c in CONTROLLERS)+GLOBAL_FIXED+('DIRECT_C8','MOVE_INTEGRAL')


def program_spec(program):
    require(type(program) is str and program in (*PROGRAMS,*PROGRAM_ALIASES),'registered complete program or exact alias')
    program=PROGRAM_ALIASES.get(program,program)
    if program in GLOBAL_FIXED:
        rate={'GLOBAL_PI_0125':.125,'GLOBAL_PI_2000':2.,'GLOBAL_PI_8000':8.}[program]
        return dict(kind='FIXED_GLOBAL',action='CONTINUE',bank=None,adapt=False,rate=rate,prefix_rate=rate)
    if program in ('DIRECT_C8','MOVE_INTEGRAL'):return dict(kind='LEGACY',action=program,bank=None,adapt=False,rate=None)
    name,action=program.split('__')
    if name.startswith('PI_'):
        return dict(kind='FIXED',action=action,bank=None,adapt=False,rate=RATES[CONTROLLERS.index(name)])
    return dict(kind='TRAINED',action=action,bank='META_FINAL' if name.startswith('META_') else 'MATCHED_ERM_FINAL',adapt=name.endswith('_ADAPT'),rate=None)


def run_program(task,initial,boundary,program,nominal,provider,policy,step,emit):
    settings=program_spec(program)
    if settings['kind']=='LEGACY':
        require(provider is None and nominal is not None,'original C8 references retain their original data and fit')
        return legacy.run(task,initial,nominal,boundary,legacy.Program(program),policy,step,emit)
    require(nominal is None and provider is not None,'public-history provider receives no nominal response prior')
    return run(task,initial,boundary,settings['action'],provider,policy,step,emit,program_name=program,prefix_rate=settings.get('prefix_rate',.5))



def run(task,initial,boundary,action,provider,policy,step,emit,*,window_steps=16,program_name=None,prefix_rate=.5):
    require(boundary in (16,32,64) and action in ('CONTINUE','VALIDATE8','MOVE_MEASURE')
        and type(window_steps) is int and 1<=window_steps<=500,'registered factual acquisition and window')
    require(not any((initial.success,initial.terminated,initial.truncated)),'live controlled initial')
    require(prefix_rate in RATES,'registered fixed prefix rate')
    machine=TaskMemoryMachine(replace(TaskMemory.initial(task,initial),time_constant_s=prefix_rate));events=[];history=[];segments=[];queries=0;windows=0;option=None
    def save(kind,payload):
        p=normalize(payload);ack=emit(kind,deepcopy(p))
        require(type(ack) is dict and set(ack)==set(p)|{'sequence','saved_ns'} and ack['sequence']==len(events)
            and digest({k:ack[k] for k in p})==digest(p),'durable unchanged acknowledgement')
        events.append(dict(kind=kind,payload=deepcopy(ack)));return ack
    def live():return machine.memory.completed_steps<500 and not cost.ended(asdict(machine.memory.current))
    def physical(saved):
        copied=deepcopy(saved);r=step(copied)
        require(type(r) is StepReceipt and digest(copied)==digest(saved) and r.completed_steps==len(history)+1,'actual consecutive unchanged receipt')
        history.append(dict(at_calls=saved['at_calls'],before=saved['before'],command=saved['command'],after=normalize(asdict(r.current))))
        return r
    def task_step(phase):
        nonlocal queries
        m=machine.memory;raw=np.asarray(policy(np.array(m.current.observation,copy=True)),np.float32).tolist();queries+=1
        plan=save('PI_PLAN',dict(at_calls=m.completed_steps,saved_plan=machine.plan(raw)))
        command=save('COMMAND',dict(at_calls=m.completed_steps,phase=phase,before=asdict(m.current),raw_policy=raw,
            decision_sequence=plan['sequence'],command=plan['saved_plan']['pi_plan']['numbers']['sent_command']))
        machine.commit(plan['saved_plan'],physical(command))
        save('STEP_RESULT',dict(at_calls=machine.memory.completed_steps,command_sequence=command['sequence'],after=asdict(machine.memory.current)))
        save('TASK_MEMORY_COMMIT',dict(at_calls=machine.memory.completed_steps,memory=machine.memory.to_dict()))
    def measure(start_at,start,planned,kind,parent=None):
        m=cost.measure(task,start_at,start,history[start_at:],planned);segments.append(m)
        save(kind,dict(at_calls=machine.memory.completed_steps,measurement=m,parent_sequence=parent));return m
    save('PROGRAM',dict(at_calls=0,task=task,boundary=boundary,acquisition_action=action,window_steps=window_steps,
        bank_sha256=provider.bank_sha256,program=program_name,prefix_time_constant_s=prefix_rate,scope='STANDARD_REFERENCE_OWN_HISTORY_QUALIFICATION_NOT_NEW_ACQUISITION',online_LLM_API_calls=0))
    while machine.memory.completed_steps<boundary and live():task_step('PREFIX_TASK')
    measure(0,normalize(asdict(initial)),boundary,'PREFIX_COST')
    if live():
        before=machine.memory;n=before.completed_steps
        save('ACQUISITION_CHOICE',dict(at_calls=n,action=action,before_memory=before.to_dict(),assignment='FROZEN_FACTUAL_ARM'))
        if action=='VALIDATE8':
            for _ in range(8):
                if not live():break
                task_step('VALIDATION_TASK')
            option=dict(reason='NORMAL_TASK_CONTINUATION',reposition_steps=0,probe_steps=machine.memory.completed_steps-n)
        elif action=='MOVE_MEASURE':
            token=machine.suspend();save('TASK_MEMORY_SUSPEND',dict(at_calls=n,token=token,memory=before.to_dict()));receipts=[]
            def moved(command):
                r=physical(command);receipts.append(r);return r
            option=macro.acquire(Start(task,n,before.current,before.saved_controller[1],before.saved_controller[2][:2]),moved,save,method='LOCAL_PID')
            machine.resume(token,receipts)
        else:option=dict(reason='NO_ACQUISITION',reposition_steps=0,probe_steps=0)
        returned=machine.memory
        save('TASK_MEMORY_RETURN',dict(at_calls=returned.completed_steps,memory=returned.to_dict(),reason=option['reason']))
        count=returned.completed_steps-n
        if count:measure(n,normalize(asdict(before.current)),count,'ACQUISITION_COST')
    while live():
        m=machine.memory;n=m.completed_steps;planned=min(window_steps,500-n)
        query=dict(schema='OCCAM_PUBLIC_HISTORY_V1',task=task,completed_steps=n,initial=normalize(asdict(initial)),
            history=deepcopy(history),integral_xy=list(m.integral_xy),candidate_time_constant_s=RATES[0],evaluation_steps=planned)
        declared_input=save('WINDOW_QUERY',dict(at_calls=n,value=query))
        decision=save('WINDOW_DECISION',dict(at_calls=n,input_sequence=declared_input['sequence'],declaration=provider.declare(query)))
        d=decision['declaration'];require(d['at_calls']==n and d['evaluation_steps']==planned and d['public_query_sha256']==digest(query),'stale/future performance decision')
        rate=save('RATE_PLAN',dict(at_calls=n,rate=d['selected_rate'],memory_mode='CARRY',before_memory=m.to_dict(),decision_sequence=decision['sequence']))
        receipt=machine.set_rate(rate['rate'],memory_mode='CARRY')
        save('RATE_COMMIT',dict(at_calls=n,plan_sequence=rate['sequence'],receipt=receipt,memory=machine.memory.to_dict()))
        for _ in range(planned):
            if not live():break
            task_step('TAIL_TASK')
        measured=measure(n,normalize(asdict(m.current)),planned,'WINDOW_RESULT',decision['sequence'])
        feedback=provider.feedback(d,measured,asdict(machine.memory.current));windows+=1
        save('WINDOW_FEEDBACK',dict(at_calls=machine.memory.completed_steps,decision_sequence=decision['sequence'],feedback=feedback))
    m=machine.memory;account=cost.total_cost(task,normalize(asdict(initial)),segments,m.completed_steps,m.current.success)
    outcome=dict(**account,success=m.current.success,terminated=m.current.terminated,truncated=m.current.truncated,total_steps=m.completed_steps,
        policy_queries=queries,performance_windows=windows,full_feedback_windows=0 if provider.session is None else provider.session.version,
        movement_steps=0 if option is None else option['reposition_steps'],measurement_steps=0 if option is None else option['probe_steps'],
        stop_reason='SUCCESS' if m.current.success else 'ENVIRONMENT_ENDED' if cost.ended(asdict(m.current)) else 'DEADLINE',final_memory=m.to_dict(),
        new_neural_or_response_training=0,online_LLM_API_calls=0,untrained_software_fixture=False,reference_qualification=True)
    save('OUTCOME',dict(at_calls=m.completed_steps,outcome=outcome,final=asdict(m.current)))
    return dict(outcome=outcome,events=events)
