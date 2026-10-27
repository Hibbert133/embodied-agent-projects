"""Eighty declared clean-input commands; no policy, fit, or physical restore."""
from copy import deepcopy
from dataclasses import asdict
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.graybox_observer_v1 import require,digest,sent
from src.probe.physical_reprobe_v1 import StepReceipt

def run(task,initial,commands,step,emit):
    require(type(commands) is list and len(commands)==80,'frozen nominal command count')
    for u in commands:sent(u)
    current=initial;events=[];n=0
    def save(kind,payload):
        p=normalize(payload);ack=emit(kind,deepcopy(p))
        require(type(ack) is dict and set(ack)==set(p)|{'sequence','saved_ns'} and ack['sequence']==len(events) and digest({k:ack[k] for k in p})==digest(p),'unchanged durable nominal event')
        events.append(ack);return ack
    declaration=save('PROGRAM',dict(at_calls=0,task=task,boundary=0,acquisition_action='NOMINAL',commands=commands,packets={'NOMINAL':commands},
        common_measure_commands=[],purpose='DECLARED_IDENTITY_INPUT_NOMINAL_TRAINING',new_parameter_fits=0,online_LLM_API_calls=0))
    while n<80 and not any((current.success,current.terminated,current.truncated)):
        choice=save('NOMINAL_COMMAND_CHOICE',dict(at_calls=n,program_sequence=declaration['sequence'],index=n,command=commands[n]))
        request=save('COMMAND',dict(at_calls=n,phase='NOMINAL_INPUT',before=asdict(current),decision_sequence=choice['sequence'],command=commands[n],raw_policy=None))
        supplied=deepcopy(request);r=step(supplied)
        require(type(r) is StepReceipt and r.completed_steps==n+1 and digest(supplied)==digest(request),'one unchanged saved command before actual nominal response')
        current=r.current;n+=1
    out=dict(total_steps=n,policy_queries=0,reposition_steps=0,common_measure_steps=0,packet_steps=0,entry_at_calls=None,complete_packet=False,complete_first_eight=False,
        reason='NOMINAL_PLAN_COMPLETE' if n==80 else 'NOMINAL_EARLY_END',anchor=None,success_at_response_horizon=current.success,terminated=current.terminated,truncated=current.truncated,
        final_memory=None,nominal_steps=n,completed_nominal_plan=n==80,full_task_tail_evaluated=False,new_model_fits=0,online_LLM_API_calls=0)
    save('OUTCOME',dict(at_calls=n,outcome=out,final=asdict(current)));return out
