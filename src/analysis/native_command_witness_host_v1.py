"""Qualified fixed public actor with read-only evaluator-native witnesses."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from src.analysis import native_command_witness_io_v1 as a
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import acquisition_reference_program_v1 as actor
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe.nominal_command_target_v1 import PublicNominalTarget,finite_vector,INITIAL,LOW,HIGH
io=a.io


def public_prefix(trajectory,at):
    """No access to responses or fields at indices >= the completed clock."""
    io.require(type(trajectory) is dict and set(trajectory)=={'schema','task','initial_observation','steps'}
        and trajectory['schema']=='PUBLIC_COMMAND_WITNESS_TRAJECTORY_V1','strict public trajectory')
    io.require(type(at) is int and type(trajectory['steps']) is list and 0<=at<=500 and at<=len(trajectory['steps']),'completed public clock')
    initial=list(finite_vector(trajectory['initial_observation'],39));current=initial
    reference=PublicNominalTarget.initial(trajectory['task'],controlled_reset_declared=True);commands=[];observations=[]
    for i,row in enumerate(trajectory['steps'][:at]):
        io.require(set(row)=={'logical_step','command','observation_before','observation_after','reference_after'} and row['logical_step']==i,'strict completed public row')
        before=list(finite_vector(row['observation_before'],39));after=list(finite_vector(row['observation_after'],39))
        io.require(before==current,'causal observation history');reference=reference.consume(reference.propose(row['command']))
        io.require(reference.to_dict()==row['reference_after'],'public reference from sent inputs only')
        commands.append(list(row['command']));observations.append(after);current=after
    return {'task':trajectory['task'],'completed_steps':at,'initial_observation':initial,'past_commands':commands,
        'past_observations':observations,'current_observation':current,'nominal_reference':reference.to_dict()}


def native_values(session,label,position):
    """This function never returns a value to the actor or public export."""
    base=session.env.unwrapped;q=np.array(base.data.mocap_pos,copy=True);quat=np.array(base.data.mocap_quat,copy=True)
    io.require(q.shape==(1,3) and quat.shape==(1,4) and q.dtype==np.float64 and np.isfinite(q).all() and np.isfinite(quat).all(),'native target layout')
    return normalize({'label':label,'at_calls':session.ctx['calls'],'mocap_pos_oracle':q,'mocap_quat_oracle':quat,
        'mocap_dtype_oracle':q.dtype.str,'simulation_time':float(base.data.time),'native_signature_oracle':session.witness(),
        'last_public_event':position(),'model_address_oracle':int(base.model._address),'data_address_oracle':int(base.data._address),
        'evaluator_only':True,'permitted_training_input_or_label':False})


def run_live(spec,session,private,emit_outer,position,sync):
    a.validate_spec(spec);base=session.env.unwrapped;addresses=(base.model._address,base.data._address);tape=session.ctx['noise_rows']
    initial_time=float(base.data.time);paid=session.run_budget['completed'];frames=session.ledger.counts['simulation_frames_completed'];resets=session.ledger.counts['reset_attempts']
    io.require(float(base.action_scale)==.01 and np.array_equal(base.mocap_low,LOW) and np.array_equal(base.mocap_high,HIGH),'declared installed public priors')
    io.require(np.array_equal(base.data.mocap_pos,np.array([INITIAL])),'declared initial target must be independently observed')
    state=PublicNominalTarget.initial(spec['task'],controlled_reset_declared=True);public_rows=[];pending=None;events={};boundary=False
    def witness(label):return private('NATIVE_TARGET_VALUES',native_values(session,label,position))
    def continuous():
        n=session.ctx['calls'];io.require((base.model._address,base.data._address)==addresses and session.ctx['noise_rows'] is tape,'native world or noise replaced')
        io.require(session.ledger.counts['reset_attempts']==resets and not session.captures and not session.restores and not session._snapshots,'reset/restore after initial forbidden')
        io.require(n<=500 and session.run_budget['completed']-paid==n and session.ledger.counts['simulation_frames_completed']-frames==5*n,'whole physical cost continuity')
        io.require(np.isclose(float(base.data.time)-initial_time,.0125*n,atol=1e-9,rtol=0),'physical clock continuity')
    def intervene():
        nonlocal boundary
        if session.ctx['calls']!=spec['planned_boundary'] or not session.alive():return
        io.require(not boundary and pending is None and session._pending is None,'late or repeated fault boundary')
        before=session.witness();old=deepcopy(session.fault);session.fault=a.destination(spec)
        io.require(session.witness()==before,'private fault change must not change native state/RNG/clock')
        emit_outer('FAULT_BOUNDARY',{'logical_step':session.ctx['calls'],'old_fault_oracle':old,'new_fault_oracle':session.fault,
            'before':before,'after':session.witness()});boundary=True
    def query(obs):
        nonlocal pending
        continuous();io.require(pending is None and np.array_equal(obs,session.public().observation),'one policy query from current observation')
        pending=session.policy_query(obs).tolist();return np.asarray(pending,np.float32)
    def emit(kind,payload):
        continuous();io.require(payload['at_calls']==session.ctx['calls'] and session._pending is None,'causal public actor event')
        io.require(kind not in ('FIT_INTENT','FIT_RESULT'),'native phase forbids fits')
        if kind=='COMMAND':
            io.require(payload['before']==normalize(asdict(session.public())),'actual public observation required')
            task=payload['phase'] in ('PREFIX_TASK','TAIL_TASK');io.require(task==(pending is not None) and payload['raw_policy']==pending,'raw policy query budget')
            prior=events.get(payload['decision_sequence']);io.require(prior is not None,'saved earlier decision required')
            if task:io.require(prior[0]=='PI_PLAN' and payload['command']==prior[1]['saved_plan']['pi_plan']['numbers']['sent_command'],'saved plan must drive execution')
        saved=session._agent_emit(kind,payload);events[saved['sequence']]=(kind,deepcopy(saved));return saved
    def step(saved):
        nonlocal pending,state
        continuous();io.require(saved==session._pending,'unsaved/changed public command')
        before=list(session.public().observation);plan=state.propose(saved['command'])
        declared=emit_outer('PUBLIC_SENT_TARGET_PLAN',{'at_calls':session.ctx['calls'],'actor_command_sequence':session._map[saved['sequence']],'plan':plan})
        io.require(io.digest(declared['plan'])==io.digest(plan),'changed public target plan acknowledgement')
        witness('BEFORE_STEP');sync();current=session._agent_step(saved);witness('AFTER_STEP')
        state=state.consume(declared['plan']);emit_outer('PUBLIC_SENT_TARGET_COMMIT',{'at_calls':session.ctx['calls'],'plan_sequence':declared['sequence'],'reference':state.to_dict()})
        public_rows.append({'logical_step':len(public_rows),'command':list(saved['command']),'observation_before':before,
            'observation_after':list(current.observation),'reference_after':state.to_dict()})
        if saved['raw_policy'] is not None:pending=None
        continuous();intervene();return StepReceipt(current,session.ctx['calls'])
    witness('INITIAL');initial=list(session.public().observation)
    result=actor.run(spec['task'],session.public(),spec['planned_boundary'],spec['program'],None,query,step,emit)
    continuous();io.require(pending is None and session._pending is None and state.completed_commands==session.ctx['calls'],'unconsumed command or policy query')
    io.require(result['outcome']['total_steps']==session.ctx['calls'] and result['outcome']['policy_queries']==session.policy_queries,'host/actor accounting')
    witness('FINAL');public={'schema':'PUBLIC_COMMAND_WITNESS_TRAJECTORY_V1','task':spec['task'],'initial_observation':initial,'steps':public_rows}
    public_prefix(public,len(public_rows))
    return result['outcome']|{'boundary_applied':boundary},public


class CaseFailure(RuntimeError):
    def __init__(self,record):super().__init__(str(record.get('error')));self.record=record


def execute_case(spec,emit,private,ledger,budget,position,sync):
    from src.analysis.paired_probe_host_v1 import ProbeSession
    from src.rollout.task_registry import create_task_environment,create_task_policy
    a.validate_spec(spec);start=perf_counter_ns();env=session=None;public=None
    row={**spec,'completed':False,'error':None,'close_error':None,'environment_closed':False,'ledger_before':ledger.snapshot(),
        'initial_fault_oracle':a.initial_fault(),'destination_oracle':a.destination(spec)}
    try:
        emit('FACTORY_INTENT',{'ledger':ledger.snapshot()})
        with ledger.scope('FACTORY_SETUP'):env=create_task_environment(spec['task'],spec['seed'])
        emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
        with ledger.scope('CONTROLLED_RESET'):initial,_=env.reset(seed=spec['seed'])
        session=ProbeSession(env,create_task_policy(spec['task']),initial,spec['task'],spec['seed'],row['initial_fault_oracle'],emit,ledger,budget)
        session.ctx['noise_rows']=a.noise(spec);session.branch={'role':'NATIVE_COMMAND_TARGET_WITNESS','future':0,'program':spec['program']}
        emit('NOISE_COMMITMENT',{'at_calls':0,'tape_sha256_oracle':io.digest(session.ctx['noise_rows'].tolist()),'noise_namespace_oracle':2026102301})
        row['initial']=normalize(asdict(session.public()));outcome,public=run_live(spec,session,private,emit,position,sync)
        row.update(outcome);row['final']=normalize(asdict(session.public()));row['completed']=True
    except BaseException as error:row['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        if session is not None:row.update(total_steps=session.ctx['calls'],host_attempts=session.attempts,host_returned=session.completed,
            policy_queries=session.policy_queries,captures=session.captures,restores=session.restores)
        row['ledger_before_close']=ledger.snapshot()
        if env is not None:
            try:env.close();row['environment_closed']=True
            except BaseException as error:row['close_error']={'type':type(error).__name__,'message':str(error)}
        row['ledger_after_close']=ledger.snapshot();row['wall_ns']=perf_counter_ns()-start
    if row['error'] is not None or row['close_error'] is not None or not row['completed'] or not row['environment_closed']:raise CaseFailure(normalize(row))
    return normalize(row),public
