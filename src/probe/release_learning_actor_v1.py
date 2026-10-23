"""Actual fixed-policy continuation after one acquisition and signal release.

The actor owns no environment, reset, oracle, future-noise or RNG capability.
The host supplies one exposure draw only after a durable physical-return seal.
"""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.physical_reprobe_v1 import Start,StepReceipt
from src.probe.task_passive_pi_v1 import require,digest
from src.probe import acquisition_reference_operation_v1 as macro
from src.probe import information_release_v1 as release
from src.probe import memory_reset_program_v1 as old
from src.probe import release_learning_programs_v1 as programs
from src.probe import release_learning_predictor_v1 as predictor

TEST_VERSION=digest({'schema':'NUMERICAL_NATIVE_AND_FACTORIAL_RATE_BANK_V1','rates':release.RATES})
RESERVE={'CONTINUE':1,'VALIDATE8':32,'MOVE_MEASURE':100}
COST={'CONTINUE':0,'VALIDATE8':8,'MOVE_MEASURE':72}


def ended(c):return any((c.success,c.terminated,c.truncated))
def is_legacy(program):return programs.legacy(program)


def choose_pre(memory,history,runtime,program):
    if program=='TRAIN_BEST_PROGRAM':return dict(action=runtime['receiver']['best_fixed_program']['action'],
        expose=False,rate=runtime['receiver']['best_fixed_program']['rate'],source='TAIL_SELECT_FIXED_COMPLETE_PROGRAM')
    bank=runtime['policy'];kind='direct' if program=='DIRECT_RISK' else 'effect'
    risks=predictor.acquisition(bank,kind,normalize(memory.to_dict()),history);choices=[]
    for i,a in enumerate(release.ACTIONS):
        if 500-memory.completed_steps<COST[a]+RESERVE[a]:continue
        for expose in (False,True) if a!='CONTINUE' else (False,):
            v=risks[a];score=v['masked_risk']+(v['information_effect'] if expose else 0.)
            if program=='EFFECT_DISABLED' and expose:continue
            choices.append((score,a!='CONTINUE',expose,i,a))
    require(choices,'live continuation has no budget');score,_,expose,_,a=min(choices)
    if program=='RELEASE_ALWAYS':expose=a!='CONTINUE'
    if program=='FORCE_MASKED':expose=False
    return dict(action=a,expose=expose,rate=None,source='FROZEN_'+kind.upper(),predicted=risks,
        complete_program_risk=score,policy_version=bank['policy_version'])


def run(task,initial,boundary,program,nominal,policy,step,emit,*,runtime,draw_exposure):
    require(program in programs.ALL and boundary in (16,32,64),'registered public program and boundary')
    if is_legacy(program):
        if program=='PURE_MOVE_KEEP':
            from unittest.mock import patch
            actual_acquire=macro.acquire
            def no_probe(start,step,emit,*,method,measure=True):return actual_acquire(start,step,emit,method=method,measure=False)
            with patch.object(old.macro,'acquire',no_probe):result=old.run(task,initial,boundary,programs.legacy_name(program),nominal,policy,step,emit)
        else:result=old.run(task,initial,boundary,programs.legacy_name(program),nominal,policy,step,emit)
        result['outcome'].update(learning=None,exposure_draws=0,receiver_version=None,rate_transition_applied=False)
        return result
    require(nominal is None and not ended(initial),'RAW-history live program, no physics model')
    machine=TaskMemoryMachine(TaskMemory.initial(task,initial));events=[];history=[];phases=[];queries=0
    option=None;learning=None;draws=0;gain_applied=False;version=None;acquisition_action=None;exposure=None;forecasts=None
    def save(kind,payload):
        p=normalize(payload);ack=emit(kind,deepcopy(p))
        require(type(ack) is dict and set(ack)==set(p)|{'sequence','saved_ns'} and ack['sequence']==len(events)
            and digest({k:ack[k] for k in p})==digest(p),'changed/unordered durable acknowledgement')
        events.append({'kind':kind,'payload':deepcopy(ack)});return ack
    def physical(saved):
        supplied=deepcopy(saved);receipt=step(supplied)
        require(type(receipt) is StepReceipt and digest(supplied)==digest(saved) and receipt.completed_steps==len(history)+1,'actual consecutive physical receipt')
        history.append(dict(at_calls=saved['at_calls'],command=saved['command'],before=saved['before'],after=normalize(asdict(receipt.current))))
        phases.append(saved['phase']);return receipt
    def task_step(phase):
        nonlocal queries
        m=machine.memory;require(not ended(m.current) and m.completed_steps<500,'task after actual end/cap')
        raw=np.asarray(policy(np.array(m.current.observation,copy=True)),np.float32).tolist();queries+=1
        declared=save('PI_PLAN',dict(at_calls=m.completed_steps,saved_plan=machine.plan(raw)))
        request=save('COMMAND',dict(at_calls=m.completed_steps,phase=phase,decision_sequence=declared['sequence'],
            before=asdict(m.current),command=declared['saved_plan']['pi_plan']['numbers']['sent_command'],raw_policy=raw))
        machine.commit(declared['saved_plan'],physical(request))
        save('STEP_RESULT',dict(at_calls=machine.memory.completed_steps,command_sequence=request['sequence'],after=asdict(machine.memory.current)))
        save('TASK_MEMORY_COMMIT',dict(at_calls=machine.memory.completed_steps,memory=machine.memory.to_dict()))
    save('PROGRAM',dict(at_calls=0,task=task,program=program,boundary=boundary,initial=asdict(initial),
        source_policy='RAW_TASK_PI_T0.5',new_response_training=0,new_low_level_policy_training=0,online_LLM_API_calls=0))
    while machine.memory.completed_steps<boundary and not ended(machine.memory.current):task_step('PREFIX_TASK')
    if not ended(machine.memory.current):
        before=machine.memory;prefix=deepcopy(history);a,rate,exposure=programs.fixed(program)
        if program.startswith('CAL_'):
            forecasts=[]
            for i,bank in enumerate(runtime['pre_bank']['banks']):
                rt={**runtime,'policy':bank}
                forecasts.append(dict(bank_index=i,effect=choose_pre(before,prefix,rt,'LEARNED_EFFECT'),direct=choose_pre(before,prefix,rt,'DIRECT_RISK')))
            save('CAL_BANK_PREDICTIONS',dict(at_calls=before.completed_steps,recommendations=forecasts,
                prefix_sha256=digest(prefix),saved_before_any_current_acquisition_or_outcome=True))
        pre=dict(action=a,rate=rate,expose=exposure,source='REGISTERED_FIXED_PROCEDURE')
        if a is None:pre=choose_pre(before,prefix,runtime,program);a,rate,exposure=pre['action'],pre['rate'],pre['expose']
        requested=a
        if 500-before.completed_steps<COST[a]+RESERVE[a]:a,rate,exposure='CONTINUE',.5,False
        acquisition_action=a
        choice=save('ACQUISITION_CHOICE',dict(at_calls=before.completed_steps,before_memory=before.to_dict(),
            prefix_history=prefix,action=a,requested_action=requested,pre_plan=pre,
            assignment='ACTUAL_FROZEN_PROGRAM_SELECTION_NOT_ORACLE',acquisition_cost_already_in_risk=True))
        start=len(history)
        if a=='VALIDATE8':
            for _ in range(8):
                if ended(machine.memory.current):break
                task_step('VALIDATION_TASK')
            reason='EARLY_END' if ended(machine.memory.current) else 'COMPLETE'
            option=dict(reason='TASK_VALIDATION',reposition_steps=0,probe_steps=len(history)-start,window=None)
        elif a=='MOVE_MEASURE':
            token=machine.suspend();save('TASK_MEMORY_SUSPEND',dict(at_calls=before.completed_steps,token=token,memory=before.to_dict()));receipts=[]
            def moved(request):
                r=physical(request);receipts.append(r);return r
            option=macro.acquire(Start(task,before.completed_steps,before.current,before.saved_controller[1],before.saved_controller[2][:2]),moved,save,method='LOCAL_PID')
            machine.resume(token,receipts)
            reason='EARLY_END' if ended(machine.memory.current) else 'COMPLETE' if option['window'] is not None else 'PARTIAL' if receipts else 'BUDGET_KEEP'
        else:
            option=dict(reason='ZERO_ACQUISITION_CONTINUE',reposition_steps=0,probe_steps=0,window=None);reason='NO_ACQUISITION'
        trace=[{**row,'phase':'MEASUREMENT' if phase=='WARM_PROBE' else phase} for row,phase in zip(history[start:],phases[start:])]
        record=release.public_record(before,machine.memory,a,trace,reason)
        returned=save('TASK_MEMORY_RETURN',dict(at_calls=machine.memory.completed_steps,memory=machine.memory.to_dict(),first_action=a,option_reason=option['reason']))
        sealed=release.seal(record,returned['sequence']);declared=save('SIGNAL_SEAL',dict(at_calls=machine.memory.completed_steps,saved_return=sealed))
        version=runtime['receiver']['receiver_version'] if rate is None else TEST_VERSION
        if exposure=='RANDOM':
            u=draw_exposure(declared['sequence']);draws+=1
            receipt=release.assign(sealed,probability=.5,uniform=u,release_sequence=len(events),receiver_version=version)
        else:receipt=release.release(sealed,expose=exposure,release_sequence=len(events),receiver_version=version)
        released=save('INFORMATION_RELEASE',dict(at_calls=machine.memory.completed_steps,receipt=receipt,seal_sequence=declared['sequence']))
        decision=None
        if not ended(machine.memory.current) and machine.memory.completed_steps<500:
            if rate is None:base,full=predictor.receiver(runtime['receiver'],receipt['model_view'],prefix)
            else:
                base=[0. if t==rate else 500. for t in release.RATES];full=list(base) if receipt['model_view']['signal'] is not None else None
            decision=release.receiver_plan(sealed,receipt,base,full)
            chosen=save('RECEIVER_CHOICE',dict(at_calls=machine.memory.completed_steps,release_sequence=released['sequence'],decision=decision,
                receiver_input_sha256=digest(dict(model_view=receipt['model_view'],prefix_history=prefix))))
            if program not in ('RAW','N_CONT_KEEP'):
                declared=save('MEMORY_TRANSITION_PLAN',dict(at_calls=machine.memory.completed_steps,
                    receiver_choice_sequence=chosen['sequence'],plan=decision['gain_plan'],kind='RATE_ONLY_CARRY'))
                committed=release.consume_receiver(machine,decision,sealed,receipt);gain_applied=True
                save('MEMORY_TRANSITION_COMMIT',dict(at_calls=machine.memory.completed_steps,plan_sequence=declared['sequence'],receipt=committed,memory=machine.memory.to_dict()))
        learning=dict(pre_memory=normalize(before.to_dict()),prefix_history=prefix,pre_plan=pre,saved_return=sealed,
            release_receipt=receipt,receiver_decision=decision,acquisition_choice_sequence=choice['sequence'],cal_predictions=forecasts)
    while not ended(machine.memory.current) and machine.memory.completed_steps<500:task_step('TAIL_TASK')
    m=machine.memory;outcome=dict(success=m.current.success,terminated=m.current.terminated,truncated=m.current.truncated,total_steps=m.completed_steps,
        deadline_loss=m.completed_steps if m.current.success else 500,stop_reason='SUCCESS' if m.current.success else 'ENVIRONMENT_ENDED' if ended(m.current) else 'DEADLINE',
        policy_queries=queries,movement_steps=0 if option is None else option['reposition_steps'],warm_probe_steps=0 if option is None else option['probe_steps'],
        option_reason=None if option is None else option['reason'],complete_warm_window=option is not None and option['window'] is not None,
        acquisition_action=acquisition_action,exposure_draws=draws,receiver_version=version,learning=learning,rate_transition_applied=gain_applied,
        memory_transition_applied=gain_applied,reference_update_applied=False,final_memory=m.to_dict(),
        c4_c8_fit_attempts=0,c4_c8_fit_results=0,c4_c8_optimizer_nfev=0,new_response_training=0,new_low_level_policy_training=0,online_LLM_API_calls=0)
    save('OUTCOME',dict(at_calls=m.completed_steps,outcome=outcome,final=asdict(m.current)))
    return dict(outcome=outcome,events=events)
