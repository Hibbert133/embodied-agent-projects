"""Native continuous host: authentic receipts, durable saved actions, no reset undo."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from src.analysis import memory_acquisition_io_v1 as allocation
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import memory_acquisition_program_v1 as actor
from src.probe.physical_reprobe_v1 import StepReceipt
io=allocation.io


class CaseFailure(RuntimeError):
    def __init__(self,record):super().__init__(str(record.get('error')));self.record=record


def run_live(spec,session,witness,sync):
    allocation.validate_spec(spec);base=session.env.unwrapped;addresses=(base.model._address,base.data._address)
    io.require(float(base.action_scale)==.01,'fixed command units')
    tape=session.ctx['noise_rows'];clock=float(base.data.time);paid=session.run_budget['completed']
    frames=session.ledger.counts.get('simulation_frames_completed',0)
    resets={k:session.ledger.counts.get(k,0) for k in ('reset_attempts','reset_completed','reset_errors')}
    history=[session.public().observation];pending=None;events={};applied=False
    def continuous():
        io.require(session.env.unwrapped is base and (base.model._address,base.data._address)==addresses,'world identity changed')
        io.require(session.ctx['noise_rows'] is tape and not tape.flags.writeable,'noise tape replaced')
        io.require(all(session.ledger.counts.get(k,0)==v for k,v in resets.items()),'mid-task reset')
        n=session.ctx['calls'];io.require(n==session.attempts==session.completed==len(session.last_rows)==len(history)-1,'history/noise cursor')
        io.require(n<=500 and session.run_budget['completed']-paid==n and session.ledger.counts.get('simulation_frames_completed',0)-frames==5*n,'whole cost continuity')
        io.require(np.isclose(float(base.data.time)-clock,.0125*n,atol=1e-9,rtol=0),'physical clock discontinuity')
        io.require(not session.captures and not session.restores and not session._snapshots,'state capture/restore forbidden')
    def intervene():
        nonlocal applied
        if session.ctx['calls']!=spec['planned_boundary'] or not session.alive():return
        io.require(not applied and pending is None and session._pending is None,'late/repeated private change')
        before=session.witness();witness('INTERVENTION_PRE');old=deepcopy(session.fault);session.fault=allocation.destination(spec)
        io.require(session.witness()==before,'parameter change altered world/RNG/clock')
        session.emit('FAULT_BOUNDARY',{'logical_step':session.ctx['calls'],'old_fault_oracle':old,'new_fault_oracle':session.fault,
            'changed_oracle':spec['context']=='CHANGED','before':before,'after':session.witness()})
        witness('INTERVENTION_POST');applied=True
    def policy(observation):
        nonlocal pending
        continuous();io.require(pending is None and np.array_equal(observation,session.public().observation),'duplicate/stale policy query')
        pending=session.policy_query(observation).tolist();return np.array(pending,np.float32)
    def emit(name,payload):
        continuous();io.require(payload['at_calls']==session.ctx['calls'] and session._pending is None,'stale event or pending action')
        if name=='ACQUISITION_CHOICE':
            io.require(payload['action']==spec['action'] and payload['at_calls']==spec['planned_boundary'],'unassigned acquisition choice')
            io.require(payload['behavior_probabilities']==[float(a==spec['action']) for a in actor.ACTIONS],'reported behavior probability changed')
        if name=='COMMAND':
            io.require(payload['before']==normalize(asdict(session.public())),'stale public command')
            required=payload['phase'] in ('PREFIX_TASK','VALIDATE_TASK','TAIL_TASK')
            io.require(required==(pending is not None) and payload['raw_policy']==pending,'one raw query per real task command')
            decision=events.get(payload['decision_sequence']);io.require(decision is not None,'unsaved physical decision')
            if required:
                io.require(decision[0]=='PI_PLAN' and payload['command']==decision[1]['saved_plan']['pi_plan']['numbers']['sent_command'],'saved PI plan not consumed')
        saved=session._agent_emit(name,payload);events[saved['sequence']]=(name,deepcopy(saved))
        if name=='TASK_MEMORY_RETURN':witness('POST_ACQUISITION')
        return saved
    def step(saved):
        nonlocal pending
        continuous();io.require(saved==session._pending,'unsaved or changed command');sync();continuous()
        current=session._agent_step(saved);history.append(current.observation)
        if saved['raw_policy'] is not None:pending=None
        continuous();intervene();return StepReceipt(current,session.ctx['calls'])
    result=actor.run(spec['task'],session.public(),spec['planned_boundary'],spec['action'],policy,step,emit)
    continuous();io.require(pending is None and session._pending is None,'unconsumed task command')
    io.require(result['outcome']['total_steps']==session.ctx['calls'] and result['outcome']['policy_queries']==session.policy_queries,'actor/host costs differ')
    witness('FINAL')
    return {**result['outcome'],'boundary_applied':applied,'boundary_missing_reason':None if applied else 'EARLY_SUCCESS' if session.public().success else 'ENVIRONMENT_ENDED'}


def execute_case(spec,emit,emit_private,ledger,budget,position,sync):
    allocation.validate_spec(spec)
    from src.analysis.paired_probe_host_v1 import ProbeSession
    from src.rollout.task_registry import create_task_environment,create_task_policy
    from scripts.qualify_delayed_intervention_v2 import observe_state
    start=perf_counter_ns();env=session=None;refs=[]
    row={**spec,'completed':False,'error':None,'close_error':None,'environment_closed':False,'ledger_before':ledger.snapshot(),
        'initial_fault_oracle':allocation.initial_fault(),'destination_oracle':allocation.destination(spec),'state_witness_refs':refs}
    def witness(label):
        saved=observe_state(session,label,session.witness(),position,emit_private);w=saved['witness']
        refs.append({'label':label,'sequence':saved['sequence'],'logical_step':session.ctx['calls'],'native_sha256':w['native_sha256'],'comparison_python_sha256':w['comparison_python_sha256']})
    try:
        emit('FACTORY_INTENT',{'ledger':ledger.snapshot()})
        with ledger.scope('FACTORY_SETUP'):env=create_task_environment(spec['task'],spec['seed'])
        emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
        with ledger.scope('CONTROLLED_RESET'):initial,_=env.reset(seed=spec['seed'])
        session=ProbeSession(env,create_task_policy(spec['task']),initial,spec['task'],spec['seed'],row['initial_fault_oracle'],emit,ledger,budget)
        session.ctx['noise_rows']=allocation.noise(spec['seed']);session.branch={'role':'MEMORY_ACQUISITION_NATIVE','future':0,'program':spec['action']}
        emit('NOISE_COMMITMENT',{'at_calls':0,'noise_namespace_oracle':140002,'tape_sha256_oracle':io.digest(session.ctx['noise_rows'].tolist())})
        row['initial']=normalize(asdict(session.public()));witness('INITIAL')
        row.update(run_live(spec,session,witness,sync));row['final']=normalize(asdict(session.public()));row['completed']=True
    except BaseException as error:row['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        if session is not None:row.update(host_attempts=session.attempts,host_returned=session.completed,total_steps=session.ctx['calls'],
            policy_queries=session.policy_queries,captures=session.captures,restores=session.restores,physical_rows_count=len(session.last_rows))
        row['ledger_before_close']=ledger.snapshot()
        if env is not None:
            try:env.close();row['environment_closed']=True
            except BaseException as error:row['close_error']={'type':type(error).__name__,'message':str(error)}
        row['ledger_after_close']=ledger.snapshot();row['wall_ns']=perf_counter_ns()-start
    if row['error'] is not None or row['close_error'] is not None or not row['completed'] or not row['environment_closed']:raise CaseFailure(normalize(row))
    return normalize(row)
