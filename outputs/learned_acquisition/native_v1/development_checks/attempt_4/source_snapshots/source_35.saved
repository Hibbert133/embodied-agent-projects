"""Frozen factual controller arms and forecasts before their physical outcomes."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.physical_reprobe_v1 import Start,StepReceipt
from src.probe.task_passive_pi_v1 import require,digest
from src.probe import acquisition_reference_operation_v1 as macro
from src.probe import correction_scope_model_v1 as model


def ended(c):return any((c.success,c.terminated,c.truncated))


def run(task,initial,boundary,action,rate,policy,step,emit,*,bank=None):
    require(task in model.TASKS and boundary in (16,32,64) and action in model.ACTIONS and rate in model.RATES,'registered factual program')
    require(not ended(initial),'live controlled initial observation')
    machine=TaskMemoryMachine(TaskMemory.initial(task,initial));events=[];history=[];queries=0;option=None;pre=None;post=None
    def save(kind,payload):
        p=normalize(payload);ack=emit(kind,deepcopy(p))
        require(type(ack) is dict and set(ack)==set(p)|{'sequence','saved_ns'} and ack['sequence']==len(events)
            and digest({k:ack[k] for k in p})==digest(p),'changed/unordered durable acknowledgement')
        events.append({'kind':kind,'payload':deepcopy(ack)});return ack
    def physical(saved):
        supplied=deepcopy(saved);receipt=step(supplied)
        require(type(receipt) is StepReceipt and digest(saved)==digest(supplied) and receipt.completed_steps==len(history)+1,'actual consecutive physical receipt')
        history.append(dict(at_calls=saved['at_calls'],before=saved['before'],command=saved['command'],after=normalize(asdict(receipt.current))))
        return receipt
    def task_step(phase):
        nonlocal queries
        m=machine.memory;raw=np.asarray(policy(np.array(m.current.observation,copy=True)),np.float32).tolist();queries+=1
        plan=save('PI_PLAN',dict(at_calls=m.completed_steps,saved_plan=machine.plan(raw)))
        request=save('COMMAND',dict(at_calls=m.completed_steps,phase=phase,decision_sequence=plan['sequence'],before=asdict(m.current),
            command=plan['saved_plan']['pi_plan']['numbers']['sent_command'],raw_policy=raw))
        machine.commit(plan['saved_plan'],physical(request))
        save('STEP_RESULT',dict(at_calls=machine.memory.completed_steps,command_sequence=request['sequence'],after=asdict(machine.memory.current)))
        save('TASK_MEMORY_COMMIT',dict(at_calls=machine.memory.completed_steps,memory=machine.memory.to_dict()))
    def forecast(stage):
        value=model.view(stage,machine.memory,history,action,rate)
        declared=save('FORECAST_INPUT',dict(at_calls=machine.memory.completed_steps,value=value))
        saved=save('FORECAST',dict(at_calls=machine.memory.completed_steps,input_sequence=declared['sequence'],
            forecast=None if bank is None else model.predict(bank,value),prediction_only_not_control_selection=True))
        return dict(input_sequence=declared['sequence'],forecast_sequence=saved['sequence'],at_calls=machine.memory.completed_steps)
    save('PROGRAM',dict(at_calls=0,task=task,boundary=boundary,acquisition_action=action,time_constant_s=rate,
        prediction_only=True,source_policy='RAW_TASK_PI_T0.5',online_LLM_API_calls=0))
    while machine.memory.completed_steps<boundary and not ended(machine.memory.current):task_step('PREFIX_TASK')
    if not ended(machine.memory.current):
        pre=forecast('PRE');before=machine.memory
        choice=save('ACQUISITION_CHOICE',dict(at_calls=before.completed_steps,action=action,before_memory=before.to_dict(),
            forecast_sequence=pre['forecast_sequence'],assignment='FROZEN_FACTUAL_ARM_NOT_MODEL_SELECTION'))
        if action=='VALIDATE8':
            start=len(history)
            for _ in range(8):
                if ended(machine.memory.current):break
                task_step('VALIDATION_TASK')
            option=dict(reason='NORMAL_TASK_CONTINUATION',reposition_steps=0,probe_steps=len(history)-start,window=None)
        elif action=='MOVE_MEASURE':
            token=machine.suspend();save('TASK_MEMORY_SUSPEND',dict(at_calls=before.completed_steps,token=token,memory=before.to_dict()));receipts=[]
            def moved(request):
                r=physical(request);receipts.append(r);return r
            option=macro.acquire(Start(task,before.completed_steps,before.current,before.saved_controller[1],before.saved_controller[2][:2]),moved,save,method='LOCAL_PID')
            machine.resume(token,receipts)
        else:option=dict(reason='NO_ACQUISITION',reposition_steps=0,probe_steps=0,window=None)
        returned=save('TASK_MEMORY_RETURN',dict(at_calls=machine.memory.completed_steps,memory=machine.memory.to_dict(),
            action=action,parent_choice_sequence=choice['sequence'],reason=option['reason']))
        if not ended(machine.memory.current):
            proposed=save('RATE_PLAN',dict(at_calls=machine.memory.completed_steps,before_memory=machine.memory.to_dict(),
                rate=rate,memory_mode='CARRY',return_sequence=returned['sequence']))
            saved_rate=proposed['rate'];require(saved_rate==rate and proposed['before_memory']==normalize(machine.memory.to_dict()),'unsaved/stale rate choice')
            receipt=machine.set_rate(saved_rate,memory_mode=proposed['memory_mode'])
            save('RATE_COMMIT',dict(at_calls=machine.memory.completed_steps,plan_sequence=proposed['sequence'],receipt=receipt,memory=machine.memory.to_dict()))
            post=forecast('POST')
    while machine.memory.completed_steps<500 and not ended(machine.memory.current):task_step('TAIL_TASK')
    m=machine.memory;outcome=dict(success=m.current.success,terminated=m.current.terminated,truncated=m.current.truncated,total_steps=m.completed_steps,
        deadline_loss=m.completed_steps if m.current.success else 500,stop_reason='SUCCESS' if m.current.success else 'ENVIRONMENT_ENDED' if ended(m.current) else 'DEADLINE',
        policy_queries=queries,movement_steps=0 if option is None else option['reposition_steps'],measurement_steps=0 if option is None else option['probe_steps'],
        pre_forecast=pre,post_forecast=post,final_memory=m.to_dict(),online_LLM_API_calls=0,c4_c8_fit_attempts=0,new_policy_training=0)
    save('OUTCOME',dict(at_calls=m.completed_steps,outcome=outcome,final=asdict(m.current)))
    return dict(outcome=outcome,events=events)
