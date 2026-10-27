"""Fixed RAW PI prefix, optional standard movement, common8, known16; no fit."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.local_reprobe_v1 import selected_anchor,anchor_ready,control_update
from src.probe.physical_reprobe_v1 import Start,StepReceipt,PROGRAM as MEASURE
from src.probe.cache_acquisition_evidence_v1 import digest
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.task_passive_pi_v1 import require

def ended(s):return any((s.success,s.terminated,s.truncated))

def run(task,initial,boundary,action,commands,packets,policy,step,emit,forecast):
    require(boundary in (16,32,64) and action in ('IN_TASK','MOVE') and len(commands)==16,'registered paired response program')
    machine=TaskMemoryMachine(TaskMemory.initial(task,initial));events=[];queries=0;move_count=measure_count=packet_count=0;entry_at=None;anchor=None
    def save(kind,payload):
        p=normalize(payload);ack=emit(kind,deepcopy(p))
        require(type(ack) is dict and set(ack)==set(p)|{'sequence','saved_ns'} and ack['sequence']==len(events) and digest({k:ack[k] for k in p})==digest(p),'durable unchanged public acknowledgement')
        events.append(ack);return ack
    def act(command,phase,decision,raw=None):
        prefix=phase=='PREFIX_TASK';current=machine.memory.current if prefix else receipts[-1].current if receipts else machine.memory.current
        at=machine.memory.completed_steps if prefix else start.completed_steps+len(receipts)
        request=save('COMMAND',dict(at_calls=at,phase=phase,before=asdict(current),decision_sequence=decision['sequence'],command=np.asarray(command,np.float32).tolist(),raw_policy=raw))
        supplied=deepcopy(request);r=step(supplied)
        require(type(r) is StepReceipt and digest(supplied)==digest(request) and r.completed_steps==at+1,'actual current-state receipt for saved command')
        return r
    declaration=save('PROGRAM',dict(at_calls=0,task=task,boundary=boundary,acquisition_action=action,commands=commands,packets=packets,
        common_measure_commands=[list(u) for u in MEASURE],purpose='PAIRED_RESPONSE_NOT_TASK_UTILITY',new_parameter_fits=0,online_LLM_API_calls=0))
    while machine.memory.completed_steps<boundary and not ended(machine.memory.current):
        m=machine.memory;raw=np.asarray(policy(np.asarray(m.current.observation).copy()),np.float32).tolist();queries+=1
        plan=save('PI_PLAN',dict(at_calls=m.completed_steps,saved_plan=machine.plan(raw)))
        r=act(plan['saved_plan']['pi_plan']['numbers']['sent_command'],'PREFIX_TASK',plan,raw);machine.commit(plan['saved_plan'],r)
        save('TASK_MEMORY_COMMIT',dict(at_calls=machine.memory.completed_steps,memory=machine.memory.to_dict()))
    reason='ENDED_BEFORE_BOUNDARY'
    if not ended(machine.memory.current):
        m=machine.memory;token=machine.suspend();receipts=[];start=Start(task,m.completed_steps,m.current,m.saved_controller[1],m.saved_controller[2][:2]);current=m.current;ready=action=='IN_TASK'
        if action=='MOVE':
            anchor=selected_anchor(start,'LOCAL_PID');history=[current.observation];integral=[0.,0.];lifted=current.observation[2]>=anchor[2]-.015
            save('MOVE_ENTRY',dict(at_calls=m.completed_steps,anchor=list(anchor),memory=m.to_dict(),token=token))
            while not ended(current) and move_count<64 and not anchor_ready(history,anchor):
                updated,u=control_update(start,history,lifted,integral,'LOCAL_PID')
                choice=save('INTEGRAL_UPDATE',dict(at_calls=start.completed_steps+len(receipts),integral_before=integral,integral_after=updated))
                r=act(u,'REPOSITION',choice);receipts.append(r);current=r.current;history.append(current.observation);integral=updated;move_count+=1
                lifted=lifted or current.observation[2]>=anchor[2]-.015
            ready=not ended(current) and anchor_ready(history,anchor)
        reason='ENDED_DURING_REPOSITION' if ended(current) else 'ANCHOR_NOT_REACHED' if not ready else 'ENDED_DURING_COMMON_MEASURE'
        if ready:
            plan=save('COMMON_MEASURE_PLAN',dict(at_calls=start.completed_steps+len(receipts),commands=[list(u) for u in MEASURE]))
            while measure_count<8 and not ended(current):
                choice=save('MEASURE_COMMAND_CHOICE',dict(at_calls=start.completed_steps+len(receipts),plan_sequence=plan['sequence'],index=measure_count,command=list(MEASURE[measure_count])))
                r=act(choice['command'],'COMMON_MEASURE',choice);receipts.append(r);current=r.current;measure_count+=1
            if measure_count==8 and not ended(current):
                entry_at=start.completed_steps+len(receipts)
                plan=save('PACKET_PLAN',dict(at_calls=entry_at,program_sequence=declaration['sequence'],commands=commands,integral_carried_xy=list(m.integral_xy)))
                request=save('FORECAST_REQUEST',dict(at_calls=entry_at,packet_plan_sequence=plan['sequence'],packets=packets,integral_carried_xy=list(m.integral_xy)))
                result=forecast(deepcopy(request));saved=save('FORECAST_RESULT',dict(at_calls=entry_at,request_sequence=request['sequence'],result=result))
                while packet_count<16 and not ended(current):
                    choice=save('PACKET_COMMAND_CHOICE',dict(at_calls=start.completed_steps+len(receipts),packet_plan_sequence=plan['sequence'],forecast_sequence=saved['sequence'],index=packet_count,command=commands[packet_count]))
                    r=act(choice['command'],'EXOGENOUS_PACKET',choice);receipts.append(r);current=r.current;packet_count+=1
                reason='PACKET_COMPLETE' if packet_count==16 else 'ENDED_DURING_PACKET'
        machine.resume(token,receipts);save('TASK_MEMORY_RETURN',dict(at_calls=machine.memory.completed_steps,memory=machine.memory.to_dict()))
    m=machine.memory
    result=dict(total_steps=m.completed_steps,policy_queries=queries,reposition_steps=move_count,common_measure_steps=measure_count,packet_steps=packet_count,
        entry_at_calls=entry_at,complete_packet=packet_count==16,complete_first_eight=packet_count>=8,reason=reason,anchor=None if anchor is None else list(anchor),
        success_at_response_horizon=m.current.success,terminated=m.current.terminated,truncated=m.current.truncated,final_memory=m.to_dict(),
        full_task_tail_evaluated=False,new_model_fits=0,online_LLM_API_calls=0)
    save('OUTCOME',dict(at_calls=m.completed_steps,outcome=result,final=asdict(m.current)));return result
