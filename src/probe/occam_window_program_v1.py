"""Public-only, factual acquisition and recurrent gain selection above fixed PI.

The native host authenticates each receipt. This actor cannot reset/restore.
"""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.occam_performance_core_v1 import FeedbackSession,basis_forward,digest,require,RATES
from src.probe.occam_public_history_v1 import features
from src.probe import occam_window_cost_v1 as cost
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.physical_reprobe_v1 import Start,StepReceipt
from src.probe import acquisition_reference_operation_v1 as macro


class OccamProvider:
    def __init__(self,bank,*,history_steps=8,beta=0.):
        self.bank=deepcopy(bank);self.history_steps=history_steps;self.beta=beta;self.session=None
        d=bank['dimensions'];require(d==dict(history=83*history_steps,descriptor=87,outputs=1,bases=d['bases']),'registered public dimensions')
        self.bank_sha256=digest(bank)

    def declare(self,query):
        require(digest(self.bank)==self.bank_sha256,'saved bank changed')
        n=query['completed_steps'];prior=self.bank['prior']
        if self.session is None:
            self.session=FeedbackSession(prior['mean'],prior['covariance'],prior['process_covariance'],prior['measurement_covariance'],completed_steps=n)
        hs=[];xs=[]
        for rate in RATES:
            q={**deepcopy(query),'candidate_time_constant_s':rate};h,x=features(q,self.history_steps);hs.append(h);xs.append(x)
        bases=basis_forward(self.bank,np.asarray(hs),np.asarray(xs))
        return self.session.declare(bases,completed_steps=n,evaluation_steps=query['evaluation_steps'],
            reward_weights=[-1.],beta=self.beta,public_query_sha256=digest(query))

    def feedback(self,declared,measurement,current):
        if measurement['full_window']:
            return self.session.complete(declared,completed_steps=measurement['end_at'],
                observed_performance=[measurement['cost']],executed_rate=declared['selected_rate'])
        reason='SUCCESS' if current['success'] else 'TERMINATED' if current['terminated'] else 'TRUNCATED' if current['truncated'] else 'HOST_FAILURE'
        return self.session.end_partial(declared,completed_steps=measurement['end_at'],reason=reason)


def constructed_bank(sign):
    """Untrained hardware-contract fixture; never a learned reference result."""
    require(type(sign) is int and sign in (-1,1),'explicit two software fixtures')
    weights=np.zeros((2,88));weights[1,83]=1.
    return dict(schema='OCCAM_PERFORMANCE_BASIS_V1',dimensions=dict(history=664,descriptor=87,outputs=1,bases=2),
        encoder=[dict(weight=np.zeros((1,664)).tolist(),bias=[0.])],
        head=[dict(weight=weights.tolist(),bias=[1.,0.])],prior=dict(mean=[0.,float(sign)],covariance=[[1.,0.],[0.,1.]],
            process_covariance=[[.001,0.],[0.,.001]],measurement_covariance=[[.01]]))


def run(task,initial,boundary,action,provider,policy,step,emit,*,window_steps=16):
    require(boundary in (16,32,64) and action in ('CONTINUE','VALIDATE8','MOVE_MEASURE')
        and type(window_steps) is int and 1<=window_steps<=500,'registered factual acquisition and window')
    require(not any((initial.success,initial.terminated,initial.truncated)),'live controlled initial')
    machine=TaskMemoryMachine(TaskMemory.initial(task,initial));events=[];history=[];segments=[];queries=0;windows=0;option=None
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
        bank_sha256=provider.bank_sha256,scope='CONTINUOUS_HOST_CONTRACT_NOT_LEARNED_TASK_QUALIFICATION',online_LLM_API_calls=0))
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
        new_scientific_model_training=0,online_LLM_API_calls=0,untrained_software_fixture=True)
    save('OUTCOME',dict(at_calls=m.completed_steps,outcome=outcome,final=asdict(m.current)))
    return dict(outcome=outcome,events=events)
