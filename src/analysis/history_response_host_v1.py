"""Continuous, one-reset known-packet collection with canonical before-outcome forecasts."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from src.analysis import history_response_io_v1 as a
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import paired_packet_program_v1 as actor
from src.probe.paired_packet_query_v1 import make as make_query
from src.probe.history_response_model_v1 import predict
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe.nominal_command_target_v1 import INITIAL,LOW,HIGH
io=a.io


def without_episode_wall_clock(value,layer_types):
    """One explicit nonphysical timer exclusion; never mutate the real wrapper."""
    result=dict(value);result['layers']=[dict(v) for v in value['layers']];omitted=[]
    io.require(len(result['layers'])==len(layer_types),'complete wrapper metadata')
    for i,name in enumerate(layer_types):
        if name=='gymnasium.wrappers.common.RecordEpisodeStatistics':
            v=result['layers'][i];io.require('episode_start_time' in v and type(v['episode_start_time']) is float and np.isfinite(v['episode_start_time']),'registered wall clock timer')
            v.pop('episode_start_time');omitted.append(dict(layer=i,type=name,field='episode_start_time'))
    io.require(len(omitted)==1,'exactly the qualified episode-statistics wrapper; no generic exclusions')
    return result,omitted


def paired_witness(session):
    from src.analysis.state_capsule_v1 import python_state,state_signature,layers
    raw=session.witness();chain=layers(session.env);base=session.env.unwrapped
    projected,omitted=without_episode_wall_clock(python_state(chain,session.policy,session.ctx),[type(v).__module__+'.'+type(v).__qualname__ for v in chain])
    result=dict(raw);result['python_semantic_sha256']=state_signature(projected,base.model,base.data);result['python_comparison_omissions']=omitted
    return result,raw['python_semantic_sha256']

def native_values(session,label,position):
    base=session.env.unwrapped;target=np.array(base.data.mocap_pos,copy=True);quat=np.array(base.data.mocap_quat,copy=True)
    io.require(target.shape==(1,3) and target.dtype==np.float64 and quat.shape==(1,4) and np.isfinite(target).all() and np.isfinite(quat).all(),'native numeric target layout')
    full=label in ('INITIAL','QUERY','FINAL');signature,raw_python=paired_witness(session) if full else (None,None)
    return normalize(dict(label=label,at_calls=session.ctx['calls'],mocap_pos_oracle=target,mocap_quat_oracle=quat,simulation_time=float(base.data.time),
        model_address_oracle=int(base.model._address),data_address_oracle=int(base.data._address),mocap_dtype_oracle=target.dtype.str,last_public_event=position(),
        signature_scope='PHASE_BOUNDARY' if full else 'NUMERIC_ONLY',witness_oracle=signature,raw_python_semantic_sha256_oracle=raw_python,
        evaluator_only=True,permitted_training_input_or_label=False))

def run_live(spec,session,emit,private,position,sync,families,model_bank=None,model_sha=None):
    a.validate_spec(spec);base=session.env.unwrapped;addresses=(base.model._address,base.data._address);tape=session.ctx['noise_rows'];cap=a.case_cap(spec)
    initial_time=float(base.data.time);paid=session.run_budget['completed'];frames=session.ledger.counts['simulation_frames_completed'];resets=session.ledger.counts['reset_attempts']
    io.require(float(base.action_scale)==.01 and np.array_equal(base.mocap_low,LOW) and np.array_equal(base.mocap_high,HIGH) and np.array_equal(base.data.mocap_pos,np.array([INITIAL])),'unchanged qualified native interface')
    rows=[];events={};pending=None;boundary_applied=False;forecast_record=None;entry_witness=None;packet_plan=a.packets(spec);key=a.family_key(spec)
    public=dict(schema='PAIRED_PACKET_PUBLIC_V1',task=spec['task'],initial=normalize(asdict(session.public())),steps=rows)
    def continuous():
        n=session.ctx['calls'];io.require((base.model._address,base.data._address)==addresses and session.ctx['noise_rows'] is tape,'world or noise replacement')
        io.require(not session.captures and not session.restores and not session._snapshots and session.ledger.counts['reset_attempts']==resets,'no capture/restore/reset in attempt')
        io.require(n<=cap and session.run_budget['completed']-paid==n and session.ledger.counts['simulation_frames_completed']-frames==5*n,'exact continuous budget')
        io.require(np.isclose(float(base.data.time)-initial_time,.0125*n,atol=1e-9,rtol=0),'continuous simulation clock')
    def snapshot(label):return private('NATIVE_TARGET_VALUES',native_values(session,label,position))
    def intervene():
        nonlocal boundary_applied
        if session.ctx['calls']!=spec['boundary'] or not session.alive():return
        io.require(not boundary_applied and pending is None and session._pending is None,'single registered fault boundary')
        before=session.witness();old=deepcopy(session.fault);session.fault=a.destination(spec)
        io.require(session.witness()==before,'fault installation changed physical state/RNG/clock')
        emit('FAULT_BOUNDARY',dict(logical_step=session.ctx['calls'],old_fault_oracle=old,new_fault_oracle=session.fault,before=before,after=session.witness()));boundary_applied=True
    def query(observation):
        nonlocal pending
        continuous();io.require(pending is None and np.array_equal(observation,session.public().observation),'one policy query at actual current observation')
        pending=session.policy_query(observation).tolist();return np.asarray(pending,np.float32)
    def saved_event(kind,payload):
        continuous();io.require(payload['at_calls']==session.ctx['calls'] and session._pending is None,'actual public event clock')
        if kind=='PROGRAM':io.require(payload['commands']==packet_plan[spec['packet_kind']] and payload['packets']==packet_plan,'frozen complete packet program before responses')
        if kind=='COMMAND':
            io.require(payload['before']==normalize(asdict(session.public())),'actual command observation')
            prefix=payload['phase']=='PREFIX_TASK';io.require(prefix==(pending is not None) and payload['raw_policy']==pending,'fixed policy query accounting')
            prior=events.get(payload['decision_sequence']);io.require(prior is not None,'saved earlier command choice')
            if prefix:io.require(prior[0]=='PI_PLAN' and payload['command']==prior[1]['saved_plan']['pi_plan']['numbers']['sent_command'],'saved PI plan consumed')
            elif payload['phase'] in ('COMMON_MEASURE','EXOGENOUS_PACKET'):io.require(payload['command']==prior[1]['command'],'saved known command consumed')
        ack=session._agent_emit(kind,payload);events[ack['sequence']]=(kind,deepcopy(ack));return ack
    def forecast(request):
        nonlocal forecast_record,entry_witness
        continuous();io.require(events.get(request['sequence'])==('FORECAST_REQUEST',request) and request['at_calls']==len(rows),'saved request before packet')
        q=make_query(spec['task'],len(rows),spec['acquisition_action'],normalize(asdict(session.public())),rows,request['integral_carried_xy'],packet_plan)
        entry_witness=paired_witness(session)[0];snapshot('QUERY');start=perf_counter_ns()
        if spec['packet_kind']=='ZERO':
            io.require(key not in families,'one canonical ZERO entry per family');forecasts={};error=None;counter={}
            if spec['split'] in ('CAL','QUAL'):
                io.require(model_bank is not None and model_sha is not None,'frozen learned bank before CAL/QUAL')
                try:forecasts=predict(model_bank,q,counter)
                except Exception as ex:error=dict(type=type(ex).__name__,message=str(ex))
            value=dict(query=q,query_sha256=io.digest(q),model_sha256=model_sha,forecasts=forecasts,forecast_error=error,
                canonical=True,compute_wall_ns=perf_counter_ns()-start,model_compute_counts=counter,
                scope='KNOWN_PACKETS_BEFORE_ANY_FAMILY_PACKET_OUTCOME')
            families[key]=dict(query=deepcopy(q),witness=deepcopy(entry_witness),result=deepcopy(value))
        else:
            prior=families.get(key);io.require(prior is not None and prior['query']==q and prior['witness']==entry_witness,'common actual public/native/Python/RNG entry before factual pair')
            value=deepcopy(prior['result']);value.update(canonical=False,compute_wall_ns=0,model_compute_counts={})
        forecast_record=value;sync();return deepcopy(value)
    def step(saved):
        nonlocal pending
        continuous();io.require(saved==session._pending,'consume actual saved command once');before=normalize(asdict(session.public()))
        snapshot('BEFORE_STEP');sync();current=session._agent_step(saved);snapshot('AFTER_STEP')
        rows.append(dict(at_calls=len(rows),before=before,command=list(saved['command']),after=normalize(asdict(current))))
        if saved['raw_policy'] is not None:pending=None
        continuous();intervene();return StepReceipt(current,session.ctx['calls'])
    snapshot('INITIAL')
    result=actor.run(spec['task'],session.public(),spec['boundary'],spec['acquisition_action'],packet_plan[spec['packet_kind']],packet_plan,query,step,saved_event,forecast)
    continuous();io.require(pending is None and session._pending is None and result['total_steps']==len(rows)==session.ctx['calls'] and result['policy_queries']==session.policy_queries,'exact actor/host outcomes')
    if spec['packet_kind']=='ZERO' and forecast_record is None:
        io.require(key not in families,'unique unavailable canonical family');families[key]=dict(query=None,witness=None,result=None)
    if spec['packet_kind']!='ZERO' and forecast_record is None:io.require(families[key]['query'] is None,'all siblings share entry availability')
    snapshot('FINAL')
    return result|dict(boundary_applied=boundary_applied,forecast_record=forecast_record,entry_witness_oracle=entry_witness),public

class CaseFailure(RuntimeError):
    def __init__(self,record):super().__init__(str(record.get('error')));self.record=record

def execute_case(spec,emit,private,ledger,budget,position,sync,families,model_bank=None,model_sha=None):
    from src.analysis.paired_probe_host_v1 import ProbeSession
    from src.rollout.task_registry import create_task_environment,create_task_policy
    a.validate_spec(spec);start=perf_counter_ns();env=session=None;public=None
    row={**spec,'completed':False,'error':None,'close_error':None,'environment_closed':False,'ledger_before':ledger.snapshot(),
        'initial_fault_oracle':a.initial_fault(spec),'destination_oracle':a.destination(spec),'preallocated_packets':a.packets(spec)}
    try:
        emit('FACTORY_INTENT',dict(ledger=ledger.snapshot()))
        with ledger.scope('FACTORY_SETUP'):env=create_task_environment(spec['task'],spec['seed'])
        emit('FACTORY_COMPLETE',dict(ledger=ledger.snapshot()))
        with ledger.scope('CONTROLLED_RESET'):initial,_=env.reset(seed=spec['seed'])
        session=ProbeSession(env,create_task_policy(spec['task']),initial,spec['task'],spec['seed'],row['initial_fault_oracle'],emit,ledger,budget)
        session.ctx['noise_rows']=a.noise(spec);session.branch=dict(role='PAIRED_PACKET_RESPONSE',future=0,program=spec['packet_kind'])
        emit('NOISE_COMMITMENT',dict(at_calls=0,tape_sha256_oracle=io.digest(session.ctx['noise_rows'].tolist())))
        row['initial']=normalize(asdict(session.public()));result,public=run_live(spec,session,emit,private,position,sync,families,model_bank,model_sha)
        row.update(result);row['final']=normalize(asdict(session.public()));row['completed']=True
    except BaseException as ex:row['error']=dict(type=type(ex).__name__,message=str(ex))
    finally:
        if session is not None:row.update(total_steps=session.ctx['calls'],host_attempts=session.attempts,host_returned=session.completed,policy_queries=session.policy_queries,captures=session.captures,restores=session.restores)
        row['ledger_before_close']=ledger.snapshot()
        if env is not None:
            try:env.close();row['environment_closed']=True
            except BaseException as ex:row['close_error']=dict(type=type(ex).__name__,message=str(ex))
        row['ledger_after_close']=ledger.snapshot();row['wall_ns']=perf_counter_ns()-start
    if row['error'] is not None or row['close_error'] is not None or not row['completed'] or not row['environment_closed']:raise CaseFailure(normalize(row))
    return normalize(row),public
