"""Literal record/cost/actuation audit plus supplementary saved-program replay.

No environment is constructed. The scheduler/parser and fixed-policy class are
shared in the supplementary replay; PI/PID, target and predictor arithmetic
are reconstructed separately. Native hashes are source witnesses, not an
independent physical simulation or a proof of all unobserved state equality.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import graybox_response_io_v1 as a
from src.analysis.command_target_sources_v1 import GroupedJournal
from src.analysis.short_probe_journal_audit_v1 import applied,ledger_add,simulation,check_observation
from src.analysis.native_command_witness_audit_v1 import target
from src.analysis.acquisition_reference_audit_v1 import readiness,pid_numbers
from src.analysis.response_action_audit_v1 import same,audit_pi
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.graybox_response_independent_v1 import evaluate
io=a.io
MEASURE=[[.4,0.,0.,0.],[0.,.4,0.,0.],[-.4,0.,0.,0.],[0.,-.4,0.,0.]]*2
MEASURE=np.asarray(MEASURE,np.float32).tolist()


def independent_query(spec,initial,steps,integral):
    n=len(steps);io.require(n>=24,'genuine public entry history, no padding')
    history=[dict(at_calls=j,before=deepcopy(initial if j==0 else steps[j-1]['after']),command=deepcopy(steps[j]['command']),after=deepcopy(steps[j]['after'])) for j in range(n)]
    return dict(schema='GRAYBOX_PACKET_QUERY_V1',task=spec['task'],at_calls=n,acquisition_action=spec['acquisition_action'],
        initial=deepcopy(initial),current=deepcopy(steps[-1]['after']),history=history,integral_carried_xy=list(integral),packets=a.packets(spec))


def compare_prefix(left,right,n):
    io.require(len(left)>=n and len(right)>=n,'both actually completed prefixes')
    for l,r in zip(left[:n],right[:n]):
        for field in ('command','raw_policy','after','executed_action_oracle','simulation_time_before','simulation_time_after','noise_cursor_after'):
            same(l[field],r[field],'paired actual prefix '+field)


def replay_nominal(spec,c,public,steps):
    names=['PROGRAM']+['NOMINAL_COMMAND_CHOICE','COMMAND']*len(steps)+['OUTCOME'];same([p['agent_event'] for p in public],names,'literal nominal schedule')
    for i in range(len(steps)):
        choice=public[1+2*i]['public_payload'];same(choice['index'],i);same(choice['command'],a.packets(spec)['NOMINAL'][i])
    expected=dict(total_steps=len(steps),policy_queries=0,reposition_steps=0,common_measure_steps=0,packet_steps=0,entry_at_calls=None,complete_packet=False,complete_first_eight=False,
        reason='NOMINAL_PLAN_COMPLETE' if len(steps)==80 else 'NOMINAL_EARLY_END',anchor=None,success_at_response_horizon=c['final']['success'],terminated=c['final']['terminated'],truncated=c['final']['truncated'],
        final_memory=None,nominal_steps=len(steps),completed_nominal_plan=len(steps)==80,full_task_tail_evaluated=False,new_model_fits=0,online_LLM_API_calls=0)
    same(public[-1]['public_payload']['outcome'],expected)
    for k,v in expected.items():same(c[k],v,'literal nominal outcome')
    return 0


def replay(spec,c,public,steps):
    if spec['split']=='NOMINAL':return replay_nominal(spec,c,public,steps)
    from src.probe.paired_packet_program_v1 import run
    from src.rollout.task_registry import create_task_policy
    from src.probe.continuous import StepObservation
    from src.probe.physical_reprobe_v1 import StepReceipt
    policy=create_task_policy(spec['task']);ei=si=queries=0;current=deepcopy(c['initial'])
    def query(obs):
        nonlocal queries
        same(obs,current['observation']);queries+=1;return np.asarray(policy.get_action(np.array(obs,copy=True)),np.float32)
    def emit(kind,payload):
        nonlocal ei
        io.require(ei<len(public),'no invented public event');e=public[ei];ei+=1;p=e['public_payload']
        same(kind,e['agent_event']);same(normalize(payload),{k:v for k,v in p.items() if k not in ('sequence','saved_ns')},'supplementary complete actor transcript '+kind)
        return deepcopy(p)
    def step(saved):
        nonlocal si,current
        e=steps[si];same(saved['command'],e['command']);same(saved['raw_policy'],e['raw_policy']);same(saved['before'],current)
        same(e['global_command_sequence'],next(p['sequence'] for p in public if p['public_payload']['sequence']==saved['sequence']))
        current=deepcopy(e['after']);si+=1;return StepReceipt(StepObservation(**current),si)
    def forecast(request):
        e=public[ei];same(e['agent_event'],'FORECAST_RESULT');same(e['public_payload']['request_sequence'],request['sequence']);return deepcopy(e['public_payload']['result'])
    packets=a.packets(spec);outcome=run(spec['task'],StepObservation(**c['initial']),spec['boundary'],spec['acquisition_action'],packets[spec['packet_kind']],packets,query,step,emit,forecast)
    same(si,len(steps));same(ei,len(public));same(queries,c['policy_queries'])
    for k,v in outcome.items():same(c[k],v,'saved outcome '+k)
    return queries


def audit_case(spec,c,events,private,export,ledger,bank=None,model_sha=None,inference_counter=None):
    a.validate_spec(spec);same({k:c[k] for k in a.KEYS},spec);same(c['ledger_before'],ledger)
    io.require(c['completed'] and c['environment_closed'] and c['error'] is c['close_error'] is None and c['captures']==c['restores']==0,'complete one-reset no-undo execution')
    same(c['initial_fault_oracle'],a.initial_fault(spec));same(c['destination_oracle'],a.destination(spec));same(c['preallocated_packets'],a.packets(spec))
    initial=[p for p in private if p['label']=='INITIAL'];final=[p for p in private if p['label']=='FINAL'];queries=[p for p in private if p['label']=='QUERY']
    same(len(initial),1);same(len(final),1);initial=initial[0];final=final[0]
    same(len(queries),int(c['entry_at_calls'] is not None));same(len(private),2*c['total_steps']+2+len(queries))
    before={p['at_calls']:p for p in private if p['label']=='BEFORE_STEP'};after={p['at_calls']:p for p in private if p['label']=='AFTER_STEP'}
    same(len(before),c['total_steps']);same(len(after),c['total_steps']);same(initial['mocap_pos_oracle'],[[0.,.6,.2]]);mapping={e['sequence']:e for e in events}
    for p in private:
        io.require(p['event']=='NATIVE_TARGET_VALUES' and p['evaluator_only'] is True and p['permitted_training_input_or_label'] is False,'private evaluator-only native witness')
        same((p['model_address_oracle'],p['data_address_oracle']),(initial['model_address_oracle'],initial['data_address_oracle']));same(p['mocap_dtype_oracle'],'<f8')
        scope='PHASE_BOUNDARY' if p['label'] in ('INITIAL','QUERY','FINAL') else 'NUMERIC_ONLY';same(p['signature_scope'],scope)
        io.require((p['witness_oracle'] is None)==(scope=='NUMERIC_ONLY'),'explicit witness scope')
        io.require((p['raw_python_semantic_sha256_oracle'] is None)==(scope=='NUMERIC_ONLY'),'raw Python semantic hash retained separately from projected pair comparison')
        io.require(np.isclose(p['simulation_time'],initial['simulation_time']+.0125*p['at_calls'],atol=1e-9,rtol=0),'continuous native clock')
        anchor=mapping[p['last_public_event']['sequence']];same(anchor['saved_ns'],p['last_public_event']['saved_ns']);io.require(anchor['saved_ns']<p['saved_ns'],'private samples after public anchor')
    steps=[];public=[];local={};current=deepcopy(c['initial']);fault=a.initial_fault(spec);noise=a.noise(spec);actual=[0.,.6,.2]
    command=intent=reset=None;factories=boundary=0;resets=Counter();integral=[0.,0.];pi=next_i=None;move_i=[0.,0.];move_update=None;history=[];anchor=None;lifted=False
    entry=None;entry_query=None;forecast_record=None;target_error=0.;invalid=0;independent_forecast_rows=0
    allowed={'CASE_ALLOCATION','FACTORY_INTENT','FACTORY_COMPLETE','LIFECYCLE_RESET_INTENT','LIFECYCLE_RESET_COMPLETE','CONTROLLED_INITIAL','NOISE_COMMITMENT','AGENT_EVENT','STEP_INTENT','STEP_COMPLETE','PHYSICAL_BOUNDARY','FAULT_BOUNDARY','CASE_COMPLETE'}
    def memory():return dict(schema='TASK_MEMORY_OPTION_V1',task=spec['task'],completed_steps=len(steps),current=deepcopy(current),
        controller=dict(source='UNCORRECTED',matrix_xy=[[1.,0.],[0.,1.]],offset=[0.,0.,0.,0.]),integral_xy=list(integral),time_constant_s=.5)
    for e in events:
        kind=e['event'];n=len(steps);io.require(kind in allowed,'unregistered host mutation '+kind)
        if kind=='CASE_ALLOCATION':same(e['assignment'],'FROZEN_GRAYBOX_NOMINAL_OR_KNOWN_PACKET');same(e['preallocated_packets'],a.packets(spec));same(e['model_sha256'],model_sha)
        elif kind=='FACTORY_INTENT':same(factories,0);same(e['ledger'],ledger);factories=1
        elif kind=='LIFECYCLE_RESET_INTENT':
            phase=e['phase'];io.require(reset is None and not public,'no nested or mid-attempt reset')
            io.require((factories==1 and phase=='GOAL_GENERATION' and resets[phase]<50) or (factories==2 and phase=='CONTROLLED_RESET' and resets[phase]==0),'registered initial resets')
            same(e['before'],ledger);reset=e;ledger=ledger_add(ledger,phase,'reset_attempts',1)
        elif kind=='LIFECYCLE_RESET_COMPLETE':
            io.require(reset is not None and e['phase']==reset['phase'] and e['intent_sequence']==reset['sequence'],'orphan reset')
            ledger=simulation(ledger,e['phase'],100,500);ledger=ledger_add(ledger,e['phase'],'reset_completed',1);same(e['after'],ledger);resets[e['phase']]+=1;reset=None
        elif kind=='FACTORY_COMPLETE':same(factories,1);same(resets['GOAL_GENERATION'],50);same(e['ledger'],ledger);factories=2
        elif kind=='CONTROLLED_INITIAL':same(factories,2);same(resets['CONTROLLED_RESET'],1);same(e['ledger'],ledger);same(e['observation'],current['observation']);same(e['simulation_time'],initial['simulation_time']);check_observation(current)
        elif kind=='NOISE_COMMITMENT':same(n,0);same(e['at_calls'],0);same(e['tape_sha256_oracle'],io.digest(noise.tolist()))
        elif kind=='FAULT_BOUNDARY':
            io.require(boundary==0 and command is None and intent is None and n==spec['boundary']==e['logical_step'] and not any(current[k] for k in ('success','terminated','truncated')),'one actual live fault boundary')
            same(e['old_fault_oracle'],fault);fault=a.destination(spec);same(e['new_fault_oracle'],fault);same(e['before'],e['after'],'no boundary state/RNG/time change');boundary=1
        elif kind=='STEP_INTENT':
            io.require(command is not None and intent is None and n==e['logical_step'],'one saved command before response')
            if spec['split']!='NOMINAL' and n>=spec['boundary']:same(boundary,1)
            same(e['global_command_sequence'],command['sequence']);same(e['command'],command['public_payload']['command']);same(e['phase'],command['public_payload']['phase']);same(e['ledger_before'],ledger);intent=e
        elif kind=='STEP_COMPLETE':
            io.require(command is not None and intent is not None and e['logical_step']==n and e['noise_cursor_after']==n+1,'noise cursor and command receipt')
            same(e['intent_sequence'],intent['sequence']);same(e['global_command_sequence'],command['sequence'])
            for field in ('command','phase','raw_policy'):same(e[field],command['public_payload'][field])
            io.require(command['saved_ns']<=intent['saved_ns']<=e['execution_started_ns']<=e['completed_ns']<=e['saved_ns'],'saved choice before execution/outcome')
            same(e['executed_action_oracle'],applied(e['command'],fault,noise[n]),'literal float32 affine/deadzone then XYZ noise then final clip')
            b=before[n];p=after[n+1];same(b['mocap_pos_oracle'],[actual]);io.require(b['saved_ns']<e['execution_started_ns']<=e['completed_ns']<p['saved_ns'],'native values bracket action')
            expected=target(actual,e['executed_action_oracle'])['target'];actual=p['mocap_pos_oracle'][0];target_error=max(target_error,max(abs(x-y) for x,y in zip(actual,expected)))
            same(b['simulation_time'],e['simulation_time_before']);same(p['simulation_time'],e['simulation_time_after'])
            ledger=simulation(ledger,'CONTROL',1,5);same(e['ledger_before'],intent['ledger_before']);same(e['ledger_after'],ledger)
            check_observation(e['after']);same(e['after']['success'],bool(e['info'].get('success',False)));current=deepcopy(e['after']);steps.append(e);command=intent=None
            if e['phase']=='REPOSITION':history.append(current['observation']);lifted=lifted or current['observation'][2]>=anchor[2]-.015;move_i=move_update;move_update=None
        elif kind=='PHYSICAL_BOUNDARY':same(n,e['logical_step']);io.require(n in (4,8),'early physical witness');same(e['noise_past_sha256'],io.digest(noise[:n].tolist()))
        elif kind=='AGENT_EVENT':
            io.require(command is None and intent is None,'no unsaved intervening operation');p=e['public_payload'];name=e['agent_event'];same(p['at_calls'],n);same(p['sequence'],len(public));io.require(p['saved_ns']<=e['saved_ns'],'public ack chronology');public.append(e);local[p['sequence']]=e
            if name=='PROGRAM':same(p['commands'],a.packets(spec)[spec['packet_kind']]);same(p['packets'],a.packets(spec));same(p['common_measure_commands'],[] if spec['split']=='NOMINAL' else MEASURE)
            elif name=='PI_PLAN':io.require(pi is None,'one PI plan');pi=p['saved_plan'];same(pi['before_memory_sha256'],io.digest(memory()))
            elif name=='COMMAND':
                io.require(not any(current[k] for k in ('success','terminated','truncated')) and n<a.case_cap(spec),'no command after terminal/cap');same(p['before'],current)
                decision=p['decision_sequence'];io.require(decision<p['sequence'] and decision in local,'earlier saved actual choice')
                sent=np.asarray(p['command'],np.float32);io.require(sent.shape==(4,) and np.isfinite(sent).all() and np.max(abs(sent))<=1,'finite bounded command');same(p['command'],sent.tolist())
                if p['phase']=='PREFIX_TASK':next_i,_=audit_pi(pi['pi_plan'],p['command'],integral,spec['task'],n,current,p['raw_policy'])
                elif p['phase']=='REPOSITION':
                    expected_i,u=pid_numbers(history,anchor,lifted,move_i,'LOCAL_PID');same(p['command'],u);same(move_update,expected_i);same(p['raw_policy'],None)
                else:
                    same(p['raw_policy'],None);prior=local[decision];same(p['command'],prior['public_payload']['command'])
                    if p['phase']=='NOMINAL_INPUT':same(prior['agent_event'],'NOMINAL_COMMAND_CHOICE');same(prior['public_payload']['index'],n);same(p['command'],a.packets(spec)['NOMINAL'][n])
                    elif p['phase']=='COMMON_MEASURE':same(prior['agent_event'],'MEASURE_COMMAND_CHOICE');same(p['command'],MEASURE[prior['public_payload']['index']])
                    else:
                        same(p['phase'],'EXOGENOUS_PACKET');io.require(forecast_record is not None and forecast_record['sequence']<e['sequence'],'forecast before first and every packet action');same(prior['agent_event'],'PACKET_COMMAND_CHOICE');same(p['command'],a.packets(spec)[spec['packet_kind']][prior['public_payload']['index']])
                command=e
            elif name=='TASK_MEMORY_COMMIT':integral=list(next_i);same(p['memory'],memory());pi=next_i=None
            elif name=='MOVE_ENTRY':
                same(p['memory'],memory());o=current['observation'];anchor=[min(.45,max(-.45,o[0])),min(.95,max(.45,o[1])),min(.45,max(.25,o[6]+.12))];same(p['anchor'],anchor);history=[o];lifted=o[2]>=anchor[2]-.015
            elif name=='INTEGRAL_UPDATE':io.require(not readiness(history,anchor),'no unnecessary move after readiness');same(p['integral_before'],move_i);move_update=pid_numbers(history,anchor,lifted,move_i,'LOCAL_PID')[0];same(p['integral_after'],move_update)
            elif name=='COMMON_MEASURE_PLAN':
                if spec['acquisition_action']=='MOVE':io.require(readiness(history,anchor),'same actual ready anchor')
                same(p['commands'],MEASURE)
            elif name=='PACKET_PLAN':same(p['commands'],a.packets(spec)[spec['packet_kind']]);same(p['integral_carried_xy'],integral);entry=n
            elif name=='FORECAST_REQUEST':entry_query=independent_query(spec,c['initial'],steps,integral);same(p['packets'],a.packets(spec));same(p['integral_carried_xy'],integral)
            elif name=='FORECAST_RESULT':
                result=p['result'];same(result['query'],entry_query,'literal causal query excludes private/future response');same(result['query_sha256'],io.digest(entry_query));same(result['model_sha256'],model_sha);same(result['canonical'],spec['packet_kind']=='ZERO')
                same(result['scope'],'KNOWN_PACKETS_BEFORE_ANY_FAMILY_PACKET_OUTCOME');forecasts=result['forecasts']
                errors=result['method_errors']
                if bank is None:same(forecasts,{});same(errors,{});same(result['forecast_error'],None);same(result['model_compute_counts'],{})
                elif result['forecast_error'] is not None:
                    same(forecasts,{});invalid=(24 if bank['selected_q_index'] is None else 18) if result['canonical'] else 0
                elif result['canonical']:
                    expected,expected_errors=evaluate(bank,entry_query,inference_counter)
                    same(sorted(forecasts),sorted(expected));same(sorted(errors),sorted(expected_errors))
                    for method in errors:same(errors[method]['type'],expected_errors[method]['type'])
                    for method in expected:
                        for pair in expected[method]:io.require(np.allclose(forecasts[method][pair],expected[method][pair],atol=2e-8,rtol=2e-7),'independent before-outcome response forecast '+method)
                    ngray=4 if bank['selected_q_index'] is None else 2;nm=8 if bank['selected_q_index'] is None else 6
                    complete_counts=dict(method_attempts=nm,methods_completed=nm,zero_rows=48,linear_rows=96,rls_updates=n-2,rls_forecast_steps=48,
                        axis_predictions=2*(n+48)*ngray,axis_observations=2*n*ngray)
                    if not errors:same(result['model_compute_counts'],complete_counts,'all online inference operations charged')
                    else:
                        for k,v in result['model_compute_counts'].items():io.require(k in complete_counts and 0<=v<=complete_counts[k],'partial inference count bound')
                    invalid=3*len(errors);independent_forecast_rows=48*len(expected)
                else:same(result['model_compute_counts'],{});same(result['compute_wall_ns'],0)
                forecast_record=e;same(c['forecast_record'],result)
            elif name=='TASK_MEMORY_RETURN':same(p['memory'],memory(),'original task integral carried across actual acquisition')
    io.require(reset is command is intent is pi is next_i is move_update is None,'all operations consumed')
    same(c['boundary_applied'],bool(boundary));same(len(steps),c['total_steps']);same(c['ledger_before_close'],ledger);same(c['ledger_after_close'],ledger);same(final['at_calls'],len(steps));same(final['mocap_pos_oracle'],[actual])
    expected_public=dict(schema='GRAYBOX_RESPONSE_PUBLIC_V1',task=spec['task'],initial=c['initial'],steps=[dict(at_calls=i,before=c['initial'] if i==0 else steps[i-1]['after'],command=s['command'],after=s['after']) for i,s in enumerate(steps)])
    same(export,expected_public,'strict public export');same(c['public_trajectory_sha256'],io.digest(export));same(entry,c['entry_at_calls'])
    if entry is None:same(c['forecast_record'],None);same(c['entry_witness_oracle'],None)
    else:same(queries[0]['at_calls'],entry);same(queries[0]['witness_oracle'],c['entry_witness_oracle']);same(c['entry_witness_oracle']['noise_past_sha256'],io.digest(noise[:entry].tolist()))
    extra_queries=replay(spec,c,public,steps)
    row={**spec,'total_steps':len(steps),'entry_at_calls':entry,'packet_steps':c['packet_steps'],'reason':c['reason'],'success_at_response_horizon':c['success_at_response_horizon'],
        'native_target_updates_bit_exact':target_error==0.,'max_native_target_error_m':target_error,'invalid_forecasts':invalid,'independent_policy_queries':extra_queries,'independent_forecast_rows':independent_forecast_rows}
    return row,ledger,steps,initial['witness_oracle'],forecast_record


def audit(path,split):
    from src.analysis.release_learning_guard_v1 import read_only
    start=perf_counter_ns();m=a.checked(path);root=Path(path).parent;out=root/split.lower();done=io.read(out/'completion.json');io.require(done['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','complete phase before audit')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'raw artifact unchanged '+n)
    identity={k:m[k] for k in a.IDENTITY};journal=GroupedJournal(io.rows(out/'events.jsonl.gz'),a.KEYS,identity);priv=GroupedJournal(io.rows(out/'private_targets.jsonl.gz'),a.KEYS,identity)
    cases=iter(io.rows(out/'cases.jsonl.gz'));exports=iter(io.rows(out/'public_trajectories.jsonl.gz'));bank=model_sha=None
    if split in ('CAL','QUAL'):bank,model_sha=a.phase_model(path,split)
    ledger=dict(counts={},by_phase={});rows=[];canonical={};prefixes={};counts=Counter();guard={};inference_counter={};online_counts=Counter()
    with read_only(guard,max_solve=(len(a.population(split))//3*2 if split in ('CAL','QUAL') else 0)):
        for spec in a.population(split):
            c=next(cases,None);io.require(c is not None,'full allocated population');events=journal.take_case(c);private=priv.take_case(c)
            same(events[-1]['event'],'CASE_COMPLETE');same(events[-1]['case_record_sha256'],io.digest(c));same(events[0]['sequence'],c['event_start_sequence']);same(events[-1]['sequence'],c['event_end_sequence_exclusive'])
            row,ledger,steps,initial,forecast=audit_case(spec,c,events,private,next(exports,None),ledger,bank,model_sha,inference_counter);rows.append(row)
            if split=='NOMINAL':continue
            pkey=(spec['group'],spec['task']);n=min(spec['boundary'],len(steps));reference=prefixes.get(pkey)
            if reference is None:prefixes[pkey]=(steps,n,initial)
            else:same(reference[1],n);same(reference[2],initial,'same initial state/RNG');compare_prefix(reference[0],steps,n);counts['pre_boundary_prefix_comparisons']+=1
            key=a.family_key(spec)
            if spec['packet_kind']=='ZERO':canonical[key]=(c,steps,forecast)
            else:
                ref,old,first=canonical[key];same(ref['entry_at_calls'],c['entry_at_calls']);same(ref['entry_witness_oracle'],c['entry_witness_oracle'],'actual common query native/Python/RNG/time')
                n=len(old) if ref['entry_at_calls'] is None else ref['entry_at_calls'];same(n,len(steps) if c['entry_at_calls'] is None else c['entry_at_calls']);compare_prefix(old,steps,n)
                if forecast is not None:
                    l={k:v for k,v in ref['forecast_record'].items() if k not in ('canonical','compute_wall_ns','model_compute_counts')};r={k:v for k,v in c['forecast_record'].items() if k not in ('canonical','compute_wall_ns','model_compute_counts')};same(l,r,'cached prediction does not observe a previous response')
                    first_packet=next(e for e in events if e['event']=='STEP_INTENT' and e['phase']=='EXOGENOUS_PACKET');io.require(first['saved_ns']<first_packet['saved_ns'],'canonical forecast before sibling action/outcome')
                counts['full_entry_prefix_comparisons']+=1
    journal.finish();priv.finish();io.require(next(cases,None) is None and next(exports,None) is None,'no extra data')
    summary=io.read(out/'summary.json');same(summary['lifecycle'],ledger);same(summary['events'],journal.count);same(summary['private_target_records'],priv.count);same(summary['executions'],len(rows));same(summary['control_steps'],sum(r['total_steps'] for r in rows))
    if split=='QUAL':io.require(summary['started_monotonic_ns']>io.read(root/'model_lock.json')['locked_monotonic_ns'],'CAL choice saved before QUAL collection')
    same(summary['fitting_guard'],{'attempted_fits':0});same(summary['network_guard'],{'attempted_network_calls':0});limits=a.limits(split)
    io.require(len(rows)==limits['executions'] and summary['control_steps']<=limits['control_steps'] and ledger['counts']['reset_attempts']==limits['all_resets'] and ledger['counts']['simulation_frames_completed']<=limits['physical_frames'],'complete cost budget')
    same(counts['full_entry_prefix_comparisons'],0 if split=='NOMINAL' else len(rows)//3*2);same(counts['pre_boundary_prefix_comparisons'],0 if split=='NOMINAL' else len(rows)-len(rows)//12)
    native=all(r['native_target_updates_bit_exact'] for r in rows);io.require(native,'all measured native targets exact')
    nominal_contract='NOT_APPLICABLE'
    if split=='NOMINAL':nominal_contract='PASSED' if all(sum(r['task']==t and r['total_steps']>=40 for r in rows)>=6 for t in io.TASKS) else 'NOT_QUALIFIED'
    software='NOT_APPLICABLE'
    if split=='SOFTWARE':software='PASSED' if all(any(all(r['packet_steps']==16 for r in rows if a.family_key(r)==key) for key in canonical if key[2]==task and key[-1]==action) for task in io.TASKS for action in ('IN_TASK','MOVE')) else 'NOT_QUALIFIED'
    io.write(out/'trajectory_audit.json',rows);a.checked(path)
    result=dict(integrity='PASSED',split=split,software_contract=software,nominal_contract=nominal_contract,manifest_id=m['manifest_id'],executions=len(rows),control_steps=summary['control_steps'],all_resets=ledger['counts']['reset_attempts'],
        physical_frames=ledger['counts']['simulation_frames_completed'],native_target_updates_bit_exact=native,paired_prefixes=dict(counts),invalid_forecasts=sum(r['invalid_forecasts'] for r in rows),
        extra_independent_policy_queries=sum(r['independent_policy_queries'] for r in rows),independent_forecast_rows=sum(r['independent_forecast_rows'] for r in rows),
        artifact_sha256=done['artifact_sha256'],trajectory_audit_sha256=io.sha(out/'trajectory_audit.json'),read_only_guard=guard,independent_inference_counts=inference_counter,wall_ns=perf_counter_ns()-start,new_environment_steps=0,new_global_model_fits=0,online_LLM_API_calls=0)
    io.write(out/'audit.json',result);return result
