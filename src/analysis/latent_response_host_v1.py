"""Continuous physical host; compact evaluator witnesses and causal forecasts."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from src.analysis import latent_response_io_v1 as a
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import latent_response_packet_v1 as actor
from src.probe.latent_response_query_v1 import make_query,METHODS
from src.probe.latent_response_model_v1 import predict
from src.probe.nominal_command_target_v1 import PublicNominalTarget,INITIAL,LOW,HIGH
from src.probe.physical_reprobe_v1 import StepReceipt
io=a.io


def native_values(session,label,position):
    base=session.env.unwrapped;q=np.array(base.data.mocap_pos,copy=True);quat=np.array(base.data.mocap_quat,copy=True)
    io.require(q.shape==(1,3) and q.dtype==np.float64 and quat.shape==(1,4) and np.isfinite(q).all() and np.isfinite(quat).all(),'native array layout')
    full=label in ('INITIAL','FINAL')
    return normalize({'label':label,'at_calls':session.ctx['calls'],'mocap_pos_oracle':q,'mocap_quat_oracle':quat,
        'simulation_time':float(base.data.time),'mocap_dtype_oracle':q.dtype.str,'model_address_oracle':int(base.model._address),'data_address_oracle':int(base.data._address),
        'last_public_event':position(),'signature_scope':'PHASE_BOUNDARY' if full else 'NUMERIC_ONLY',
        'native_signature_oracle':session.witness() if full else None,'evaluator_only':True,'permitted_training_input_or_label':False})


def run_live(spec,session,emit,private,position,sync,model_bank=None,model_sha=None):
    a.validate_spec(spec);base=session.env.unwrapped;addresses=(base.model._address,base.data._address);tape=session.ctx['noise_rows']
    initial_time=float(base.data.time);paid=session.run_budget['completed'];frames=session.ledger.counts['simulation_frames_completed'];resets=session.ledger.counts['reset_attempts']
    cap=a.limits(spec['split'])['per_case_control_cap']
    io.require(float(base.action_scale)==.01 and np.array_equal(base.mocap_low,LOW) and np.array_equal(base.mocap_high,HIGH)
        and np.array_equal(base.data.mocap_pos,np.array([INITIAL])),'qualified public reset/input priors')
    reference=PublicNominalTarget.initial(spec['task'],controlled_reset_declared=True);pending=None;events={};rows=[];boundary_applied=False
    initial=list(session.public().observation);public={'schema':'PUBLIC_COMMAND_WITNESS_TRAJECTORY_V1','task':spec['task'],'initial_observation':initial,'steps':rows}
    def snapshot(label):return private('NATIVE_TARGET_VALUES',native_values(session,label,position))
    def continuous():
        n=session.ctx['calls'];io.require((base.model._address,base.data._address)==addresses and session.ctx['noise_rows'] is tape,'world or noise replaced')
        io.require(not session.captures and not session.restores and not session._snapshots and session.ledger.counts['reset_attempts']==resets,'no capture/restore/reset')
        io.require(n<=cap and session.run_budget['completed']-paid==n
            and session.ledger.counts['simulation_frames_completed']-frames==5*n,'registered continuous physical budget')
        io.require(np.isclose(float(base.data.time)-initial_time,.0125*n,atol=1e-9,rtol=0),'actual physical clock')
    def intervene():
        nonlocal boundary_applied
        if session.ctx['calls']!=spec['boundary'] or not session.alive():return
        io.require(not boundary_applied and pending is None and session._pending is None,'single causal fault boundary')
        before=session.witness();old=deepcopy(session.fault);session.fault=a.destination(spec)
        io.require(session.witness()==before,'fault change altered state/RNG/clock')
        emit('FAULT_BOUNDARY',{'logical_step':session.ctx['calls'],'old_fault_oracle':old,'new_fault_oracle':session.fault,'before':before,'after':session.witness()});boundary_applied=True
    def query(obs):
        nonlocal pending
        continuous();io.require(pending is None and np.array_equal(obs,session.public().observation),'one fixed-policy query at current observation')
        pending=session.policy_query(obs).tolist();return np.array(pending,np.float32)
    def saved_event(kind,payload):
        continuous();io.require(payload['at_calls']==session.ctx['calls'] and session._pending is None,'actual actor clock and no unconsumed command')
        if kind=='PROGRAM':io.require(payload['actions']==a.packet(spec),'preallocated packet declared before its responses')
        if kind=='COMMAND':
            io.require(payload['before']==normalize(asdict(session.public())),'real current observation')
            task=payload['phase']=='PREFIX_TASK';io.require(task==(pending is not None) and payload['raw_policy']==pending,'actual fixed-policy query budget')
            prior=events.get(payload['decision_sequence']);io.require(prior is not None,'saved earlier command decision')
            if task:io.require(prior[0]=='PI_PLAN' and payload['command']==prior[1]['saved_plan']['pi_plan']['numbers']['sent_command'],'saved task plan drives command')
            elif payload['phase']=='EXOGENOUS_PACKET':io.require(prior[0]=='PACKET_COMMAND_CHOICE' and payload['command']==prior[1]['command'],'saved exogenous choice drives command')
        value=session._agent_emit(kind,payload);events[value['sequence']]=(kind,deepcopy(value));return value
    def forecast(request):
        io.require(events.get(request['sequence'])==('FORECAST_REQUEST',request) and request['at_calls']==len(rows),'saved forecast request before packet')
        q=make_query(public,len(rows),request['planned_commands']);start=perf_counter_ns();result={}
        if spec['split'] in ('CAL','QUAL'):
            io.require(model_bank is not None and model_sha is not None,'locked model before CAL/QUAL')
            for method in METHODS:
                try:result[method]={'valid':True,'displacements':predict(model_bank[spec['task']][method],[q])[0].tolist()}
                except BaseException as error:result[method]={'valid':False,'error':{'type':type(error).__name__,'message':str(error)}}
        return {'query':q.to_dict(),'query_sha256':io.digest(q.to_dict()),'model_sha256':model_sha,'forecasts':result,
            'forecast_scope':'PREDECLARED_FUTURE_COMMANDS_NO_FUTURE_OBSERVATIONS','compute_wall_ns':perf_counter_ns()-start}
    def step(saved):
        nonlocal reference,pending
        continuous();io.require(saved==session._pending,'saved command must be consumed')
        before=list(session.public().observation);plan=reference.propose(saved['command'])
        declaration=emit('PUBLIC_SENT_TARGET_PLAN',{'at_calls':len(rows),'actor_command_sequence':session._map[saved['sequence']],'plan':plan})
        io.require(io.digest(plan)==io.digest(declaration['plan']),'unchanged nominal-summary acknowledgement')
        snapshot('BEFORE_STEP');sync();current=session._agent_step(saved);snapshot('AFTER_STEP');reference=reference.consume(declaration['plan'])
        emit('PUBLIC_SENT_TARGET_COMMIT',{'at_calls':session.ctx['calls'],'plan_sequence':declaration['sequence'],'reference':reference.to_dict()})
        rows.append({'logical_step':len(rows),'command':list(saved['command']),'observation_before':before,'observation_after':list(current.observation),'reference_after':reference.to_dict()})
        if saved['raw_policy'] is not None:pending=None
        continuous();intervene();return StepReceipt(current,session.ctx['calls'])
    snapshot('INITIAL');outcome=actor.run(spec['task'],session.public(),spec['boundary'],a.packet(spec),query,step,saved_event,forecast)
    continuous();io.require(pending is None and session._pending is None and outcome['total_steps']==len(rows)==session.ctx['calls']
        and outcome['policy_queries']==session.policy_queries,'actual actor/host costs')
    snapshot('FINAL');return outcome|{'boundary_applied':boundary_applied},public


class CaseFailure(RuntimeError):
    def __init__(self,record):super().__init__(str(record.get('error')));self.record=record


def execute_case(spec,emit,private,ledger,budget,position,sync,model_bank=None,model_sha=None):
    from src.analysis.paired_probe_host_v1 import ProbeSession
    from src.rollout.task_registry import create_task_environment,create_task_policy
    a.validate_spec(spec);start=perf_counter_ns();env=session=None;public=None
    row={**spec,'completed':False,'error':None,'close_error':None,'environment_closed':False,'ledger_before':ledger.snapshot(),
        'initial_fault_oracle':a.initial_fault(spec),'destination_oracle':a.destination(spec),'preallocated_packet':a.packet(spec)}
    try:
        emit('FACTORY_INTENT',{'ledger':ledger.snapshot()})
        with ledger.scope('FACTORY_SETUP'):env=create_task_environment(spec['task'],spec['seed'])
        emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
        with ledger.scope('CONTROLLED_RESET'):initial,_=env.reset(seed=spec['seed'])
        session=ProbeSession(env,create_task_policy(spec['task']),initial,spec['task'],spec['seed'],row['initial_fault_oracle'],emit,ledger,budget)
        session.ctx['noise_rows']=a.noise(spec);session.branch={'role':'LATENT_RESPONSE_COLLECTION','future':0,'program':'PREDECLARED_PACKET'}
        emit('NOISE_COMMITMENT',{'at_calls':0,'tape_sha256_oracle':io.digest(session.ctx['noise_rows'].tolist())})
        row['initial']=normalize(asdict(session.public()));outcome,public=run_live(spec,session,emit,private,position,sync,model_bank,model_sha)
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
