"""Real-state acquisition/receiver host. No simulator, seed, oracle or fit API."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.correction_scope_risk_reference_v1 import node_from_view
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.physical_reprobe_v1 import Start,StepReceipt
from src.probe.task_passive_pi_v1 import require,digest
from src.probe import acquisition_reference_operation_v1 as macro
from src.probe import correction_scope_model_v1 as public
from src.probe.correction_scope_program_v1 import ended


def validate_decision(node,value):
    require(type(value) is dict and set(value)=={'schema','stage','action','rate','scores','model_sha256','input_sha256','kind'},'strict saved risk decision')
    require(value['schema']=='LIVE_RISK_DECISION_V1' and value['stage']==node['stage'] and value['input_sha256']==digest(node),'actual public query binding')
    require(value['kind'] in ('FROZEN_MODEL','FORCED_REFERENCE') and isinstance(value['model_sha256'],str),'decision provenance')
    pre=node['stage']=='PRE';scores=value['scores'];require(type(scores) is list and len(scores)==(3 if pre else 4),'finite candidate risk scores')
    require(all(type(v) in (float,int) and np.isfinite(v) for v in scores),'finite raw scores')
    choice=value['action'] if pre else value['rate'];require(type(choice) is int and 0<=choice<len(scores),'registered selected index')
    require(value['rate'] is None if pre else value['action'] is None,'stage ownership')
    require(choice==next(i for i,v in enumerate(scores) if v-min(scores)<=1e-10),'selection consumes saved scores with fixed tie convention')
    return value


def run(task,initial,boundary,policy,step,emit,decide):
    require(task in public.TASKS and boundary in (16,32,64) and not ended(initial),'registered live task and boundary')
    machine=TaskMemoryMachine(TaskMemory.initial(task,initial));events=[];history=[];queries=0;option=None;pre=None;post=None;action=None;rate=None
    def save(kind,payload):
        p=normalize(payload);ack=emit(kind,deepcopy(p))
        require(type(ack) is dict and set(ack)==set(p)|{'sequence','saved_ns'} and ack['sequence']==len(events)
            and digest({k:ack[k] for k in p})==digest(p),'changed/unordered durable acknowledgement')
        events.append(dict(kind=kind,payload=deepcopy(ack)));return ack
    def physical(saved):
        supplied=deepcopy(saved);receipt=step(supplied)
        require(type(receipt) is StepReceipt and digest(saved)==digest(supplied) and receipt.completed_steps==len(history)+1,'continuous actual physical receipt')
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
    def query(stage):
        # These metadata are the actual OLD controller, before rate adoption.
        # The canonical node removes zero-duration candidate metadata.
        value=public.view(stage,machine.memory,history,action or 'CONTINUE',.5)
        node=node_from_view(value);declared=save('FORECAST_INPUT',dict(at_calls=machine.memory.completed_steps,value=value,node=node))
        decision=validate_decision(node,normalize(decide(deepcopy(node))))
        saved=save('FORECAST',dict(at_calls=machine.memory.completed_steps,input_sequence=declared['sequence'],forecast=decision,
            prediction_only_not_control_selection=False))
        return dict(input_sequence=declared['sequence'],forecast_sequence=saved['sequence'],at_calls=machine.memory.completed_steps,decision=decision)
    save('PROGRAM',dict(at_calls=0,task=task,boundary=boundary,prediction_only=False,dynamic_decision=True,
        source_policy='RAW_TASK_PI_T0.5',online_LLM_API_calls=0))
    while machine.memory.completed_steps<boundary and not ended(machine.memory.current):task_step('PREFIX_TASK')
    if not ended(machine.memory.current):
        pre=query('PRE');action=public.ACTIONS[pre['decision']['action']];before=machine.memory
        choice=save('ACQUISITION_CHOICE',dict(at_calls=before.completed_steps,action=action,before_memory=before.to_dict(),
            forecast_sequence=pre['forecast_sequence'],assignment=pre['decision']['kind']))
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
        returned=save('TASK_MEMORY_RETURN',dict(at_calls=machine.memory.completed_steps,memory=machine.memory.to_dict(),action=action,
            parent_choice_sequence=choice['sequence'],reason=option['reason']))
        if not ended(machine.memory.current):
            post=query('POST');rate=public.RATES[post['decision']['rate']]
            proposed=save('RATE_PLAN',dict(at_calls=machine.memory.completed_steps,before_memory=machine.memory.to_dict(),
                rate=rate,memory_mode='CARRY',return_sequence=returned['sequence'],decision_sequence=post['forecast_sequence']))
            require(proposed['rate']==rate and proposed['before_memory']==normalize(machine.memory.to_dict()),'saved nonstale correction')
            receipt=machine.set_rate(proposed['rate'],memory_mode=proposed['memory_mode'])
            save('RATE_COMMIT',dict(at_calls=machine.memory.completed_steps,plan_sequence=proposed['sequence'],receipt=receipt,memory=machine.memory.to_dict()))
    while machine.memory.completed_steps<500 and not ended(machine.memory.current):task_step('TAIL_TASK')
    m=machine.memory;outcome=dict(success=m.current.success,terminated=m.current.terminated,truncated=m.current.truncated,total_steps=m.completed_steps,
        deadline_loss=m.completed_steps if m.current.success else 500,stop_reason='SUCCESS' if m.current.success else 'ENVIRONMENT_ENDED' if ended(m.current) else 'DEADLINE',
        policy_queries=queries,movement_steps=0 if option is None else option['reposition_steps'],measurement_steps=0 if option is None else option['probe_steps'],
        pre_forecast=pre,post_forecast=post,selected_action=action,selected_rate=rate,final_memory=m.to_dict(),online_LLM_API_calls=0,
        c4_c8_fit_attempts=0,new_policy_training=0)
    save('OUTCOME',dict(at_calls=m.completed_steps,outcome=outcome,final=asdict(m.current)))
    return dict(outcome=outcome,events=events)
