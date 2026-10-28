"""Authentic fixed-bank deployment and unchanged legacy controls in one live world."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import traceback
import numpy as np
from src.analysis import occam_reference_qualification_io_v1 as a
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import occam_qualification_program_v1 as actor
from src.probe.physical_reprobe_v1 import StepReceipt
io=a.io


class CaseFailure(RuntimeError):
    def __init__(self,row):super().__init__(str(row.get('error')));self.record=row


def run_live(spec,session,witness,sync,provider,nominal,*,rng_guard=None,fit_counters=None):
    from src.analysis.occam_live_rng_guard_v1 import no_global_reseed
    a.validate_spec(spec);settings=actor.program_spec(spec['program']);legacy=settings['kind']=='LEGACY'
    base=session.env.unwrapped;addresses=(base.model._address,base.data._address);tape=session.ctx['noise_rows']
    clock=float(base.data.time);paid=session.run_budget['completed'];frames=session.ledger.counts.get('simulation_frames_completed',0)
    resets=session.ledger.counts.get('reset_attempts',0);history=[];pending=None;events={};applied=False;rate_witness=None;rates=0;integral=[0.,0.]
    initial=normalize(asdict(session.public()));fit_counters={} if fit_counters is None else fit_counters
    def continuous():
        n=session.ctx['calls'];io.require(session.env.unwrapped is base and (base.model._address,base.data._address)==addresses,'world identity changed')
        io.require(session.ctx['noise_rows'] is tape and not tape.flags.writeable and session.ledger.counts.get('reset_attempts',0)==resets,'noise replacement or within-task reset')
        io.require(n==session.attempts==session.completed==len(session.last_rows)==len(history)<=500,'actual history/noise cursor')
        io.require(session.run_budget['completed']-paid==n and session.ledger.counts.get('simulation_frames_completed',0)-frames==5*n,'actual physical cost')
        io.require(np.isclose(float(base.data.time)-clock,.0125*n,atol=1e-9,rtol=0) and not session.captures and not session.restores and not session._snapshots,'continuous time, no restoration')
    def policy(observation):
        nonlocal pending
        continuous();io.require(pending is None and np.array_equal(observation,session.public().observation),'stale or duplicate fixed-policy query')
        pending=session.policy_query(observation).tolist();return np.array(pending,np.float32)
    def emit(name,payload):
        nonlocal integral,rate_witness,rates
        continuous();io.require(payload['at_calls']==session.ctx['calls'] and session._pending is None,'stale event or unfinished command')
        if name=='FIT_INTENT':
            from src.probe.cold_start_response import ColdPrefix
            p=ColdPrefix.from_dict(payload['prefix'])
            io.require(legacy and np.array_equal(p.initial_observation,session.ctx['initial_observation'])
                and np.array_equal(p.commands,session.ctx['commands']) and np.array_equal(p.observations,session.ctx['observations']),'causal C4/C8 prefix only')
        if name=='WINDOW_QUERY':
            q=payload['value'];io.require(not legacy and q['initial']==initial and q['history']==history and q['integral_xy']==integral,'true public history only')
        if name=='WINDOW_DECISION':
            previous=events.get(payload['input_sequence']);d=payload['declaration']
            io.require(previous is not None and previous[0]=='WINDOW_QUERY' and payload['input_sequence']==len(events)-1
                and d['public_query_sha256']==io.digest(previous[1]['value']),'model decision after saved actual query')
        if name=='COMMAND':
            io.require(payload['before']==normalize(asdict(session.public())) and payload['raw_policy']==pending,'current observation and one actual raw query')
            parent=events.get(payload['decision_sequence']);io.require(parent is not None,'command requires saved parent')
            if pending is not None:
                if legacy:
                    from src.probe.operator_identification import encode_controller
                    io.require('controller' in parent[1] and np.array_equal(np.asarray(payload['command'],np.float32),encode_controller(parent[1]['controller'],pending)),'original saved C8 correction consumed')
                else:io.require(parent[0]=='PI_PLAN' and payload['command']==parent[1]['saved_plan']['pi_plan']['numbers']['sent_command'],'saved PI command consumed')
        if name=='TASK_MEMORY_COMMIT':integral=payload['memory']['integral_xy']
        saved=session._agent_emit(name,payload);events[saved['sequence']]=(name,deepcopy(saved))
        if name=='FIT_INTENT':fit_counters['fit_intents']=fit_counters.get('fit_intents',0)+1
        if name=='FIT_RESULT':
            fit_counters['fit_results']=fit_counters.get('fit_results',0)+1
            fit_counters['optimizer_nfev']=fit_counters.get('optimizer_nfev',0)+int(payload['fit'].get('nfev',0))
        if name=='RATE_PLAN':
            d=events[payload['decision_sequence']];io.require(d[0]=='WINDOW_DECISION' and payload['rate']==d[1]['declaration']['selected_rate'] and rate_witness is None,'saved model selection actually used')
            rate_witness=session.witness()
            if rates==0:witness('FIRST_RATE_PRE')
        if name=='RATE_COMMIT':
            io.require(rate_witness==session.witness() and pending is None,'parameter change altered world/RNG/time')
            if rates==0:witness('FIRST_RATE_POST')
            rate_witness=None;rates+=1
        if name=='RELOCATION_EVIDENCE':witness('POST_RELOCATION')
        if name in ('TASK_MEMORY_RETURN','POST_MOVE_TASK_ENTRY'):witness('POST_ACQUISITION')
        if name in ('WINDOW_DECISION','ACQUISITION_CHOICE','FIT_INTENT'):sync()
        return saved
    def step(saved):
        nonlocal pending,applied
        continuous();io.require(saved==session._pending,'only saved physical command');sync()
        before=normalize(asdict(session.public()));current=session._agent_step(saved)
        history.append(dict(at_calls=saved['at_calls'],before=before,command=saved['command'],after=normalize(asdict(current))))
        if saved['raw_policy'] is not None:pending=None
        continuous()
        if session.ctx['calls']==spec['planned_boundary'] and session.alive():
            io.require(not applied and pending is None,'repeated or pending fault boundary')
            w=session.witness();witness('INTERVENTION_PRE');old=deepcopy(session.fault);session.fault=a.destination(spec)
            io.require(w==session.witness(),'fault switch changed physical/RNG state')
            session.emit('FAULT_BOUNDARY',dict(logical_step=session.ctx['calls'],old_fault_oracle=old,new_fault_oracle=session.fault,before=w,after=session.witness()))
            witness('INTERVENTION_POST');applied=True
        return StepReceipt(current,session.ctx['calls'])
    guard={} if rng_guard is None else rng_guard
    with no_global_reseed(guard):
        result=actor.run_program(spec['task'],session.public(),spec['planned_boundary'],spec['program'],nominal,provider,policy,step,emit)
    continuous();o=result['outcome'];io.require(pending is None and session._pending is None and rate_witness is None,'unfinished operation')
    io.require(o['total_steps']==session.ctx['calls'] and o['policy_queries']==session.policy_queries,'actor/host counts')
    if not legacy:io.require(o['performance_windows']==rates,'all rate windows')
    witness('FINAL');return {**o,'boundary_applied':applied,'live_global_rng_guard':guard,
        'performance_windows':o.get('performance_windows',0),'full_feedback_windows':o.get('full_feedback_windows',0)}


def execute_case(spec,emit,emit_private,ledger,budget,position,sync):
    a.validate_spec(spec)
    from src.analysis.paired_probe_host_v1 import ProbeSession
    from src.rollout.task_registry import create_task_environment,create_task_policy
    from scripts.qualify_delayed_intervention_v2 import observe_state
    start=perf_counter_ns();env=session=provider=None;refs=[]
    row={**spec,'completed':False,'error':None,'close_error':None,'environment_closed':False,'ledger_before':ledger.snapshot(),
        'initial_fault_oracle':a.initial_fault(),'destination_oracle':a.destination(spec),'state_witness_refs':refs,'live_global_rng_guard':{},'legacy_fit_accounting':{}}
    def witness(label):
        saved=observe_state(session,label,session.witness(),position,emit_private);w=saved['witness']
        refs.append(dict(label=label,sequence=saved['sequence'],logical_step=session.ctx['calls'],native_sha256=w['native_sha256'],comparison_python_sha256=w['comparison_python_sha256']))
    try:
        provider=a.provider(spec);nominal=a.nominal(spec)
        emit('FACTORY_INTENT',dict(ledger=ledger.snapshot()))
        with ledger.scope('FACTORY_SETUP'):env=create_task_environment(spec['task'],spec['seed'])
        emit('FACTORY_COMPLETE',dict(ledger=ledger.snapshot()))
        with ledger.scope('CONTROLLED_RESET'):initial,_=env.reset(seed=spec['seed'])
        session=ProbeSession(env,create_task_policy(spec['task']),initial,spec['task'],spec['seed'],row['initial_fault_oracle'],emit,ledger,budget)
        session.ctx['noise_rows']=a.noise(spec);session.branch=dict(role='STANDARD_REFERENCE_OWN_HISTORY',future=0,program=spec['program'])
        emit('NOISE_COMMITMENT',dict(at_calls=0,noise_namespace_oracle=a.registry()['noise_namespace'],tape_sha256_oracle=io.digest(session.ctx['noise_rows'].tolist())))
        row['initial']=normalize(asdict(session.public()));witness('INITIAL')
        row.update(run_live(spec,session,witness,sync,provider,nominal,rng_guard=row['live_global_rng_guard'],fit_counters=row['legacy_fit_accounting']))
        row['final']=normalize(asdict(session.public()));row['completed']=True
    except BaseException as error:row['error']=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
    finally:
        row['filter_update_attempts']=getattr(provider,'update_attempts',0)
        if session is not None:row.update(host_attempts=session.attempts,host_returned=session.completed,total_steps=session.ctx['calls'],policy_queries=session.policy_queries,
            captures=session.captures,restores=session.restores,physical_rows_count=len(session.last_rows))
        row['ledger_before_close']=ledger.snapshot()
        if env is not None:
            try:env.close();row['environment_closed']=True
            except BaseException as error:row['close_error']=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
        row['ledger_after_close']=ledger.snapshot();row['wall_ns']=perf_counter_ns()-start
    if row['error'] is not None or row['close_error'] is not None or not row['completed'] or not row['environment_closed']:raise CaseFailure(normalize(row))
    return normalize(row)
