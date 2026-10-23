"""Whole-population read-only audit; independent PI/PID, target and query arithmetic."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import latent_response_io_v1 as a
from src.analysis.command_target_sources_v1 import GroupedJournal
from src.analysis.short_probe_journal_audit_v1 import applied,ledger_add,simulation
from src.analysis.native_command_witness_audit_v1 import target,public_state
from src.analysis.acquisition_reference_audit_v1 import readiness,pid_numbers
from src.analysis.response_action_audit_v1 import same,audit_pi
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe.latent_response_query_v1 import ForecastQuery,METHODS
from src.analysis.latent_response_model_audit_v1 import independent_predict,same_predictions
io=a.io


def independent_query(task,states,commands,sent,planned):
    n=len(commands);begin=max(0,n-15)
    value={'schema':'PUBLIC_LATENT_PACKET_QUERY_V1','task':task,'completed_steps':n,'observations':states[begin:],
        'previous_commands':[commands[j-1] if j else [0.,0.,0.,0.] for j in range(begin,n+1)],
        'has_previous':[int(j>0) for j in range(begin,n+1)],'nominal_offset':[sent[j]-states[-1][j] for j in range(3)],'planned_commands':planned}
    ForecastQuery.from_dict(value);return value


def replay(spec,c,public,steps):
    from src.probe.latent_response_packet_v1 import run
    from src.rollout.task_registry import create_task_policy
    policy=create_task_policy(spec['task']);ei=si=queries=0;current=deepcopy(c['initial'])
    def query(obs):
        nonlocal queries
        same(obs,current['observation']);queries+=1;return np.asarray(policy.get_action(np.asarray(obs).copy()),np.float32)
    def emit(kind,payload):
        nonlocal ei
        e=public[ei];ei+=1;saved=e['public_payload'];same(kind,e['agent_event']);same(normalize(payload),{k:v for k,v in saved.items() if k not in ('sequence','saved_ns')},'complete public actor transcript')
        return deepcopy(saved)
    def step(saved):
        nonlocal si,current
        e=steps[si];same(saved['command'],e['command']);same(saved['before'],current);same(saved['raw_policy'],e['raw_policy'])
        same(e['global_command_sequence'],next(p['sequence'] for p in public if p['agent_event']=='COMMAND' and p['public_payload']['sequence']==saved['sequence']))
        current=deepcopy(e['after']);si+=1;return StepReceipt(StepObservation(**current),si)
    def forecast(request):
        e=public[ei];same(e['agent_event'],'FORECAST_RESULT');same(e['public_payload']['request_sequence'],request['sequence']);return deepcopy(e['public_payload']['result'])
    outcome=run(spec['task'],StepObservation(**c['initial']),spec['boundary'],a.packet(spec),query,step,emit,forecast)
    same(si,len(steps));same(ei,len(public));same(queries,c['policy_queries'])
    for k,v in outcome.items():same(c[k],v,'recorded actor outcome '+k)
    return queries


def audit_case(spec,c,events,private,export,meta,ledger,bank=None,model_sha=None):
    a.validate_spec(spec);same({k:c[k] for k in a.KEYS},spec);same(c['ledger_before'],ledger)
    io.require(c['completed'] and c['environment_closed'] and c['error'] is c['close_error'] is None and c['captures']==c['restores']==0,'complete no-undo execution')
    mapping={e['sequence']:e for e in events};initial=next(p for p in private if p['label']=='INITIAL');final=next(p for p in private if p['label']=='FINAL')
    before={p['at_calls']:p for p in private if p['label']=='BEFORE_STEP'};after={p['at_calls']:p for p in private if p['label']=='AFTER_STEP'}
    same(len(private),2*c['total_steps']+2);same(len(before),c['total_steps']);same(len(after),c['total_steps']);same(initial['mocap_pos_oracle'],[[0.,.6,.2]])
    for p in private:
        same((p['model_address_oracle'],p['data_address_oracle']),(initial['model_address_oracle'],initial['data_address_oracle']));same(p['mocap_dtype_oracle'],'<f8')
        io.require(p['evaluator_only'] is True and p['permitted_training_input_or_label'] is False,'private evaluator scope')
        scope='PHASE_BOUNDARY' if p['label'] in ('INITIAL','FINAL') else 'NUMERIC_ONLY';same(p['signature_scope'],scope)
        io.require((p['native_signature_oracle'] is None)==(scope=='NUMERIC_ONLY'),'no unrecorded full-native-signature claim')
        io.require(np.isclose(p['simulation_time'],initial['simulation_time']+.0125*p['at_calls'],rtol=0,atol=1e-9),'native clock')
        anchor=mapping[p['last_public_event']['sequence']];same(anchor['saved_ns'],p['last_public_event']['saved_ns']);io.require(anchor['saved_ns']<p['saved_ns'],'native sample after public anchor')
    states=[c['initial']['observation']];commands=[];steps=[];public=[];sent=[0.,.6,.2];actual=[0.,.6,.2];fault=a.initial_fault(spec);noise=a.noise(spec)
    intent=plan=reset=None;boundary=0;target_error=0.;entry_query=None;entry=None;forecast_record=None;invalid=0;integral=[0.,0.];pi=None;next_i=None;history=[];anchor=None;lifted=False;move_i=[0.,0.];move_update=None
    def memory():return {'schema':'TASK_MEMORY_OPTION_V1','task':spec['task'],'completed_steps':len(commands),
        'current':deepcopy(c['initial']) if not steps else deepcopy(steps[-1]['after']),
        'controller':{'source':'UNCORRECTED','matrix_xy':[[1.,0.],[0.,1.]],'offset':[0.,0.,0.,0.]},'integral_xy':integral,'time_constant_s':.5}
    for e in events:
        kind=e['event'];n=len(commands)
        if kind=='LIFECYCLE_RESET_INTENT':same(e['before'],ledger);io.require(reset is None,'nested reset');reset=e;ledger=ledger_add(ledger,e['phase'],'reset_attempts',1)
        elif kind=='LIFECYCLE_RESET_COMPLETE':
            same(e['intent_sequence'],reset['sequence']);ledger=simulation(ledger,e['phase'],100,500);ledger=ledger_add(ledger,e['phase'],'reset_completed',1);same(e['after'],ledger);reset=None
        elif kind=='FACTORY_COMPLETE':same(e['ledger'],ledger)
        elif kind=='CONTROLLED_INITIAL':same(e['ledger'],ledger);same(e['observation'],c['initial']['observation'])
        elif kind=='NOISE_COMMITMENT':same(e['tape_sha256_oracle'],io.digest(noise.tolist()))
        elif kind=='FAULT_BOUNDARY':
            same(e['logical_step'],n);same(n,spec['boundary']);same(e['old_fault_oracle'],fault);same(e['new_fault_oracle'],a.destination(spec));same(e['before'],e['after']);fault=e['new_fault_oracle'];boundary+=1;io.require(boundary==1,'one change')
        elif kind=='PUBLIC_SENT_TARGET_PLAN':
            io.require(plan is None,'single public target plan');same(e['at_calls'],n);u=mapping[e['actor_command_sequence']]['public_payload']['command'];numbers=target(sent,u)
            expected={'schema':'PUBLIC_NOMINAL_TARGET_PLAN_V1','before_sha256':io.digest(public_state(spec['task'],n,sent)),
                'command':np.asarray(u,np.float32).tolist(),'numbers':numbers,'after':public_state(spec['task'],n+1,numbers['target'])}
            same(e['plan'],expected,'independent nominal target arithmetic');plan=e
        elif kind=='STEP_INTENT':
            io.require(intent is None and plan is not None and plan['sequence']<e['sequence'],'saved plan before action');same(e['logical_step'],n);same(e['ledger_before'],ledger);same(e['command'],plan['plan']['command']);intent=e
        elif kind=='STEP_COMPLETE':
            same(e['logical_step'],n);same(e['noise_cursor_after'],n+1);same(e['intent_sequence'],intent['sequence']);same(e['command'],intent['command'])
            same(e['global_command_sequence'],plan['actor_command_sequence']);same(e['executed_action_oracle'],applied(e['command'],fault,noise[n]),'exact actuator/noise/clip order')
            b=before[n];p=after[n+1];same(b['mocap_pos_oracle'],[actual]);io.require(b['saved_ns']<e['execution_started_ns']<=e['completed_ns']<p['saved_ns'],'native samples bracket action')
            observed=p['mocap_pos_oracle'][0];expected=target(actual,e['executed_action_oracle'])['target'];target_error=max(target_error,max(abs(x-y) for x,y in zip(expected,observed)));actual=observed
            ledger=simulation(ledger,'CONTROL',1,5);same(e['ledger_before'],intent['ledger_before']);same(e['ledger_after'],ledger)
            same(b['simulation_time'],e['simulation_time_before']);same(p['simulation_time'],e['simulation_time_after'])
            commands.append(e['command']);states.append(e['after']['observation']);steps.append(e);sent=plan['plan']['numbers']['target'];intent=None
            if e['phase']=='REPOSITION':history.append(states[-1]);lifted=lifted or states[-1][2]>=anchor[2]-.015;move_i=move_update;move_update=None
        elif kind=='PUBLIC_SENT_TARGET_COMMIT':same(e['at_calls'],n);same(e['plan_sequence'],plan['sequence']);same(e['reference'],public_state(spec['task'],n,sent));plan=None
        elif kind=='AGENT_EVENT':
            public.append(e);p=e['public_payload'];name=e['agent_event'];same(p['at_calls'],n)
            if name=='PROGRAM':same(p['actions'],a.packet(spec))
            elif name=='PI_PLAN':
                io.require(pi is None,'one PI plan');pi=p['saved_plan'];same(pi['before_memory_sha256'],io.digest(memory()))
            elif name=='COMMAND':
                same(p['before'],memory()['current'])
                if p['phase']=='PREFIX_TASK':
                    io.require(pi is not None,'saved PI');next_i,_=audit_pi(pi['pi_plan'],p['command'],integral,spec['task'],n,memory()['current'],p['raw_policy'])
                elif p['phase']=='REPOSITION':
                    expected_i,u=pid_numbers(history,anchor,lifted,move_i,'LOCAL_PID');same(p['command'],u);same(move_update,expected_i)
                else:io.require(p['phase']=='EXOGENOUS_PACKET','registered phase');io.require(forecast_record is not None and forecast_record['sequence']<e['sequence'],'forecast saved before actual packet input')
            elif name=='TASK_MEMORY_COMMIT':integral=list(next_i);same(p['memory'],memory());pi=next_i=None
            elif name=='MOVE_ENTRY':
                same(p['memory'],memory());o=states[-1];anchor=[min(.45,max(-.45,o[0])),min(.95,max(.45,o[1])),min(.45,max(.25,o[6]+.12))]
                same(p['anchor'],anchor);history=[o];lifted=o[2]>=anchor[2]-.015
            elif name=='INTEGRAL_UPDATE':
                io.require(not readiness(history,anchor),'move only until readiness');same(p['integral_before'],move_i);move_update=pid_numbers(history,anchor,lifted,move_i,'LOCAL_PID')[0];same(p['integral_after'],move_update)
            elif name=='PACKET_PLAN':
                io.require(readiness(history,anchor),'real ready measurement state');same(p['entry_history'],history[-4:]);same(p['commands'],a.packet(spec));entry=n
            elif name=='FORECAST_REQUEST':entry_query=independent_query(spec['task'],states,commands,sent,p['planned_commands'])
            elif name=='FORECAST_RESULT':
                result=p['result'];same(result['query'],entry_query,'no private or future response in forecast query');same(result['query_sha256'],io.digest(entry_query));same(result['model_sha256'],model_sha)
                forecasts=result['forecasts'];io.require(set(forecasts)==(set(METHODS) if bank is not None else set()),'all registered forecasts')
                for method,v in forecasts.items():
                    if not v['valid']:invalid+=1;continue
                    same_predictions(v['displacements'],independent_predict(bank[spec['task']][method],[entry_query])[0])
                forecast_record=e
            elif name=='TASK_MEMORY_RETURN':same(p['memory'],memory(),'carry original task integral after real acquisition')
    io.require(reset is None and plan is None and intent is None and pi is None and move_update is None,'all operations consumed')
    n=len(commands);same(n,c['total_steps']);same(c['boundary_applied'],bool(boundary));same(final['at_calls'],n);same(final['mocap_pos_oracle'],[actual]);same(c['ledger_before_close'],ledger);same(c['ledger_after_close'],ledger)
    expected_public={'schema':'PUBLIC_COMMAND_WITNESS_TRAJECTORY_V1','task':spec['task'],'initial_observation':states[0],'steps':[]};q=[0.,.6,.2]
    for k,e in enumerate(steps):
        q=target(q,e['command'])['target'];expected_public['steps'].append({'logical_step':k,'command':e['command'],'observation_before':states[k],
            'observation_after':states[k+1],'reference_after':public_state(spec['task'],k+1,q)})
    same(export,expected_public,'strict oracle-free public trajectory');same(c['public_trajectory_sha256'],io.digest(export))
    same(meta,{'schema':'PUBLIC_PACKET_METADATA_V1','entry_at_calls':entry,'packet_commands':a.packet(spec),'reason':c['reason']})
    queries=replay(spec,c,public,steps)
    summary={**spec,'total_steps':n,'packet_steps':c['packet_steps'],'entry_at_calls':entry,'complete_first_eight':c['complete_first_eight'],
        'reason':c['reason'],'success_at_response_horizon':c['success_at_response_horizon'],'max_native_target_error_m':target_error,
        'native_target_updates_bit_exact':target_error==0.,'invalid_forecasts':invalid,'independent_policy_queries':queries}
    return summary,ledger,steps,entry


def audit(path,split):
    start=perf_counter_ns();m=a.checked(path);root=Path(path).parent;out=root/split.lower();done=io.read(out/'completion.json')
    io.require(done['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','complete one-shot phase before audit')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'frozen raw bytes '+n)
    identity={k:m[k] for k in a.IDENTITY};journal=GroupedJournal(io.rows(out/'events.jsonl.gz'),a.KEYS,identity);priv=GroupedJournal(io.rows(out/'private_targets.jsonl.gz'),a.KEYS,identity)
    exports=iter(io.rows(out/'public_trajectories.jsonl.gz'));metadata=iter(io.rows(out/'public_packet_metadata.jsonl.gz'));cases=iter(io.rows(out/'cases.jsonl.gz'))
    bank=model_sha=None
    if split in ('CAL','QUAL'):model_sha=io.sha(root/'training/models.json');bank=io.read(root/'training/models.json')['by_task']
    ledger={'counts':{},'by_phase':{}};rows=[];pairs={};unit=None;counts=Counter()
    for spec in a.population(split):
        c=next(cases,None);io.require(c is not None,'full allocated population');events=journal.take_case(c);private=priv.take_case(c)
        same(events[-1]['event'],'CASE_COMPLETE');same(events[-1]['case_record_sha256'],io.digest(c));same(events[0]['sequence'],c['event_start_sequence']);same(events[-1]['sequence'],c['event_end_sequence_exclusive'])
        row,ledger,steps,entry=audit_case(spec,c,events,private,next(exports,None),next(metadata,None),ledger,bank,model_sha);rows.append(row)
        this=(spec['group'],spec['task'])
        if this!=unit:pairs={};unit=this
        for kind,key,length in (('context',(spec['initial_kind'],spec['packet_kind']),min(spec['boundary'],len(steps))),
            ('packet',(spec['initial_kind'],spec['context']),len(steps) if entry is None else entry)):
            if kind=='packet' and split=='TRAIN':continue
            ref=pairs.get((kind,key))
            if ref is None:pairs[(kind,key)]=(steps,length)
            else:
                old,n=ref;count=min(n,length);same(n,length,'matching real prefix length')
                for left,right in zip(steps[:count],old[:count]):
                    for field in ('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(left[field],right[field],'actual paired prefix')
                counts[kind+'_prefix_pairs']+=1
    journal.finish();priv.finish();io.require(all(next(v,None) is None for v in (cases,exports,metadata)),'no extra cases/public data')
    summary=io.read(out/'summary.json');same(summary['lifecycle'],ledger);same(summary['events'],journal.count);same(summary['private_target_records'],priv.count)
    same(summary['executions'],len(rows));same(summary['control_steps'],sum(r['total_steps'] for r in rows));same(summary['fitting_guard'],{'attempted_fits':0});same(summary['network_guard'],{'attempted_network_calls':0})
    limits=a.limits(split);io.require(len(rows)==limits['executions'] and summary['control_steps']<=limits['control_steps'] and ledger['counts']['reset_attempts']==limits['all_resets']
        and ledger['counts']['simulation_frames_completed']<=limits['physical_frames'],'entire collection budget')
    native=all(r['native_target_updates_bit_exact'] for r in rows)
    software='NOT_APPLICABLE'
    if split=='SOFTWARE':software='PASSED' if native and all(any(r['task']==t and r['packet_kind']==p and r['packet_steps']>0 for r in rows) for t in io.TASKS for p in ('FIXED8','RANDOM8')) else 'NOT_QUALIFIED'
    same(counts['context_prefix_pairs'],len(rows)//2)
    if split!='TRAIN':same(counts['packet_prefix_pairs'],len(rows)//2)
    io.write(out/'trajectory_audit.json',rows);a.checked(path)
    result={'integrity':'PASSED','split':split,'manifest_id':m['manifest_id'],'software_contract':software,'executions':len(rows),'control_steps':summary['control_steps'],
        'all_resets':ledger['counts']['reset_attempts'],'physical_frames':ledger['counts']['simulation_frames_completed'],'native_target_updates_bit_exact':native,
        'paired_prefixes':dict(counts),'extra_independent_policy_queries':sum(r['independent_policy_queries'] for r in rows),
        'invalid_forecasts':sum(r['invalid_forecasts'] for r in rows),'artifact_sha256':done['artifact_sha256'],'trajectory_audit_sha256':io.sha(out/'trajectory_audit.json'),
        'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'new_model_fits':0,'online_LLM_API_calls':0,'full_task_tail_evaluated':False}
    io.write(out/'audit.json',result);return result
