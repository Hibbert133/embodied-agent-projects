"""Fixed RAW PI / qualified local PID / predeclared exogenous packet.

Forecasts are logged before the first packet action and never select actions.
Collection ends at its registered response horizon, not a task deadline.
"""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.local_reprobe_v1 import selected_anchor,anchor_ready,control_update
from src.probe.physical_reprobe_v1 import Start,StepReceipt
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.cache_acquisition_evidence_v1 import digest


def require(ok,message):
    if not ok:raise ValueError(message)


def ended(s):return any((s.success,s.terminated,s.truncated))


def run(task,initial,boundary,actions,policy,step,emit,forecast):
    require(boundary in (16,32,64) and len(actions) in (8,32),'registered response program')
    require(all(len(u)==4 and max(abs(u[0]),abs(u[1]))<=float(np.float32(.8)) and u[2:]==[0.,0.] for u in actions),'bounded exogenous XY packet')
    machine=TaskMemoryMachine(TaskMemory.initial(task,initial));events=[];queries=0;move_count=packet_count=0;entry_at=None;forecast_record=None
    def save(kind,payload):
        p=normalize(payload);ack=emit(kind,deepcopy(p))
        require(type(ack) is dict and set(ack)==set(p)|{'sequence','saved_ns'} and ack['sequence']==len(events)
            and digest({k:ack[k] for k in p})==digest(p),'durable unchanged public acknowledgement')
        events.append({'kind':kind,'payload':deepcopy(ack)});return ack
    def act(command,phase,decision,raw=None):
        current=machine.memory.current if phase=='PREFIX_TASK' else receipts[-1].current if receipts else machine.memory.current
        at=machine.memory.completed_steps if phase=='PREFIX_TASK' else start.completed_steps+len(receipts)
        request=save('COMMAND',{'at_calls':at,'phase':phase,'before':asdict(current),'decision_sequence':decision['sequence'],
            'command':np.asarray(command,np.float32).tolist(),'raw_policy':raw})
        supplied=deepcopy(request);r=step(supplied);require(type(r) is StepReceipt and digest(supplied)==digest(request) and r.completed_steps==at+1,'actual one-step receipt')
        return r
    declaration=save('PROGRAM',{'at_calls':0,'task':task,'boundary':boundary,'actions':actions,'purpose':'RESPONSE_HORIZON_NOT_TASK_EVALUATION',
        'raw_PI_time_constant_s':.5,'local_PID_gains':[8.,16.,.32],'new_parameter_fits':0,'online_LLM_API_calls':0})
    while machine.memory.completed_steps<boundary and not ended(machine.memory.current):
        m=machine.memory;raw=np.asarray(policy(np.asarray(m.current.observation).copy()),np.float32).tolist();queries+=1
        plan=save('PI_PLAN',{'at_calls':m.completed_steps,'saved_plan':machine.plan(raw)})
        r=act(plan['saved_plan']['pi_plan']['numbers']['sent_command'],'PREFIX_TASK',plan,raw);machine.commit(plan['saved_plan'],r)
        save('TASK_MEMORY_COMMIT',{'at_calls':machine.memory.completed_steps,'memory':machine.memory.to_dict()})
    reason='ENDED_BEFORE_BOUNDARY';anchor=None
    if not ended(machine.memory.current):
        m=machine.memory;token=machine.suspend();receipts=[]
        start=Start(task,m.completed_steps,m.current,m.saved_controller[1],m.saved_controller[2][:2]);anchor=selected_anchor(start,'LOCAL_PID')
        entry=save('MOVE_ENTRY',{'at_calls':m.completed_steps,'memory':m.to_dict(),'token':token,'anchor':list(anchor)})
        history=[m.current.observation];integral=[0.,0.];lifted=history[-1][2]>=anchor[2]-.015;current=m.current
        while not ended(current) and move_count<64 and not anchor_ready(history,anchor):
            updated,u=control_update(start,history,lifted,integral,'LOCAL_PID')
            choice=save('INTEGRAL_UPDATE',{'at_calls':start.completed_steps+len(receipts),'integral_before':integral,'integral_after':updated})
            r=act(u,'REPOSITION',choice);receipts.append(r);current=r.current;history.append(current.observation);integral=updated;move_count+=1
            lifted=lifted or history[-1][2]>=anchor[2]-.015
        reason='ENDED_DURING_REPOSITION' if ended(current) else 'ANCHOR_NOT_REACHED'
        if not ended(current) and anchor_ready(history,anchor):
            entry_at=start.completed_steps+len(receipts)
            plan=save('PACKET_PLAN',{'at_calls':entry_at,'source_program_sequence':declaration['sequence'],'commands':actions,
                'entry_history':list(history[-4:]),'anchor':list(anchor),'forecast_horizon':8})
            request=save('FORECAST_REQUEST',{'at_calls':entry_at,'packet_plan_sequence':plan['sequence'],'planned_commands':actions[:8]})
            forecasts=forecast(deepcopy(request))
            forecast_record=save('FORECAST_RESULT',{'at_calls':entry_at,'request_sequence':request['sequence'],'result':forecasts})
            while packet_count<len(actions) and not ended(current):
                choice=save('PACKET_COMMAND_CHOICE',{'at_calls':start.completed_steps+len(receipts),'packet_plan_sequence':plan['sequence'],
                    'packet_index':packet_count,'forecast_sequence':forecast_record['sequence'],'command':actions[packet_count]})
                r=act(choice['command'],'EXOGENOUS_PACKET',choice);receipts.append(r);current=r.current;packet_count+=1
            reason='PACKET_COMPLETE' if packet_count==len(actions) else 'ENDED_DURING_PACKET'
        machine.resume(token,receipts)
        save('TASK_MEMORY_RETURN',{'at_calls':machine.memory.completed_steps,'memory':machine.memory.to_dict()})
    m=machine.memory;outcome={'total_steps':m.completed_steps,'policy_queries':queries,'reposition_steps':move_count,'packet_steps':packet_count,
        'entry_at_calls':entry_at,'complete_packet':packet_count==len(actions),'complete_first_eight':packet_count>=8,'reason':reason,
        'success_at_response_horizon':m.current.success,'terminated':m.current.terminated,'truncated':m.current.truncated,
        'full_task_tail_evaluated':False,'final_memory':m.to_dict(),'new_model_fits':0,'online_LLM_API_calls':0}
    save('OUTCOME',{'at_calls':m.completed_steps,'outcome':outcome,'final':asdict(m.current)})
    return outcome
