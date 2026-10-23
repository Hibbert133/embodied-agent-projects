"""Actual acquisition/KEEP contract on RAW PI's own history; no learned choice."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.task_passive_pi_v1 import require,digest
from src.probe.physical_reprobe_v1 import Start,StepReceipt,acquire

ACTIONS=('CONTINUE','VALIDATE8','MOVE_MEASURE8')


def ended(current):return any((current.success,current.terminated,current.truncated))


def run(task,initial,boundary,action,policy,step,emit):
    require(boundary in (16,32,64) and action in ACTIONS and not ended(initial),'registered live acquisition contract')
    memory=TaskMemoryMachine(TaskMemory.initial(task,initial));events=[];queries=0;option=None;entry=None

    def save(kind,payload):
        expected=normalize(payload);ack=emit(kind,deepcopy(expected))
        require(type(ack) is dict and set(ack)==set(expected)|{'sequence','saved_ns'} and ack['sequence']==len(events)
            and digest({k:ack[k] for k in expected})==digest(expected),'changed or unordered journal acknowledgement')
        events.append({'kind':kind,'payload':deepcopy(ack)});return ack

    def task_step(phase):
        nonlocal queries
        m=memory.memory;require(not ended(m.current) and m.completed_steps<500,'task step after end')
        raw=np.asarray(policy(np.array(m.current.observation,copy=True)),np.float32).tolist();queries+=1
        planned=memory.plan(raw);declared=save('PI_PLAN',{'at_calls':m.completed_steps,'saved_plan':planned})
        command=declared['saved_plan']['pi_plan']['numbers']['sent_command']
        request=save('COMMAND',{'at_calls':m.completed_steps,'phase':phase,'decision_sequence':declared['sequence'],
            'before':asdict(m.current),'command':command,'raw_policy':raw})
        supplied=deepcopy(request);receipt=step(supplied)
        require(digest(supplied)==digest(request),'host changed saved task command')
        memory.commit(declared['saved_plan'],receipt)
        save('STEP_RESULT',{'at_calls':memory.memory.completed_steps,'command_sequence':request['sequence'],'after':asdict(memory.memory.current)})
        save('TASK_MEMORY_COMMIT',{'at_calls':memory.memory.completed_steps,'memory':memory.memory.to_dict()})

    save('PROGRAM',{'at_calls':0,'task':task,'boundary':boundary,'action':action,'initial':asdict(initial),
        'source_policy':'RAW_TASK_PI_T0.5','new_parameter_fits':0,'online_LLM_API_calls':0,'adoption_action_family_qualified':False})
    while memory.memory.completed_steps<boundary and not ended(memory.memory.current):task_step('PREFIX_TASK')
    if not ended(memory.memory.current):
        m=memory.memory;entry=m.to_dict();start=m.completed_steps
        choice=save('ACQUISITION_CHOICE',{'at_calls':start,'before_memory':entry,'action':action,
            'behavior_probabilities':[float(a==action) for a in ACTIONS],
            'assignment':'DETERMINISTIC_SOFTWARE_ARM_NO_CROSS_ACTION_POSITIVITY','model_or_value_prediction':None})
        if action=='VALIDATE8':
            require(500-start>=108,'short validation and actual task reserve')
            for _ in range(8):
                if ended(memory.memory.current):break
                task_step('VALIDATE_TASK')
            option={'reason':'ENDED_DURING_VALIDATION' if ended(memory.memory.current) else 'VALIDATION_EXECUTED',
                'new_steps':memory.memory.completed_steps-start,'reposition_steps':0,'probe_steps':0,'window':None}
        elif action=='MOVE_MEASURE8':
            token=memory.suspend();save('TASK_MEMORY_SUSPEND',{'at_calls':start,'token':token,'memory':entry});receipts=[]
            def moved(request):
                receipt=step(request);require(type(receipt) is StepReceipt,'actual acquisition receipt');receipts.append(receipt);return receipt
            option=acquire(Start(task,start,m.current,m.saved_controller[1],m.saved_controller[2][:2]),moved,save)
            memory.resume(token,receipts)
            require(digest(asdict(memory.memory.current))==digest(option['final']),'return must use actual last acquisition state')
        else:option={'reason':'ZERO_ACQUISITION_CONTINUE','new_steps':0,'reposition_steps':0,'probe_steps':0,'window':None}
        returned=save('TASK_MEMORY_RETURN',{'at_calls':memory.memory.completed_steps,'action':action,'memory':memory.memory.to_dict(),
            'before_memory_sha256':digest(entry),'new_steps':memory.memory.completed_steps-start,
            'option_reason':option['reason'],'measurement_model_qualified':False})
        if not ended(memory.memory.current):
            save('TAIL_CHOICE',{'at_calls':memory.memory.completed_steps,'parent_return_sequence':returned['sequence'],'action':'KEEP',
                'behavior_probabilities':[1.0],'available_actions':['KEEP'],'memory_sha256':memory.memory.sha256,
                'new_correction_applied':False,'reason':'No qualified warm reidentification model; retain original correction and task memory'})
    while not ended(memory.memory.current) and memory.memory.completed_steps<500:task_step('TAIL_TASK')
    m=memory.memory;reason='SUCCESS' if m.current.success else 'ENVIRONMENT_ENDED' if ended(m.current) else 'DEADLINE'
    outcome={'success':m.current.success,'terminated':m.current.terminated,'truncated':m.current.truncated,'total_steps':m.completed_steps,
        'deadline_loss':m.completed_steps if m.current.success else 500,'stop_reason':reason,'policy_queries':queries,
        'boundary_reached':entry is not None,'option_reason':None if option is None else option['reason'],
        'option_steps':None if option is None else option['new_steps'],'movement_steps':0 if option is None else option['reposition_steps'],
        'warm_probe_steps':0 if option is None else option['probe_steps'],'complete_warm_window':option is not None and option['window'] is not None,
        'final_memory':m.to_dict(),'new_parameter_fits':0,'new_response_training':0,'new_policy_training':0,'online_LLM_API_calls':0}
    save('OUTCOME',{'at_calls':m.completed_steps,'outcome':outcome,'final':asdict(m.current)})
    return {'outcome':outcome,'events':events}
