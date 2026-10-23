"""One controlled reset, immutable noise and real continuous task programs.

Native imports are lazy. The controller receives no fault, seed or private state.
"""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from src.analysis import response_action_io_v1 as allocation
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import response_action_program_v1 as actor
from src.probe.cold_start_response import ColdPrefix
from src.probe.physical_reprobe_v1 import StepReceipt


class CaseFailure(RuntimeError):
    def __init__(self,record): super().__init__(str(record.get('error'))); self.record=record


def run_live(spec,nominal,rank_model,session,take_witness,sync):
    io=allocation.io; allocation.validate_spec(spec); program=actor.from_spec(spec)
    base=session.env.unwrapped; addresses=(base.model._address,base.data._address)
    io.require(float(base.action_scale)==.01,'mocap command scale differs from frozen reference units')
    tape=session.ctx['noise_rows']; start_clock=float(base.data.time)
    initial_budget=session.run_budget['completed']; initial_frames=session.ledger.counts.get('simulation_frames_completed',0)
    resets={k:session.ledger.counts.get(k,0) for k in ('reset_attempts','reset_completed','reset_errors')}
    initial=session.public(); pending=None; events=[]; history=[initial.observation]; applied=False

    def continuous():
        io.require(session.env.unwrapped is base and (base.model._address,base.data._address)==addresses,'world identity changed')
        io.require(session.ctx['noise_rows'] is tape and not tape.flags.writeable,'initial noise tape replaced')
        io.require(all(session.ledger.counts.get(k,0)==v for k,v in resets.items()),'mid-task reset')
        n=session.ctx['calls']; io.require(n==session.completed==session.attempts==len(session.last_rows)==len(history)-1,'physical/history cursor differs')
        io.require(n<=500 and session.run_budget['completed']-initial_budget==n,'control budget discontinuity')
        io.require(session.ledger.counts.get('simulation_frames_completed',0)-initial_frames==5*n,'frame budget discontinuity')
        io.require(np.isclose(float(base.data.time)-start_clock,.0125*n,atol=1e-9,rtol=0),'clock rewind/discontinuity')
        io.require(not session.captures and not session.restores and not session._snapshots,'state copying/restoration forbidden')

    def intervene():
        nonlocal applied
        if session.ctx['calls']!=spec['planned_boundary'] or not session.alive(): return
        io.require(not applied and pending is None and session._pending is None,'repeat or late private boundary update')
        continuous(); before=session.witness(); pre=take_witness('INTERVENTION_PRE')
        old=deepcopy(session.fault); session.fault=allocation.destination(spec)
        io.require(session.witness()==before,'affine coefficient update changed world/RNG/time')
        session.emit('FAULT_BOUNDARY',{'logical_step':session.ctx['calls'],'old_fault_oracle':old,
            'new_fault_oracle':session.fault,'changed_oracle':spec['context']=='CHANGED','before':before,'after':session.witness()})
        post=take_witness('INTERVENTION_POST'); io.require(pre==post,'private boundary witness differs'); applied=True

    def policy(observation):
        nonlocal pending
        continuous(); io.require(pending is None and np.array_equal(observation,session.public().observation),'duplicate or stale fixed-policy query')
        pending=session.policy_query(observation).tolist(); return np.array(pending,np.float32)

    def emit(name,payload):
        continuous(); io.require(payload['at_calls']==session.ctx['calls'] and session._pending is None,'stale public event')
        if name=='PROGRAM':
            io.require(payload['program']==program.to_dict() and payload['boundary']==spec['planned_boundary'],'program changed')
        if name=='FIT_INTENT':
            p=ColdPrefix.from_dict(payload['prefix'])
            io.require(p.initial_observation==initial.observation and np.array_equal(p.commands,session.ctx['commands'])
                and np.array_equal(p.observations,session.ctx['observations']),'noncausal C8 fit history')
        if name=='COMMAND':
            io.require(payload['before']==normalize(asdict(session.public())) and payload['decision_sequence']<len(events),'unsaved/stale command')
            required=payload['phase'] in ('APPROACH','TASK')
            io.require((pending is not None)==required and payload['raw_policy']==pending,'one original policy query per task command')
        saved=session._agent_emit(name,payload); events.append({'kind':name,'payload':deepcopy(saved)})
        if name=='POST_MOVE_TASK_ENTRY': take_witness('POST_MOVEMENT')
        return saved

    def step(saved):
        nonlocal pending
        continuous(); io.require(saved==session._pending and session.run_budget['completed']<session.run_budget['maximum'],'unsaved or unbudgeted physical action')
        # Force saved plan and actual command bytes to storage before stepping.
        sync(); continuous(); current=session._agent_step(saved); history.append(current.observation)
        if saved['raw_policy'] is not None: pending=None
        continuous(); intervene(); return StepReceipt(current,session.ctx['calls'])

    result=actor.run(spec['task'],initial,nominal if program.uses_c8 else None,spec['planned_boundary'],program,policy,step,emit,rank_model)
    continuous(); io.require(pending is None and session._pending is None,'unconsumed policy/command')
    io.require(result['outcome']['policy_queries']==session.policy_queries and result['outcome']['total_steps']==session.ctx['calls'],'actor/host counters differ')
    take_witness('FINAL')
    return {**result['outcome'],'boundary_applied':applied,
        'boundary_missing_reason':None if applied else 'EARLY_SUCCESS' if session.public().success else
            'ENVIRONMENT_ENDED' if not session.alive() else result['outcome']['stop_reason'],
        'movement_available':any(e['kind']=='POST_MOVE_TASK_ENTRY' for e in events)}


def execute_case(spec,nominal,rank_model,emit,emit_private,ledger,budget,position,sync,dependencies=None):
    allocation.validate_spec(spec); io=allocation.io
    if dependencies is None:
        from src.analysis.paired_probe_host_v1 import ProbeSession
        from src.rollout.task_registry import create_task_environment,create_task_policy
        from scripts.qualify_delayed_intervention_v2 import observe_state
        dependencies={'environment':create_task_environment,'policy':create_task_policy,'session':ProbeSession,'observe':observe_state}
    started=perf_counter_ns(); env=session=None; refs=[]
    row={**spec,'completed':False,'error':None,'close_error':None,'environment_closed':False,
        'ledger_before':ledger.snapshot(),'initial_fault_oracle':allocation.initial_fault(),
        'destination_oracle':allocation.destination(spec),'state_witness_refs':refs,'novel_algorithm':False}
    counted={'c4_c8_fit_attempts':0,'c4_c8_fit_results':0,'c4_c8_optimizer_nfev':0,'response_model_forward_evaluations':0,'kinematic_proxy_evaluations':0}
    inference={'intents':0,'validated':0,'response_planned':0,'kinematic_planned':0}
    def public_emit(name,payload):
        if name=='AGENT_EVENT':
            if payload['agent_event']=='FIT_INTENT': counted['c4_c8_fit_attempts']+=1
            if payload['agent_event']=='FIT_RESULT':
                counted['c4_c8_fit_results']+=1; counted['c4_c8_optimizer_nfev']+=int(payload['public_payload']['fit'].get('nfev',0))
            if payload['agent_event']=='RANK_INTENT':
                inference['intents']+=1;inference['response_planned']+=payload['public_payload']['forward_evaluations_planned'];inference['kinematic_planned']+=payload['public_payload']['kinematic_evaluations_planned']
            if payload['agent_event']=='RANK_VALIDATED':
                inference['validated']+=1
                for field in ('response_model_forward_evaluations','kinematic_proxy_evaluations'):counted[field]+=payload['public_payload'][field]
        return emit(name,payload)
    def witness(label):
        expected=session.witness(); saved=dependencies['observe'](session,label,expected,position,emit_private); w=saved['witness']
        refs.append({'label':label,'sequence':saved['sequence'],'logical_step':session.ctx['calls'],
            'native_sha256':w['native_sha256'],'comparison_python_sha256':w['comparison_python_sha256']})
        return (w['native_sha256'],w['comparison_python_sha256'],expected['noise_past_sha256'],expected['simulation_time'])
    try:
        emit('FACTORY_INTENT',{'ledger':ledger.snapshot()})
        with ledger.scope('FACTORY_SETUP'): env=dependencies['environment'](spec['task'],spec['seed'])
        emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
        with ledger.scope('CONTROLLED_RESET'): initial,_=env.reset(seed=spec['seed'])
        session=dependencies['session'](env,dependencies['policy'](spec['task']),initial,spec['task'],spec['seed'],row['initial_fault_oracle'],public_emit,ledger,budget)
        session.ctx['noise_rows']=allocation.noise(spec['seed'],spec['noise_namespace'])
        session.branch={'role':'RESPONSE_ACTION_REFERENCE','future':0,'program':allocation.spec_id(spec)}
        emit('NOISE_COMMITMENT',{'at_calls':0,'noise_namespace_oracle':spec['noise_namespace'],
            'tape_sha256_oracle':io.digest(session.ctx['noise_rows'].tolist())})
        row['initial']=normalize(asdict(session.public())); witness('INITIAL')
        row.update(run_live(spec,nominal,rank_model,session,witness,sync))
        io.require(all(row[k]==v for k,v in counted.items()),'fit accounting differs')
        row['final']=normalize(asdict(session.public())); row['completed']=True
    except BaseException as error: row['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        row.update(counted)
        if session is not None:
            row.update(host_attempts=session.attempts,host_returned=session.completed,total_steps=session.ctx['calls'],
                policy_queries=session.policy_queries,captures=session.captures,restores=session.restores,physical_rows_count=len(session.last_rows))
        row['ledger_before_close']=ledger.snapshot()
        if env is not None:
            try: env.close(); row['environment_closed']=True
            except BaseException as error: row['close_error']={'type':type(error).__name__,'message':str(error)}
        row['ledger_after_close']=ledger.snapshot(); row['wall_ns']=perf_counter_ns()-started
        row['inference_accounting']=inference
        row['computation_counters_complete']=row['completed'] and counted['c4_c8_fit_attempts']==counted['c4_c8_fit_results'] and inference['intents']==inference['validated']
    if row['error'] is not None or row['close_error'] is not None or not row['completed'] or not row['environment_closed']:
        raise CaseFailure(normalize(row))
    return normalize(row)
