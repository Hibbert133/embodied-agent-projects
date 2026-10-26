"""Native host: one initial reset, immutable tape, forecasts before execution."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from src.analysis import correction_scope_io_v1 as a
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import correction_scope_program_v1 as actor
from src.probe.physical_reprobe_v1 import StepReceipt
io=a.io


class CaseFailure(RuntimeError):
    def __init__(self,row):super().__init__(str(row.get('error')));self.record=row


def run_live(spec,session,witness,sync,bank):
    a.validate_spec(spec);base=session.env.unwrapped;addresses=(base.model._address,base.data._address)
    io.require(float(base.action_scale)==.01,'working-model command units must be explicit')
    tape=session.ctx['noise_rows'];clock=float(base.data.time);paid=session.run_budget['completed']
    frames=session.ledger.counts.get('simulation_frames_completed',0)
    resets={k:session.ledger.counts.get(k,0) for k in ('reset_attempts','reset_completed','reset_errors')}
    history=[];pending=None;events={};applied=False;rate_witness=None;rate_pairs=0
    def continuous():
        io.require(session.env.unwrapped is base and (base.model._address,base.data._address)==addresses,'world identity changed')
        io.require(session.ctx['noise_rows'] is tape and not tape.flags.writeable,'noise tape replaced')
        io.require(all(session.ledger.counts.get(k,0)==v for k,v in resets.items()),'mid-task reset')
        n=session.ctx['calls'];io.require(n==session.attempts==session.completed==len(session.last_rows)==len(history),'physical/history/noise cursor discontinuity')
        io.require(n<=500 and session.run_budget['completed']-paid==n and session.ledger.counts.get('simulation_frames_completed',0)-frames==5*n,'complete cost continuity')
        io.require(np.isclose(float(base.data.time)-clock,.0125*n,atol=1e-9,rtol=0),'physical clock discontinuity')
        io.require(not session.captures and not session.restores and not session._snapshots,'physical restoration forbidden')
    def intervene():
        nonlocal applied
        if session.ctx['calls']!=spec['planned_boundary'] or not session.alive():return
        io.require(not applied and pending is None and session._pending is None,'late/repeated parameter change')
        before=session.witness();witness('INTERVENTION_PRE');old=deepcopy(session.fault);session.fault=a.destination(spec)
        io.require(before==session.witness(),'private parameter change altered physical/RNG state')
        session.emit('FAULT_BOUNDARY',dict(logical_step=session.ctx['calls'],old_fault_oracle=old,new_fault_oracle=session.fault,
            changed_oracle=spec['context']=='CHANGED',before=before,after=session.witness()))
        witness('INTERVENTION_POST');applied=True
    def policy(observation):
        nonlocal pending
        continuous();io.require(pending is None and np.array_equal(observation,session.public().observation),'duplicate/stale fixed-policy query')
        pending=session.policy_query(observation).tolist();return np.array(pending,np.float32)
    def emit(name,payload):
        nonlocal rate_witness,rate_pairs
        continuous();io.require(payload['at_calls']==session.ctx['calls'] and session._pending is None,'stale public event')
        if name=='FORECAST_INPUT':
            value=payload['value'];io.require(value['history']==history and value['memory']['current']==normalize(asdict(session.public())),'future/stale/nonfactual forecast history')
            io.require(value['acquisition_action']==spec['acquisition_action'] and value['time_constant_s']==spec['time_constant_s'],'changed assigned candidate')
        if name=='FORECAST':
            prior=events.get(payload['input_sequence']);io.require(prior is not None and prior[0]=='FORECAST_INPUT' and payload['input_sequence']==len(events)-1,'forecast input must be immediately saved')
            io.require((payload['forecast'] is None)==(bank is None),'missing/invented frozen model prediction')
            if bank is not None:io.require(payload['forecast']['bank_id']==bank['bank_id'] and payload['forecast']['input_sha256']==io.digest(prior[1]['value']),'model/input changed')
        if name=='COMMAND':
            io.require(payload['before']==normalize(asdict(session.public())),'stale public command')
            required=payload['phase'] in ('PREFIX_TASK','TAIL_TASK','VALIDATION_TASK')
            io.require(required==(pending is not None) and payload['raw_policy']==pending,'one raw fixed-policy query per actual task step')
            decision=events.get(payload['decision_sequence']);io.require(decision is not None,'unsaved command decision')
            if required:io.require(decision[0]=='PI_PLAN' and payload['command']==decision[1]['saved_plan']['pi_plan']['numbers']['sent_command'],'saved task command not consumed')
        saved=session._agent_emit(name,payload);events[saved['sequence']]=(name,deepcopy(saved))
        if name=='RATE_PLAN':
            io.require(rate_witness is None and pending is None,'pending rate transition');rate_witness=session.witness();witness('RATE_PRE')
        if name=='RATE_COMMIT':
            io.require(rate_witness is not None and rate_witness==session.witness() and pending is None,'rate transition changed world/RNG/time')
            io.require(events[payload['plan_sequence']][0]=='RATE_PLAN' and payload['memory']['time_constant_s']==spec['time_constant_s'],'saved rate not consumed')
            witness('RATE_POST');rate_witness=None;rate_pairs+=1
        if name in ('FORECAST','RATE_PLAN','ACQUISITION_CHOICE'):sync()
        if name=='RELOCATION_EVIDENCE':witness('POST_RELOCATION')
        if name=='TASK_MEMORY_RETURN':witness('POST_ACQUISITION')
        return saved
    def step(saved):
        nonlocal pending
        continuous();io.require(saved==session._pending,'unsaved or changed physical command');sync();continuous()
        before=normalize(asdict(session.public()));current=session._agent_step(saved)
        history.append(dict(at_calls=saved['at_calls'],before=before,command=saved['command'],after=normalize(asdict(current))))
        if saved['raw_policy'] is not None:pending=None
        continuous();intervene();return StepReceipt(current,session.ctx['calls'])
    result=actor.run(spec['task'],session.public(),spec['planned_boundary'],spec['acquisition_action'],spec['time_constant_s'],policy,step,emit,bank=bank)
    continuous();o=result['outcome'];io.require(pending is None and session._pending is None and rate_witness is None,'unclosed saved operations')
    io.require(o['total_steps']==session.ctx['calls'] and o['policy_queries']==session.policy_queries and rate_pairs==int(o['post_forecast'] is not None),'actor/host accounting')
    witness('FINAL');return {**o,'boundary_applied':applied}


def execute_case(spec,emit,emit_private,ledger,budget,position,sync,bank):
    a.validate_spec(spec)
    from src.analysis.paired_probe_host_v1 import ProbeSession
    from src.rollout.task_registry import create_task_environment,create_task_policy
    from scripts.qualify_delayed_intervention_v2 import observe_state
    start=perf_counter_ns();env=session=None;refs=[]
    row={**spec,'completed':False,'error':None,'close_error':None,'environment_closed':False,'ledger_before':ledger.snapshot(),
        'initial_fault_oracle':a.initial_fault(),'destination_oracle':a.destination(spec),'state_witness_refs':refs}
    def witness(label):
        saved=observe_state(session,label,session.witness(),position,emit_private);w=saved['witness']
        refs.append(dict(label=label,sequence=saved['sequence'],logical_step=session.ctx['calls'],
            native_sha256=w['native_sha256'],comparison_python_sha256=w['comparison_python_sha256']))
    try:
        emit('FACTORY_INTENT',dict(ledger=ledger.snapshot()))
        with ledger.scope('FACTORY_SETUP'):env=create_task_environment(spec['task'],spec['seed'])
        emit('FACTORY_COMPLETE',dict(ledger=ledger.snapshot()))
        with ledger.scope('CONTROLLED_RESET'):initial,_=env.reset(seed=spec['seed'])
        session=ProbeSession(env,create_task_policy(spec['task']),initial,spec['task'],spec['seed'],row['initial_fault_oracle'],emit,ledger,budget)
        session.ctx['noise_rows']=a.noise(spec);session.branch=dict(role='CORRECTION_SCOPE_A1',future=0,program=spec['acquisition_action']+'_T'+str(spec['time_constant_s']))
        emit('NOISE_COMMITMENT',dict(at_calls=0,noise_namespace_oracle=202610262,tape_sha256_oracle=io.digest(session.ctx['noise_rows'].tolist())))
        row['initial']=normalize(asdict(session.public()));witness('INITIAL')
        row.update(run_live(spec,session,witness,sync,bank));row['final']=normalize(asdict(session.public()));row['completed']=True
    except BaseException as error:row['error']=dict(type=type(error).__name__,message=str(error))
    finally:
        if session is not None:row.update(host_attempts=session.attempts,host_returned=session.completed,total_steps=session.ctx['calls'],
            policy_queries=session.policy_queries,captures=session.captures,restores=session.restores,physical_rows_count=len(session.last_rows))
        row['ledger_before_close']=ledger.snapshot()
        if env is not None:
            try:env.close();row['environment_closed']=True
            except BaseException as error:row['close_error']=dict(type=type(error).__name__,message=str(error))
        row['ledger_after_close']=ledger.snapshot();row['wall_ns']=perf_counter_ns()-start
    if row['error'] is not None or row['close_error'] is not None or not row['completed'] or not row['environment_closed']:raise CaseFailure(normalize(row))
    return normalize(row)
