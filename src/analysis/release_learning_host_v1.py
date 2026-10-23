"""Fresh release-learning host; post-return private randomization and continuity."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import numpy as np
from src.analysis import release_learning_io_v1 as allocation
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import release_learning_actor_v1 as actor
from src.probe import release_learning_programs_v1 as programs
from src.probe.physical_reprobe_v1 import StepReceipt
io=allocation.io


class CaseFailure(RuntimeError):
    def __init__(self,record):super().__init__(str(record.get('error')));self.record=record


def run_live(spec,nominal,session,witness,sync,runtime):
    allocation.validate_spec(spec);base=session.env.unwrapped;addresses=(base.model._address,base.data._address)
    io.require(float(base.action_scale)==.01,'fixed command units')
    tape=session.ctx['noise_rows'];clock=float(base.data.time);paid=session.run_budget['completed']
    frames=session.ledger.counts.get('simulation_frames_completed',0)
    resets={k:session.ledger.counts.get(k,0) for k in ('reset_attempts','reset_completed','reset_errors')}
    history=[session.public().observation];pending=None;events={};applied=False;memory_witness=None;memory_pairs=0
    rng=np.random.default_rng(np.random.SeedSequence(allocation.exposure_seed(spec)));draw_count=0
    session.emit('EXPOSURE_RNG_COMMITMENT_ORACLE',{'at_calls':0,'seed_vector_oracle':allocation.exposure_seed(spec),'initial_state_oracle':deepcopy(rng.bit_generator.state)})
    def draw_exposure(seal_sequence):
        nonlocal draw_count
        continuous();io.require(draw_count==0 and pending is None and session._pending is None,'repeat/early exposure draw')
        io.require(seal_sequence==len(events)-1 and events[seal_sequence][0]=='SIGNAL_SEAL','exposure requires the latest durable return seal')
        saved=events[seal_sequence][1]['saved_return']
        io.require(saved['record']['post_memory']['completed_steps']==session.ctx['calls'],'exposure before real acquisition completion')
        sync();before=session.witness();state=deepcopy(rng.bit_generator.state);u=float(rng.random());draw_count+=1
        io.require(session.witness()==before,'exposure draw changed physical state/noise/time')
        session.emit('RELEASE_RANDOM_ORACLE',{'at_calls':session.ctx['calls'],'seal_local_sequence':seal_sequence,
            'seal_global_sequence':session._map[seal_sequence],'uniform_oracle':u,'probability':.5,
            'rng_before_oracle':state,'rng_after_oracle':deepcopy(rng.bit_generator.state),'physical_before':before,'physical_after':session.witness()})
        return u
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
        nonlocal memory_witness,memory_pairs
        continuous();io.require(payload['at_calls']==session.ctx['calls'] and session._pending is None,'stale event or pending action')
        if name=='FIT_INTENT':
            from src.probe.cold_start_response import ColdPrefix
            prefix=ColdPrefix.from_dict(payload['prefix'])
            io.require(programs.calibrated_prefix(spec['program']) and np.array_equal(prefix.initial_observation,session.ctx['initial_observation'])
                and np.array_equal(prefix.commands,session.ctx['commands']) and np.array_equal(prefix.observations,session.ctx['observations']),'causal initial C4/C8 data required')
        if name=='ACQUISITION_CHOICE':
            if spec['program'] in ('REFERENCE_NO_PROBE','PURE_MOVE_KEEP'):
                io.require(payload['action']=='LOCAL_PID' and payload['at_calls']==spec['planned_boundary'],'legacy no-probe assignment')
                io.require(payload['before_memory']['current']==normalize(asdict(session.public())),'legacy no-probe stale public state')
            else:
                io.require(payload['action'] in actor.release.ACTIONS and payload['at_calls']==spec['planned_boundary'],'late/unregistered acquisition choice')
                prefix=[];prior=normalize({'observation':session.ctx['initial_observation'],'success':False,'terminated':False,'truncated':False})
                for index,row in enumerate(session.last_rows):
                    prefix.append(dict(at_calls=index,command=row['command'],before=prior,after=row['after']));prior=row['after']
                io.require(payload['prefix_history']==prefix and payload['before_memory']['current']==normalize(asdict(session.public())),'public history is not the actual completed prefix')
                fixed,_,_=programs.fixed(spec['program'])
                if fixed is not None:io.require(payload['requested_action']==fixed,'unassigned fixed acquisition')
        if name=='COMMAND':
            io.require(payload['before']==normalize(asdict(session.public())),'stale public command')
            required=payload['phase'] in ('PREFIX_TASK','TAIL_TASK','VALIDATION_TASK','APPROACH','TASK')
            io.require(required==(pending is not None) and payload['raw_policy']==pending,'one raw query per real task command')
            decision=events.get(payload['decision_sequence']);io.require(decision is not None,'unsaved physical decision')
            if required:
                if programs.calibrated_prefix(spec['program']):
                    from src.probe.operator_identification import encode_controller
                    io.require('controller' in decision[1] and np.array_equal(np.asarray(payload['command'],np.float32),encode_controller(decision[1]['controller'],pending)),'saved legacy correction not consumed')
                else:io.require(decision[0]=='PI_PLAN' and payload['command']==decision[1]['saved_plan']['pi_plan']['numbers']['sent_command'],'saved PI plan not consumed')
        saved=session._agent_emit(name,payload);events[saved['sequence']]=(name,deepcopy(saved))
        if name=='MEMORY_TRANSITION_PLAN':
            io.require(memory_witness is None and pending is None,'duplicate or pending memory transition')
            memory_witness=session.witness();witness('MEMORY_TRANSITION_PRE');sync()
        if name=='MEMORY_TRANSITION_COMMIT':
            io.require(memory_witness is not None and pending is None and session.witness()==memory_witness,'memory transition changed world/RNG/clock')
            io.require(events[payload['plan_sequence']][0]=='MEMORY_TRANSITION_PLAN','unsaved memory transition')
            witness('MEMORY_TRANSITION_POST');memory_witness=None;memory_pairs+=1
        if name=='SIGNAL_SEAL':sync()
        if name=='RELOCATION_EVIDENCE':witness('POST_RELOCATION')
        if name in ('TASK_MEMORY_RETURN','POST_MOVE_TASK_ENTRY'):witness('POST_ACQUISITION')
        return saved
    def step(saved):
        nonlocal pending
        continuous();io.require(saved==session._pending,'unsaved or changed command');sync();continuous()
        current=session._agent_step(saved);history.append(current.observation)
        if saved['raw_policy'] is not None:pending=None
        continuous();intervene();return StepReceipt(current,session.ctx['calls'])
    result=actor.run(spec['task'],session.public(),spec['planned_boundary'],spec['program'],nominal,policy,step,emit,runtime=runtime,draw_exposure=draw_exposure)
    continuous();io.require(pending is None and session._pending is None,'unconsumed task command')
    io.require(result['outcome']['total_steps']==session.ctx['calls'] and result['outcome']['policy_queries']==session.policy_queries,'actor/host costs differ')
    io.require(memory_witness is None and memory_pairs==int(result['outcome']['memory_transition_applied']),'unclosed memory transition witness')
    io.require(result['outcome']['exposure_draws']==draw_count,'actual host exposure draw ledger')
    witness('FINAL')
    return {**result['outcome'],'boundary_applied':applied,'boundary_missing_reason':None if applied else 'EARLY_SUCCESS' if session.public().success else
        'ENVIRONMENT_ENDED' if not session.alive() else result['outcome']['stop_reason']}


def execute_case(spec,nominal,emit,emit_private,ledger,budget,position,sync,runtime):
    allocation.validate_spec(spec)
    from src.analysis.paired_probe_host_v1 import ProbeSession
    from src.rollout.task_registry import create_task_environment,create_task_policy
    from scripts.qualify_delayed_intervention_v2 import observe_state
    start=perf_counter_ns();env=session=None;refs=[]
    row={**spec,'completed':False,'error':None,'close_error':None,'environment_closed':False,'ledger_before':ledger.snapshot(),
        'initial_fault_oracle':allocation.initial_fault(),'destination_oracle':allocation.destination(spec),'state_witness_refs':refs}
    counted={'c4_c8_fit_attempts':0,'c4_c8_fit_results':0,'c4_c8_optimizer_nfev':0}
    def public_emit(name,payload):
        if name=='AGENT_EVENT':
            p=payload['public_payload']
            if payload['agent_event']=='FIT_INTENT':counted['c4_c8_fit_attempts']+=1
            if payload['agent_event']=='FIT_RESULT':counted['c4_c8_fit_results']+=1;counted['c4_c8_optimizer_nfev']+=int(p['fit'].get('nfev',0))
        return emit(name,payload)
    def witness(label):
        saved=observe_state(session,label,session.witness(),position,emit_private);w=saved['witness']
        refs.append({'label':label,'sequence':saved['sequence'],'logical_step':session.ctx['calls'],'native_sha256':w['native_sha256'],'comparison_python_sha256':w['comparison_python_sha256']})
    try:
        emit('FACTORY_INTENT',{'ledger':ledger.snapshot()})
        with ledger.scope('FACTORY_SETUP'):env=create_task_environment(spec['task'],spec['seed'])
        emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
        with ledger.scope('CONTROLLED_RESET'):initial,_=env.reset(seed=spec['seed'])
        session=ProbeSession(env,create_task_policy(spec['task']),initial,spec['task'],spec['seed'],row['initial_fault_oracle'],public_emit,ledger,budget)
        session.ctx['noise_rows']=allocation.noise(spec);session.branch={'role':'RELEASE_LEARNING_V1','future':0,'program':spec['program']}
        emit('NOISE_COMMITMENT',{'at_calls':0,'noise_namespace_oracle':allocation.namespace(spec),'tape_sha256_oracle':io.digest(session.ctx['noise_rows'].tolist())})
        row['initial']=normalize(asdict(session.public()));witness('INITIAL')
        row.update(run_live(spec,nominal,session,witness,sync,runtime));row['final']=normalize(asdict(session.public()));row['completed']=True
        io.require(all(row[k]==v for k,v in counted.items()),'public fit ledger and returned costs differ')
    except BaseException as error:row['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        row.update(counted)
        if session is not None:row.update(host_attempts=session.attempts,host_returned=session.completed,total_steps=session.ctx['calls'],
            policy_queries=session.policy_queries,captures=session.captures,restores=session.restores,physical_rows_count=len(session.last_rows))
        row['ledger_before_close']=ledger.snapshot()
        if env is not None:
            try:env.close();row['environment_closed']=True
            except BaseException as error:row['close_error']={'type':type(error).__name__,'message':str(error)}
        row['ledger_after_close']=ledger.snapshot();row['wall_ns']=perf_counter_ns()-start
    if row['error'] is not None or row['close_error'] is not None or not row['completed'] or not row['environment_closed']:raise CaseFailure(normalize(row))
    return normalize(row)
