"""Actual one-reset prefix replay and saved-plan command consumption.

Native imports are lazy. Tests supply array-only sessions and create no worlds.
The historical fixed C8/movement program is interrupted before its target command.
"""
from copy import deepcopy
from dataclasses import dataclass,asdict
from time import perf_counter_ns
import numpy as np
from src.analysis import command_contrast_io_v1 as allocation
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import command_contrast_v1 as core
from src.probe.continuous import StepObservation


class CaseFailure(RuntimeError):
    def __init__(self,record): super().__init__(str(record.get('error'))); self.record=record


class AtContrast(Exception):
    def __init__(self,payload): self.payload=deepcopy(payload)


@dataclass(frozen=True)
class Reference:
    unit_id: str
    plan: object
    plan_sequence: object
    prefix_digest: str
    comparison_signature: tuple
    missing_reason: object


def physical_prefix_digest(rows):
    fields=('logical_step','phase','command','executed_action_oracle','after','noise_cursor_after',
            'simulation_time_before','simulation_time_after')
    return allocation.io.digest([{k:r[k] for k in fields} for r in rows])


def run_live_prefix(spec,nominal,models,session,take_witness,sync,reference=None):
    from src.probe import observable_history_behavior_v1 as behavior
    from src.probe.cold_start_response import ColdPrefix
    io=allocation.io; allocation.validate_spec(spec)
    io.require(reference is None or (type(reference) is Reference and reference.unit_id==spec['unit_id']),
               'saved reference belongs to another allocated unit')
    base=session.env.unwrapped; addresses=(base.model._address,base.data._address)
    tape=session.ctx['noise_rows']; start_clock=float(base.data.time)
    initial_budget=session.run_budget['completed']; initial_frames=session.ledger.counts.get('simulation_frames_completed',0)
    reset_counts={k:session.ledger.counts.get(k,0) for k in ('reset_attempts','reset_completed','reset_errors')}
    initial=session.public(); history=[initial.observation]; pending_raw=None; events=[]; target=None

    def continuous():
        io.require(session.env.unwrapped is base and (base.model._address,base.data._address)==addresses,'world identity changed')
        io.require(session.ctx['noise_rows'] is tape and not tape.flags.writeable,'noise replaced after initial setup')
        io.require(all(session.ledger.counts.get(k,0)==v for k,v in reset_counts.items()),'reset after controlled initial reset')
        n=session.ctx['calls']; io.require(n==session.completed==session.attempts==len(session.last_rows)==len(history)-1,'physical/history cursor mismatch')
        io.require(n<=spec['maximum_steps']<=137 and n<=500,'per-branch budget')
        io.require(session.run_budget['completed']-initial_budget==n and
                   session.ledger.counts.get('simulation_frames_completed',0)-initial_frames==5*n,'control/frame ledger discontinuity')
        io.require(np.isclose(float(base.data.time)-start_clock,.0125*n,rtol=0,atol=1e-9),'continuous clock violated')
        io.require(not session.captures and not session.restores and not session._snapshots,'no state copying/restoration')

    def policy(observation):
        nonlocal pending_raw
        continuous(); io.require(pending_raw is None and np.array_equal(observation,session.public().observation),'duplicate/stale fixed-policy query')
        pending_raw=session.policy_query(observation).tolist(); return np.array(pending_raw,np.float32)

    def emit(name,payload):
        continuous(); io.require(payload['at_calls']==session.ctx['calls'] and session._pending is None,'stale prefix event')
        if name=='PROGRAM':
            io.require(payload['measurement_program']==spec['measurement_program'] and payload['boundary']==spec['planned_boundary']
                       and payload['balanced_actions']==allocation.measurement(spec),'changed fixed source program')
        if name=='FIT_INTENT':
            p=ColdPrefix.from_dict(payload['prefix'])
            io.require(p.initial_observation==initial.observation and np.array_equal(p.commands,session.ctx['commands'])
                       and np.array_equal(p.observations,session.ctx['observations']),'fit used noncausal history')
        if name=='COMMAND':
            io.require(payload['before']==normalize(asdict(session.public())) and payload['decision_sequence']<len(events),'unsaved/stale prefix command')
            required=payload['phase'] in ('POLICY','MEASURE_FEEDBACK','TASK_AFTER_MEASUREMENT')
            io.require((pending_raw is not None)==required and payload['raw_policy']==pending_raw,'one original policy query per policy command')
            if core.reaches_target(spec['target'],payload): raise AtContrast(payload)
        saved=session._agent_emit(name,normalize(payload)); events.append({'kind':name,'payload':deepcopy(saved)}); return saved

    def step(saved):
        nonlocal pending_raw
        continuous(); io.require(session.ctx['calls']<spec['maximum_steps'] and saved==session._pending
            and session.run_budget['completed']<session.run_budget['maximum'],'unsaved/exhausted physical step')
        after=session._agent_step(saved); io.require(type(after) is StepObservation,'wrong physical acknowledgement')
        history.append(after.observation)
        if saved['raw_policy'] is not None: pending_raw=None
        continuous(); return after

    result=None
    try:
        result=behavior.run(spec['task'],initial,nominal,spec['planned_boundary'],spec['measurement_program'],
                            allocation.measurement(spec),policy,step,emit)
    except AtContrast as reached: target=reached.payload
    continuous()
    prefix_digest=physical_prefix_digest(session.last_rows)
    prefix_event_count=len(events)
    fits=[e['payload']['fit'] for e in events if e['kind']=='FIT_RESULT']
    fitting={'c4_c8_fit_attempts':sum(e['kind']=='FIT_INTENT' for e in events),'c4_c8_fit_results':len(fits),
             'c4_c8_optimizer_nfev':sum(int(f.get('nfev',0)) for f in fits)}
    if target is None:
        io.require(pending_raw is None and session._pending is None,'unconsumed command without a query')
        outcome=result['outcome']; reason=('EARLY_SUCCESS' if outcome['success'] else
            'ENVIRONMENT_ENDED' if outcome['terminated'] or outcome['truncated'] else outcome['stop_reason'])
        proof=take_witness('NO_QUERY_END')
        if spec['action_id']!='BASELINE':
            io.require(type(reference) is Reference and reference.plan is None and reference.prefix_digest==prefix_digest
                       and reference.comparison_signature==proof and reference.missing_reason==reason,'unpaired unavailable branch')
        ref=Reference(spec['unit_id'],None,None,prefix_digest,proof,reason)
        return {**fitting,'query_available':False,'missing_reason':reason,'prefix_outcome':outcome,'prefix_event_count':prefix_event_count,
                'total_steps':session.ctx['calls'],'plan_sequence':None,'plan_sha256':None,'selected_action':None},ref

    io.require(session.alive() and session.ctx['calls']>=2,'live query point and real history required')
    before_proof=take_witness('QUERY_PRE')
    query=core.PhysicalQuery.create(spec['task'],session.ctx['calls'],history[-3:],target['command'])
    unchanged=session.witness()
    if spec['action_id']=='BASELINE':
        io.require(reference is None,'reference branch cannot consume an earlier unit')
        plan=core.SavedPlan.build(query,models)
        event=session.emit('UNIT_PLAN_COMMITTED',{'unit_id':spec['unit_id'],'plan':plan.to_dict(),'plan_sha256':plan.digest(),
            'target':spec['target'],'source_phase':target['phase'],'at_calls':session.ctx['calls']})
        sync(); plan_sequence=event['sequence']
        ref=Reference(spec['unit_id'],plan,plan_sequence,prefix_digest,before_proof,None)
    else:
        io.require(type(reference) is Reference and type(reference.plan) is core.SavedPlan,'no late plan or baseline substitution')
        io.require(reference.prefix_digest==prefix_digest and reference.comparison_signature==before_proof,'common physical prefix differs')
        io.require(reference.plan.query==query,'actual current input differs from pre-outcome saved plan')
        ref=reference; plan=reference.plan; plan_sequence=reference.plan_sequence
        session.emit('UNIT_PLAN_REUSED',{'unit_id':spec['unit_id'],'plan_sequence':plan_sequence,'plan_sha256':plan.digest(),'at_calls':session.ctx['calls']})
    io.require(session.witness()==unchanged,'prediction/retrieval changed state, RNG or time')
    remaining=min(500-session.ctx['calls'],spec['maximum_steps']-session.ctx['calls'],session.run_budget['maximum']-session.run_budget['completed'])
    selection=core.PlanConsumer(plan).consume(query,spec['action_id'],remaining)
    chosen=session._agent_emit('CONTRAST_CHOICE',{'at_calls':session.ctx['calls'],'selection':selection,'plan_sequence':plan_sequence})
    command=session._agent_emit('COMMAND',{'at_calls':session.ctx['calls'],'phase':'CONTRAST_QUERY','decision_sequence':chosen['sequence'],
        'before':asdict(session.public()),'command':selection['sent_command'],'raw_policy':target['raw_policy'],
        'measurement_desired':None,'source_phase':target['phase'],'plan_sha256':plan.digest()})
    sync(); before_calls=session.ctx['calls']; step(deepcopy(command))
    io.require(session.ctx['calls']==before_calls+1 and session.last_rows[-1]['command']==selection['sent_command'],'saved branch did not drive exact execution')
    io.require(pending_raw is None and session._pending is None,'unconsumed policy/command after query')
    continuous(); take_witness('FINAL')
    return {**fitting,'query_available':True,'missing_reason':None,'prefix_event_count':prefix_event_count,'total_steps':session.ctx['calls'],
            'query_step':before_calls,'source_phase':target['phase'],'plan_sequence':plan_sequence,'plan_sha256':plan.digest(),
            'selected_action':selection['action_id'],'selection_sequence':chosen['sequence'],'command_sequence':command['sequence'],
            'before_observation':list(query.observations[-1]),'after_observation':list(session.public().observation),
            'stop_reason':'ONE_STEP_CONTRAST_COMPLETE','physical_qualification':False,'task_benefit':False},ref


def execute_case(spec,nominal,models,emit,emit_private,ledger,budget,position,sync,reference=None,dependencies=None):
    """The caller instruments lifecycle classes and enforces the global storage gate."""
    allocation.validate_spec(spec); io=allocation.io
    if dependencies is None:
        from src.analysis.paired_probe_host_v1 import ProbeSession
        from src.rollout.task_registry import create_task_environment,create_task_policy
        from scripts.qualify_delayed_intervention_v2 import observe_state
        dependencies={'environment':create_task_environment,'policy':create_task_policy,'session':ProbeSession,'observe':observe_state}
    started=perf_counter_ns(); env=session=None; refs=[]; output_reference=None
    row={**spec,'completed':False,'error':None,'close_error':None,'environment_closed':False,
         'ledger_before':ledger.snapshot(),'fault_oracle':allocation.fault(spec),'state_witness_refs':refs,
         'physical_qualification':False,'task_benefit':False}
    counted={'c4_c8_fit_attempts':0,'c4_c8_fit_results':0,'c4_c8_optimizer_nfev':0}
    def public_emit(name,payload):
        if name=='AGENT_EVENT':
            if payload['agent_event']=='FIT_INTENT': counted['c4_c8_fit_attempts']+=1
            if payload['agent_event']=='FIT_RESULT':
                counted['c4_c8_fit_results']+=1
                counted['c4_c8_optimizer_nfev']+=int(payload['public_payload']['fit'].get('nfev',0))
        return emit(name,payload)
    def take_witness(label):
        expected=session.witness()
        saved=dependencies['observe'](session,label,expected,position,emit_private)
        value=saved['witness']
        refs.append({'label':label,'sequence':saved['sequence'],'native_sha256':value['native_sha256'],
                     'comparison_python_sha256':value['comparison_python_sha256'],'logical_step':session.ctx['calls']})
        return (value['native_sha256'],value['comparison_python_sha256'],expected['noise_past_sha256'],expected['simulation_time'])
    try:
        emit('FACTORY_INTENT',{'ledger':ledger.snapshot()})
        with ledger.scope('FACTORY_SETUP'): env=dependencies['environment'](spec['task'],spec['seed'])
        emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
        with ledger.scope('CONTROLLED_RESET'): initial,_=env.reset(seed=spec['seed'])
        session=dependencies['session'](env,dependencies['policy'](spec['task']),initial,spec['task'],spec['seed'],row['fault_oracle'],public_emit,ledger,budget)
        session.ctx['noise_rows']=allocation.noise(spec['seed'],spec['noise_namespace'])
        session.branch={'role':'FIXED_COMMAND_CONTRAST_QUALIFICATION','future':0,'program':spec['measurement_program']}
        emit('NOISE_COMMITMENT',{'at_calls':0,'noise_namespace_oracle':spec['noise_namespace'],
            'tape_sha256_oracle':io.digest(session.ctx['noise_rows'].tolist())})
        row['initial']=normalize(asdict(session.public())); take_witness('INITIAL')
        outcome,output_reference=run_live_prefix(spec,nominal,models,session,take_witness,sync,reference)
        row.update(outcome)
        io.require(all(row[k]==v for k,v in counted.items()),'prefix fit accounting differs')
        row['final']=normalize(asdict(session.public())); row['completed']=True
    except BaseException as error: row['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        row.update(counted)
        if session is not None:
            row.update(host_attempts=session.attempts,host_returned=session.completed,total_steps=session.ctx['calls'],
                policy_queries=session.policy_queries,captures=session.captures,restores=session.restores,
                physical_rows_count=len(session.last_rows))
        row['ledger_before_close']=ledger.snapshot()
        if env is not None:
            try: env.close(); row['environment_closed']=True
            except BaseException as error: row['close_error']={'type':type(error).__name__,'message':str(error)}
        row['ledger_after_close']=ledger.snapshot(); row['wall_ns']=perf_counter_ns()-started
        row['computation_counters_complete']=row['completed'] and counted['c4_c8_fit_attempts']==counted['c4_c8_fit_results']
    if row['error'] is not None or row['close_error'] is not None or not row['completed'] or not row['environment_closed']:
        raise CaseFailure(normalize(row))
    return normalize(row),output_reference
