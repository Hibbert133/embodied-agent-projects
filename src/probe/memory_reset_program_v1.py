"""Standard memory-only versus physical acquisition; no learned selector."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.task_passive_pi_v1 import require,digest
from src.probe.physical_reprobe_v1 import Start,StepReceipt
from src.probe import acquisition_reference_operation_v1 as macro
from src.probe import relocation_reference_update_v1 as reference
from src.probe import task_passive_program_v1 as legacy
from src.probe import controller_memory_transition_v1 as transition

PROGRAMS=('RAW_CONTINUE','RAW_NOOP','RAW_RESET_I','DIRECT_C8','MOVE_INTEGRAL','LOCAL_PID_KEEP','LOCAL_PID_RESET_I',
    'LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_CARRY','LOCAL_PID_REFERENCE_RESET_NO_PROBE')
NATIVE_PROGRAMS=('RAW_CONTINUE','RAW_NOOP','RAW_RESET_I','LOCAL_PID_KEEP','LOCAL_PID_RESET_I')
FIRST_ACTIONS=('CONTINUE','LOCAL_PID')
TAIL_ACTIONS=('KEEP','NOOP','RESET_TASK_I','REFERENCE_RESET','REFERENCE_CARRY')


def is_legacy(program):return program in ('DIRECT_C8','MOVE_INTEGRAL')
def method(program):return 'LOCAL_PID' if program.startswith('LOCAL_PID_') else None

def first_action(program):return 'CONTINUE' if program.startswith('RAW_') else method(program)
def mode(program):return 'RESET' if '_REFERENCE_RESET' in program else 'CARRY' if '_REFERENCE_CARRY' in program else None
def ended(current):return any((current.success,current.terminated,current.truncated))


def run(task,initial,boundary,program,nominal,policy,step,emit):
    require(program in PROGRAMS and boundary in (16,32,64),'registered fixed program and boundary')
    if is_legacy(program):
        result=legacy.run(task,initial,nominal,boundary,legacy.Program(program),policy,step,emit);o=result['outcome']
        result['outcome']={**o,'complete_warm_window':False,'warm_probe_steps':0,'option_reason':'LEGACY_NO_WARM_MEASUREMENT',
            'reference_update_applied':False,'reference_update_mode':None,'reference_admission_reason':'LEGACY_CONTROL_NOT_RAW_REFERENCE_ARM',
            'measurement_anchor':None,'acquisition_entered':any(e['kind']=='MOVE_ENTRY' for e in result['events']),
            'memory_transition_applied':False,'memory_transition_mode':None,'memory_nonzero_changed':None,'memory_transition_reason':'LEGACY_REFERENCE_ARM'}
        return result
    require(nominal is None,'RAW procedures receive no nominal model');require(not ended(initial),'live initial state')
    machine=TaskMemoryMachine(TaskMemory.initial(task,initial));events=[];queries=0;option=None;applied=False
    admission='EARLY_END_BEFORE_REFERENCE' if mode(program) else 'NO_REFERENCE_PROGRAM'
    memory_applied=False;memory_mode=None;memory_nonzero=None;memory_reason='EARLY_END_BEFORE_BOUNDARY' if program in ('RAW_NOOP','RAW_RESET_I','LOCAL_PID_RESET_I') else 'NOT_ASSIGNED'
    def save(kind,payload):
        p=normalize(payload);ack=emit(kind,deepcopy(p));require(type(ack) is dict and set(ack)==set(p)|{'sequence','saved_ns'}
            and ack['sequence']==len(events) and digest({k:ack[k] for k in p})==digest(p),'changed or unordered public acknowledgement')
        events.append({'kind':kind,'payload':deepcopy(ack)});return ack
    def task_step(phase):
        nonlocal queries
        m=machine.memory;require(not ended(m.current) and m.completed_steps<500,'ended task cannot step')
        raw=np.asarray(policy(np.array(m.current.observation,copy=True)),np.float32).tolist();queries+=1
        proposed=machine.plan(raw);declared=save('PI_PLAN',{'at_calls':m.completed_steps,'saved_plan':proposed})
        request=save('COMMAND',{'at_calls':m.completed_steps,'phase':phase,'decision_sequence':declared['sequence'],
            'before':asdict(m.current),'command':declared['saved_plan']['pi_plan']['numbers']['sent_command'],'raw_policy':raw})
        sent=deepcopy(request);receipt=step(sent);require(digest(sent)==digest(request),'changed actual command')
        machine.commit(declared['saved_plan'],receipt)
        save('STEP_RESULT',{'at_calls':machine.memory.completed_steps,'command_sequence':request['sequence'],'after':asdict(machine.memory.current)})
        save('TASK_MEMORY_COMMIT',{'at_calls':machine.memory.completed_steps,'memory':machine.memory.to_dict()})
    save('PROGRAM',{'at_calls':0,'task':task,'program':program,'boundary':boundary,'initial':asdict(initial),
        'source_policy':'RAW_TASK_PI_T0.5','warm_parameter_identification_qualified':False,'new_model_training':0,'online_LLM_API_calls':0})
    while machine.memory.completed_steps<boundary and not ended(machine.memory.current):task_step('PREFIX_TASK')
    if not ended(machine.memory.current):
        m=machine.memory;first=first_action(program)
        save('ACQUISITION_CHOICE',{'at_calls':m.completed_steps,'before_memory':m.to_dict(),'action':first,
            'behavior_probabilities':[float(a==first) for a in FIRST_ACTIONS],'assignment':'FIXED_PROGRAM_NOT_RANDOM_POLICY_VALUE_DATA'})
        if first!='CONTINUE':
            token=machine.suspend();save('TASK_MEMORY_SUSPEND',{'at_calls':m.completed_steps,'token':token,'memory':m.to_dict()});receipts=[]
            def moved(request):
                r=step(request);require(type(r) is StepReceipt,'actual acquisition receipt');receipts.append(r);return r
            option=macro.acquire(Start(task,m.completed_steps,m.current,m.saved_controller[1],m.saved_controller[2][:2]),moved,save,method=first,
                measure=not program.endswith('_NO_PROBE'))
            machine.resume(token,receipts);require(digest(asdict(machine.memory.current))==digest(option['final']),'actual returned state differs')
        else:option={'reason':'ZERO_ACQUISITION_CONTINUE','new_steps':0,'reposition_steps':0,'probe_steps':0,'window':None,'measurement_anchor':None}
        returned=save('TASK_MEMORY_RETURN',{'at_calls':machine.memory.completed_steps,'memory':machine.memory.to_dict(),'first_action':first,
            'option_reason':option['reason'],'new_steps':option['new_steps'],'measurement_model_qualified':False})
        if ended(machine.memory.current) and program=='LOCAL_PID_RESET_I':memory_reason='EARLY_END_DURING_ACQUISITION'
        if not ended(machine.memory.current):
            wanted=mode(program);tail='NOOP' if program=='RAW_NOOP' else 'RESET_TASK_I' if program in ('RAW_RESET_I','LOCAL_PID_RESET_I') else 'KEEP' if wanted is None else 'REFERENCE_'+wanted
            complete=option['window'] is not None or (program.endswith('_NO_PROBE') and option['reason']=='RELOCATION_COMPLETE_UNQUALIFIED')
            admission='NO_REFERENCE_PROGRAM' if wanted is None else 'INCOMPLETE_ACQUISITION_KEEP' if not complete else 'COMPLETE_RELOCATION_NO_PROBE_REFERENCE' if program.endswith('_NO_PROBE') else 'COMPLETE_WINDOW_STANDARD_REFERENCE'
            chosen=tail if first=='CONTINUE' or complete else 'KEEP'
            choice=save('TAIL_CHOICE',{'at_calls':machine.memory.completed_steps,'parent_return_sequence':returned['sequence'],'action':chosen,
                'requested_action':tail,'behavior_probabilities':[float(a==chosen) for a in TAIL_ACTIONS],'admission_reason':admission,
                'before_memory_sha256':machine.memory.sha256,'parameter_identification_qualified':False})
            if chosen in ('NOOP','RESET_TASK_I'):
                memory_mode='NOOP' if chosen=='NOOP' else 'ZERO_INTEGRAL'
                declared=save('MEMORY_TRANSITION_PLAN',{'at_calls':machine.memory.completed_steps,
                    'tail_choice_sequence':choice['sequence'],'plan':transition.propose(machine.memory,mode=memory_mode)})
                committed=transition.consume(machine,declared['plan']);memory_applied=True
                memory_nonzero=committed['nonzero_integral_changed'];memory_reason='SAVED_MEMORY_PLAN_CONSUMED'
                save('MEMORY_TRANSITION_COMMIT',{'at_calls':machine.memory.completed_steps,
                    'plan_sequence':declared['sequence'],'receipt':committed,'memory':machine.memory.to_dict()})
            elif program=='LOCAL_PID_RESET_I':memory_reason='INCOMPLETE_ACQUISITION_KEEP'
            if wanted is not None and complete:
                evidence=option['relocation_evidence'];declared=save('REFERENCE_UPDATE_PLAN',{'at_calls':machine.memory.completed_steps,
                    'tail_choice_sequence':choice['sequence'],'evidence':evidence,'plan':reference.propose(machine.memory,evidence,mode=wanted)})
                reference.consume(machine,declared['plan'],declared['evidence']);applied=True
                save('REFERENCE_UPDATE_COMMIT',{'at_calls':machine.memory.completed_steps,'plan_sequence':declared['sequence'],'memory':machine.memory.to_dict()})
    while not ended(machine.memory.current) and machine.memory.completed_steps<500:task_step('TAIL_TASK')
    m=machine.memory;reason='SUCCESS' if m.current.success else 'ENVIRONMENT_ENDED' if ended(m.current) else 'DEADLINE'
    outcome={'success':m.current.success,'terminated':m.current.terminated,'truncated':m.current.truncated,'total_steps':m.completed_steps,
        'deadline_loss':m.completed_steps if m.current.success else 500,'stop_reason':reason,'policy_queries':queries,
        'movement_steps':0 if option is None else option['reposition_steps'],'warm_probe_steps':0 if option is None else option['probe_steps'],
        'complete_warm_window':option is not None and option['window'] is not None,'option_reason':None if option is None else option['reason'],
        'measurement_anchor':None if option is None else option['measurement_anchor'],'reference_update_applied':applied,'reference_update_mode':mode(program),
        'reference_admission_reason':admission,'acquisition_entered':option is not None and method(program) is not None,
        'c4_c8_fit_attempts':0,'c4_c8_fit_results':0,'c4_c8_optimizer_nfev':0,'final_memory':m.to_dict(),
        'memory_transition_applied':memory_applied,'memory_transition_mode':memory_mode,'memory_nonzero_changed':memory_nonzero,'memory_transition_reason':memory_reason,
        'new_parameter_identification_training':0,'new_policy_training':0,'online_LLM_API_calls':0}
    save('OUTCOME',{'at_calls':m.completed_steps,'outcome':outcome,'final':asdict(m.current)})
    return {'outcome':outcome,'events':events}
