"""Actual native command consumption; private state remains in evaluator host."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from src.analysis import occam_reference_train_io_v1 as a
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import occam_training_program_v1 as actor
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe.occam_training_behavior_v1 import BehaviorProvider
io=a.io


class CaseFailure(RuntimeError):
    def __init__(self,row):super().__init__(str(row.get('error')));self.record=row


def run_live(spec,session,witness,sync):
    a.validate_spec(spec);base=session.env.unwrapped;addresses=(base.model._address,base.data._address)
    tape=session.ctx['noise_rows'];clock=float(base.data.time);paid=session.run_budget['completed']
    frames=session.ledger.counts.get('simulation_frames_completed',0);resets=session.ledger.counts.get('reset_attempts',0)
    history=[];pending=None;events={};applied=False;rate_witness=None;rate_count=0;integral=[0.,0.]
    def continuous():
        n=session.ctx['calls'];io.require(session.env.unwrapped is base and (base.model._address,base.data._address)==addresses,'world replaced')
        io.require(session.ctx['noise_rows'] is tape and not tape.flags.writeable and session.ledger.counts.get('reset_attempts',0)==resets,'noise/reset changed')
        io.require(n==session.attempts==session.completed==len(session.last_rows)==len(history)<=500,'actual cursor continuity')
        io.require(session.run_budget['completed']-paid==n and session.ledger.counts.get('simulation_frames_completed',0)-frames==5*n,'physical cost continuity')
        io.require(np.isclose(float(base.data.time)-clock,.0125*n,atol=1e-9,rtol=0) and not session.captures and not session.restores and not session._snapshots,'clock/restoration violation')
    def policy(observation):
        nonlocal pending
        continuous();io.require(pending is None and np.array_equal(observation,session.public().observation),'stale/duplicate fixed query')
        pending=session.policy_query(observation).tolist();return np.array(pending,np.float32)
    def emit(name,payload):
        nonlocal rate_witness,rate_count,integral
        continuous();io.require(payload['at_calls']==session.ctx['calls'] and session._pending is None,'stale/pending event')
        if name=='WINDOW_QUERY':
            q=payload['value'];io.require(q['history']==history and q['initial']==row_initial and q['integral_xy']==integral,'fabricated/future public history')
        if name=='WINDOW_DECISION':
            previous=events.get(payload['input_sequence']);d=payload['declaration']
            io.require(previous is not None and previous[0]=='WINDOW_QUERY' and payload['input_sequence']==len(events)-1
                and d['public_query_sha256']==io.digest(previous[1]['value']),'unsaved decision query')
        if name=='COMMAND':
            io.require(payload['before']==normalize(asdict(session.public())) and payload['raw_policy']==pending,'stale command/raw query')
            parent=events.get(payload['decision_sequence']);io.require(parent is not None,'unsaved command parent')
            if pending is not None:io.require(parent[0]=='PI_PLAN' and payload['command']==parent[1]['saved_plan']['pi_plan']['numbers']['sent_command'],'saved task command changed')
        if name=='TASK_MEMORY_COMMIT':integral=payload['memory']['integral_xy']
        saved=session._agent_emit(name,payload);events[saved['sequence']]=(name,deepcopy(saved))
        if name=='RATE_PLAN':
            d=events[payload['decision_sequence']];io.require(d[0]=='WINDOW_DECISION' and payload['rate']==d[1]['declaration']['selected_rate'] and rate_witness is None,'declared gain not consumed')
            rate_witness=session.witness()
            if rate_count==0:witness('FIRST_RATE_PRE')
        if name=='RATE_COMMIT':
            io.require(rate_witness==session.witness() and pending is None,'rate choice changed world/noise/time')
            if rate_count==0:witness('FIRST_RATE_POST')
            rate_witness=None;rate_count+=1
        if name=='TASK_MEMORY_RETURN':witness('POST_ACQUISITION')
        if name in ('WINDOW_DECISION','ACQUISITION_CHOICE'):sync()
        return saved
    def step(saved):
        nonlocal pending,applied
        continuous();io.require(saved==session._pending,'unsaved physical command');sync()
        before=normalize(asdict(session.public()));current=session._agent_step(saved)
        history.append(dict(at_calls=saved['at_calls'],before=before,command=saved['command'],after=normalize(asdict(current))))
        if saved['raw_policy'] is not None:pending=None
        continuous()
        if session.ctx['calls']==spec['planned_boundary'] and session.alive():
            io.require(not applied,'repeated fault');before=session.witness();witness('INTERVENTION_PRE');old=deepcopy(session.fault);session.fault=a.destination(spec)
            io.require(before==session.witness(),'fault switch altered physical state')
            session.emit('FAULT_BOUNDARY',dict(logical_step=session.ctx['calls'],old_fault_oracle=old,new_fault_oracle=session.fault,before=before,after=session.witness()))
            witness('INTERVENTION_POST');applied=True
        return StepReceipt(current,session.ctx['calls'])
    row_initial=normalize(asdict(session.public()));provider=BehaviorProvider(a.schedule(spec))
    result=actor.run(spec['task'],session.public(),spec['planned_boundary'],spec['acquisition_action'],provider,policy,step,emit)
    continuous();outcome=result['outcome'];io.require(pending is None and session._pending is None and rate_witness is None,'unfinished command/rate')
    io.require(outcome['total_steps']==session.ctx['calls'] and outcome['policy_queries']==session.policy_queries and outcome['performance_windows']==rate_count,'actor/host counts')
    witness('FINAL');return {**outcome,'boundary_applied':applied}


def execute_case(spec,emit,emit_private,ledger,budget,position,sync):
    a.validate_spec(spec)
    from src.analysis.paired_probe_host_v1 import ProbeSession
    from src.rollout.task_registry import create_task_environment,create_task_policy
    from scripts.qualify_delayed_intervention_v2 import observe_state
    start=perf_counter_ns();env=session=None;refs=[]
    row={**spec,'completed':False,'error':None,'close_error':None,'environment_closed':False,'ledger_before':ledger.snapshot(),
        'initial_fault_oracle':a.initial_fault(),'destination_oracle':a.destination(spec),'state_witness_refs':refs}
    def witness(label):
        saved=observe_state(session,label,session.witness(),position,emit_private);w=saved['witness']
        refs.append(dict(label=label,sequence=saved['sequence'],logical_step=session.ctx['calls'],native_sha256=w['native_sha256'],comparison_python_sha256=w['comparison_python_sha256']))
    try:
        emit('FACTORY_INTENT',dict(ledger=ledger.snapshot()))
        with ledger.scope('FACTORY_SETUP'):env=create_task_environment(spec['task'],spec['seed'])
        emit('FACTORY_COMPLETE',dict(ledger=ledger.snapshot()))
        with ledger.scope('CONTROLLED_RESET'):initial,_=env.reset(seed=spec['seed'])
        session=ProbeSession(env,create_task_policy(spec['task']),initial,spec['task'],spec['seed'],row['initial_fault_oracle'],emit,ledger,budget)
        session.ctx['noise_rows']=a.noise(spec);session.branch=dict(role='OCCAM_REFERENCE_TRAIN_BEHAVIOR',future=0,program=spec['behavior'])
        emit('NOISE_COMMITMENT',dict(at_calls=0,noise_namespace_oracle=2026102832,tape_sha256_oracle=io.digest(session.ctx['noise_rows'].tolist())))
        row['initial']=normalize(asdict(session.public()));witness('INITIAL');row.update(run_live(spec,session,witness,sync))
        row['final']=normalize(asdict(session.public()));row['completed']=True
    except BaseException as error:row['error']=dict(type=type(error).__name__,message=str(error))
    finally:
        if session is not None:row.update(host_attempts=session.attempts,host_returned=session.completed,total_steps=session.ctx['calls'],policy_queries=session.policy_queries,
            captures=session.captures,restores=session.restores,physical_rows_count=len(session.last_rows))
        row['ledger_before_close']=ledger.snapshot()
        if env is not None:
            try:env.close();row['environment_closed']=True
            except BaseException as error:row['close_error']=dict(type=type(error).__name__,message=str(error))
        row['ledger_after_close']=ledger.snapshot();row['wall_ns']=perf_counter_ns()-start
    if row['error'] is not None or row['close_error'] is not None or not row['completed'] or not row['environment_closed']:raise CaseFailure(normalize(row))
    return normalize(row)
