"""Streaming lifecycle/actuator audit plus public-record program replay.

PI arithmetic and the host journal are reconstructed separately. Macro control
replay shares the unchanged, previously tested acquisition primitive; witnesses
do not independently resimulate the world or prove hidden-state sufficiency.
"""
from collections import Counter
from copy import deepcopy
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
import gzip,json
import numpy as np
from src.analysis import correction_scope_io_v1 as a
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.short_probe_journal_audit_v1 import applied,ledger_add,simulation,check_ledger,check_observation,physical_rows_equal
from src.analysis.task_passive_audit_v1 import audit_pi
from src.analysis.release_learning_guard_v1 import read_only
from src.probe import correction_scope_program_v1 as actor
from src.probe import correction_scope_model_v1 as model
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
io=a.io


def same(x,y,message='independent record mismatch'):io.require(io.digest(normalize(x))==io.digest(normalize(y)),message)


def replay(spec,case,public,steps,bank):
    from src.rollout.task_registry import create_task_policy
    policy=create_task_policy(spec['task']);cursor=physical=queries=0
    def fixed(observation):
        nonlocal queries
        queries+=1;return np.asarray(policy.get_action(np.array(observation,copy=True)),np.float32)
    def emit(kind,payload):
        nonlocal cursor
        io.require(cursor<len(public),'unrecorded public event');e=public[cursor];p=e['public_payload']
        same(kind,e['agent_event']);same(payload,{k:v for k,v in p.items() if k not in ('sequence','saved_ns')},'public replay at '+kind)
        cursor+=1;return deepcopy(p)
    def step(saved):
        nonlocal physical
        io.require(physical<len(steps),'invented physical feedback');r=steps[physical]
        for k in ('command','phase','raw_policy'):same(saved[k],r[k],'command changed before recorded feedback')
        physical+=1;return StepReceipt(StepObservation(**r['after']),physical)
    result=actor.run(spec['task'],StepObservation(**case['initial']),spec['planned_boundary'],spec['acquisition_action'],spec['time_constant_s'],fixed,step,emit,bank=bank)
    same(cursor,len(public));same(physical,len(steps));same(queries,case['policy_queries'])
    for k,v in result['outcome'].items():same(v,case[k],'replayed outcome '+k)
    return queries


def reconstruct(spec,case,events,private,ledger):
    from src.analysis.continuous_state_witness_v1 import verify_witness,compare_witnesses
    same(case['ledger_before'],ledger);same(case['initial_fault_oracle'],a.initial_fault());same(case['destination_oracle'],a.destination(spec))
    io.require(case['completed'] and case['environment_closed'] and case['error'] is None and case['close_error'] is None,'incomplete case cannot pass')
    same(case['captures'],0);same(case['restores'],0)
    current=clock=command=intent=reset=None;factory=0;resets=Counter();steps=[];public=[];local={};fault=a.initial_fault();boundary=None
    tape=a.noise(spec);integral=[0.,0.];pi_pending=None;pi_count=0;forecasts={};returned=None;rate_pending=None
    for e in events:
        k=e['event']
        if k=='FACTORY_INTENT':same(e['ledger'],ledger);io.require(factory==0 and current is None,'repeat factory');factory=1
        elif k=='LIFECYCLE_RESET_INTENT':
            phase=e['phase'];io.require(reset is None and current is None,'mid-task/nested reset')
            io.require((factory==1 and phase=='GOAL_GENERATION' and resets[phase]<50) or (factory==2 and phase=='CONTROLLED_RESET' and resets[phase]==0),'unallocated reset')
            same(e['before'],ledger);ledger=ledger_add(ledger,phase,'reset_attempts',1);reset=e
        elif k=='LIFECYCLE_RESET_COMPLETE':
            io.require(reset is not None and e['intent_sequence']==reset['sequence'] and e['phase']==reset['phase'],'orphan reset')
            ledger=simulation(ledger,e['phase'],100,500);ledger=ledger_add(ledger,e['phase'],'reset_completed',1)
            same(e['after'],ledger);resets[e['phase']]+=1;reset=None
        elif k=='FACTORY_COMPLETE':io.require(factory==1 and resets['GOAL_GENERATION']==50,'factory resets');same(e['ledger'],ledger);factory=2
        elif k=='CONTROLLED_INITIAL':
            io.require(current is None and factory==2 and resets['CONTROLLED_RESET']==1,'single controlled initial reset')
            same(e['observation'],case['initial']['observation']);same(e['ledger'],ledger);current=deepcopy(case['initial']);clock=e['simulation_time'];check_observation(current)
        elif k=='NOISE_COMMITMENT':same(e['tape_sha256_oracle'],io.digest(tape.tolist()));same(e['noise_namespace_oracle'],202610262)
        elif k=='AGENT_EVENT':
            p=e['public_payload'];io.require(current is not None and command is None and intent is None and p['sequence']==len(public) and p['at_calls']==len(steps) and p['saved_ns']<=e['saved_ns'],'public event chronology')
            public.append(e);local[p['sequence']]=e;name=e['agent_event']
            if name=='PI_PLAN':
                io.require(pi_pending is None,'duplicate PI plan');pi_pending=p
                same(p['saved_plan']['pi_plan']['query']['integral_before'],integral,'silent task-memory reset')
            elif name=='COMMAND':
                io.require(not any(current[x] for x in ('success','terminated','truncated')) and len(steps)<500,'step after end')
                same(p['before'],current);io.require(p['decision_sequence']<p['sequence'] and p['decision_sequence'] in local,'future or absent decision')
                if p['raw_policy'] is not None:
                    io.require(pi_pending is not None and p['decision_sequence']==pi_pending['sequence'],'saved PI not consumed')
                    q=pi_pending['saved_plan']['pi_plan'];expected_rate=.5 if p['phase']!='TAIL_TASK' else spec['time_constant_s']
                    same(q['query']['time_constant_s'],expected_rate)
                    integral,_=audit_pi(q,p['command'],integral,spec['task'],len(steps),current,p['raw_policy']);pi_count+=1
                command=e
            elif name=='TASK_MEMORY_COMMIT':
                io.require(pi_pending is not None,'memory commit without a consumed PI plan');same(p['memory']['integral_xy'],integral);same(p['memory']['current'],current);pi_pending=None
            elif name=='FORECAST_INPUT':
                v=p['value'];model.validate(v)
                history=[];prior=case['initial']
                for row in steps:
                    history.append(dict(at_calls=row['logical_step'],before=prior,command=row['command'],after=row['after']));prior=row['after']
                same(v['history'],history,'forecast sees a future or fabricated observation');same(v['memory']['current'],current)
                same(v['acquisition_action'],spec['acquisition_action']);same(v['time_constant_s'],spec['time_constant_s'])
                same(v['memory']['integral_xy'],integral);same(v['memory']['task'],spec['task'])
                same(v['memory']['time_constant_s'],.5 if v['stage']=='PRE' else spec['time_constant_s'])
                io.require(v['stage'] not in forecasts,'repeated forecast stage');forecasts[v['stage']]=dict(view=v,input_event=e,forecast_event=None)
            elif name=='FORECAST':
                parent=local.get(p['input_sequence']);io.require(parent is not None and parent['agent_event']=='FORECAST_INPUT' and p['input_sequence']==p['sequence']-1,'unsaved forecast input')
                stage=parent['public_payload']['value']['stage'];io.require(forecasts[stage]['forecast_event'] is None,'repeat forecast')
                forecasts[stage]['forecast_event']=e
                if p['forecast'] is not None:same(p['forecast']['input_sha256'],io.digest(forecasts[stage]['view']))
            elif name=='ACQUISITION_CHOICE':
                io.require('PRE' in forecasts and forecasts['PRE']['forecast_event']['saved_ns']<e['saved_ns'],'acquisition before forecast');same(p['action'],spec['acquisition_action'])
            elif name=='TASK_MEMORY_RETURN':returned=p; same(p['memory']['integral_xy'],integral)
            elif name=='RATE_PLAN':
                io.require(returned is not None and rate_pending is None,'rate before return');same(p['rate'],spec['time_constant_s']);same(p['memory_mode'],'CARRY');rate_pending=p
            elif name=='RATE_COMMIT':
                io.require(rate_pending is not None and p['plan_sequence']==rate_pending['sequence'],'unsaved rate transition')
                same(p['memory']['integral_xy'],integral);same(p['memory']['current'],current);same(p['memory']['time_constant_s'],spec['time_constant_s']);rate_pending=None
        elif k=='STEP_INTENT':
            io.require(command is not None and intent is None and e['logical_step']==len(steps),'orphan action intent')
            if len(steps)>=spec['planned_boundary']:io.require(boundary is not None,'missed hidden boundary')
            same(e['global_command_sequence'],command['sequence']);same(e['command'],command['public_payload']['command']);same(e['ledger_before'],ledger);intent=e
        elif k=='STEP_COMPLETE':
            io.require(command is not None and intent is not None and e['logical_step']==len(steps) and e['noise_cursor_after']==len(steps)+1,'response/noise cursor')
            same(e['intent_sequence'],intent['sequence']);same(e['global_command_sequence'],command['sequence'])
            for field in ('command','raw_policy','phase'):same(e[field],command['public_payload'][field])
            io.require(command['saved_ns']<=intent['saved_ns']<=e['execution_started_ns']<=e['completed_ns']<=e['saved_ns'],'plan after outcome')
            if e['phase']=='TAIL_TASK':io.require('POST' in forecasts and forecasts['POST']['forecast_event']['saved_ns']<e['execution_started_ns'],'tail preceded forecast')
            same(e['ledger_before'],ledger);ledger=simulation(ledger,'CONTROL',1,5);same(e['ledger_after'],ledger)
            io.require(np.isclose(e['simulation_time_before'],clock,atol=1e-10,rtol=0) and np.isclose(e['simulation_time_after']-clock,.0125,atol=1e-10,rtol=0),'clock discontinuity')
            same(e['executed_action_oracle'],applied(e['command'],fault,tape[len(steps)]),'float32 transform/noise/final-clip order')
            check_observation(e['after']);same(e['after']['success'],bool(e['info'].get('success',False)));steps.append(e);current=e['after'];clock=e['simulation_time_after'];command=intent=None
        elif k=='FAULT_BOUNDARY':
            io.require(boundary is None and len(steps)==spec['planned_boundary']==e['logical_step'] and command is None,'hidden boundary chronology')
            same(e['old_fault_oracle'],fault);fault=a.destination(spec);same(e['new_fault_oracle'],fault);same(e['before'],e['after']);boundary=e
        elif k=='PHYSICAL_BOUNDARY':same(e['noise_past_sha256'],io.digest(tape[:len(steps)].tolist()));same(e['simulation_time'],clock)
        else:raise ValueError('unknown host event '+k)
    io.require(command is None and intent is None and reset is None and pi_pending is None and rate_pending is None,'unfinished operation')
    same(case['final'],current);same(case['ledger_before_close'],ledger);same(case['ledger_after_close'],ledger);check_ledger(ledger)
    same(case['boundary_applied'],boundary is not None);same(case['deadline_loss'],len(steps) if current['success'] else 500)
    io.require(len(steps)==case['total_steps']==case['host_attempts']==case['host_returned']==case['physical_rows_count']<=500,'physical count disagreement')
    same(case['policy_queries'],pi_count)
    refs=[];bylabel={}
    for p in private:
        io.require(p['event']=='STATE_WITNESS','unknown witness event');same(p['ledger_before'],p['ledger_after'])
        anchor=next((e for e in events if e['sequence']==p['source_anchor_sequence']),None)
        io.require(anchor is not None and anchor['saved_ns']==p['source_anchor_saved_ns']<=p['started_ns']<=p['completed_ns']<=p['saved_ns'],'private chronology')
        verify_witness(p['witness'],full_sha256=p['source_witness']['python_semantic_sha256'],native_sha256=p['source_witness']['native_sha256'])
        at=p['logical_step'];io.require(0<=at<=len(steps),'private witness step')
        same(p['source_witness']['noise_past_sha256'],io.digest(tape[:at].tolist()))
        initial_clock=next(e['simulation_time'] for e in events if e['event']=='CONTROLLED_INITIAL')
        same(p['source_witness']['simulation_time'],initial_clock if at==0 else steps[at-1]['simulation_time_after'])
        expected=next(e['ledger'] for e in events if e['event']=='CONTROLLED_INITIAL') if at==0 else steps[at-1]['ledger_after']
        same(p['ledger_before'],expected,'private witness cost')
        refs.append(dict(label=p['label'],sequence=p['sequence'],logical_step=at,native_sha256=p['witness']['native_sha256'],comparison_python_sha256=p['witness']['comparison_python_sha256']))
        io.require(p['label'] not in bylabel,'duplicate private witness');bylabel[p['label']]=p
    same(case['state_witness_refs'],refs)
    expected_labels=['INITIAL']+(['INTERVENTION_PRE','INTERVENTION_POST'] if boundary else [])
    if any(e['agent_event']=='RELOCATION_EVIDENCE' for e in public):expected_labels+=['POST_RELOCATION']
    if returned:expected_labels+=['POST_ACQUISITION']
    if 'POST' in forecasts:expected_labels+=['RATE_PRE','RATE_POST']
    expected_labels+=['FINAL'];same(list(bylabel),expected_labels)
    for left,right in (('INTERVENTION_PRE','INTERVENTION_POST'),('RATE_PRE','RATE_POST')):
        if left in bylabel:io.require(compare_witnesses(bylabel[left]['witness'],bylabel[right]['witness'])['comparison_equal'],'nonphysical operation altered witness')
    history=[];prior=case['initial']
    for s in steps:history.append(dict(at_calls=s['logical_step'],before=prior,command=s['command'],after=s['after']));prior=s['after']
    examples=[]
    for stage in model.STAGES:
        f=forecasts.get(stage);missing='EARLY_END_BEFORE_BOUNDARY' if 'PRE' not in forecasts else 'EARLY_END_DURING_ACQUISITION'
        if f is None:examples.append(dict(spec=spec,stage=stage,view=None,prediction=None,target=None,missing_reason=missing));continue
        io.require(f['forecast_event'] is not None,'missing saved forecast')
        entry=None if 'POST' not in forecasts else forecasts['POST']['view']['memory']['completed_steps']
        y,reason=(None,'NO_EXECUTED_TAIL') if entry is None else model.target(history,entry,returned['memory'])
        examples.append(dict(spec=spec,stage=stage,view=f['view'],prediction=f['forecast_event']['public_payload']['forecast'],target=y,missing_reason=reason,
            input_global_sequence=f['input_event']['sequence'],forecast_global_sequence=f['forecast_event']['sequence']))
    return ledger,steps,bylabel,public,examples


def audit(path,cohort):
    path=Path(path).resolve();m=a.checked(path);out=path.parent/cohort.lower();start=perf_counter_ns();completion=io.read(out/'completion.json')
    io.require(completion['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial allocation cannot pass')
    for n,h in completion['artifact_sha256'].items():io.require(io.sha(out/n)==h,'collection bytes changed '+n)
    summary=io.read(out/'summary.json');cases=list(io.rows(out/'cases.jsonl.gz'));specs=a.population(cohort);same(len(cases),len(specs))
    outer=iter(groupby(io.rows(out/'events.jsonl.gz'),a.case_key));priv=iter(groupby(io.rows(out/'witnesses.jsonl.gz'),a.case_key))
    sequence=psequence=stamp=pstamp=queries=steps_total=0;ledger=dict(counts={},by_phase={});guard={};counts=Counter();unit=None;prefix=None;returns={}
    bank=None if cohort in ('NATIVE','TRAIN') else io.read(path.parent/'learning/bank.json')
    with read_only(guard),gzip.open(out/'examples.jsonl.gz','xt',encoding='utf-8') as ef:
        for spec,case in zip(specs,cases):
            key,it=next(outer);events=list(it);pk,pit=next(priv);private=list(pit);same(key,a.case_key(spec));same(pk,key)
            for rows,is_private in ((events,False),(private,True)):
                for e in rows:
                    for k in (*a.KEYS,*a.IDENTITY):same(e[k],spec[k] if k in spec else m[k])
                    if is_private:io.require(e['sequence']==psequence and e['saved_ns']>=pstamp,'private journal order');psequence+=1;pstamp=e['saved_ns']
                    else:io.require(e['sequence']==sequence and e['saved_ns']>=stamp,'public journal order');sequence+=1;stamp=e['saved_ns']
            same(events[0]['event'],'CASE_ALLOCATION');last=events.pop();same(last['event'],'CASE_COMPLETE');same(last['case_record_sha256'],io.digest(case))
            same(case['event_start_sequence'],events[0]['sequence']);same(case['event_end_sequence_exclusive'],last['sequence'])
            ledger,steps,labels,public,examples=reconstruct(spec,case,events[1:],private,ledger)
            queries+=replay(spec,case,public,steps,bank);steps_total+=len(steps)
            u=a.unit_key(spec)
            if u!=unit:unit=u;prefix=steps;returns={}
            n=min(spec['planned_boundary'],len(prefix));io.require(physical_rows_equal(prefix,steps,n),'common prefix differs');counts['common_prefix_pairs']+=1
            action=spec['acquisition_action'];returned=labels.get('POST_ACQUISITION')
            if action not in returns:returns[action]=(steps,returned)
            else:
                prior,old=returns[action];same(returned is None,old is None)
                n=len(prefix) if returned is None else returned['logical_step']
                io.require(physical_rows_equal(prior,steps,n),'common acquisition differs between rate arms');counts['common_acquisition_pairs']+=1
            for r in examples:
                counts[r['stage']+'/'+(r['missing_reason'] or 'FACTUAL_TARGET')]+=1
                ef.write(json.dumps(normalize(r),separators=(',',':'),allow_nan=False)+'\n')
        io.require(next(outer,None) is None and next(priv,None) is None,'unallocated journal cases')
    same(summary['control_steps'],steps_total);same(summary['events'],sequence);same(summary['private_records'],psequence);same(summary['lifecycle'],ledger)
    same(summary['network_guard']['attempted_network_calls'],0);same(ledger['counts']['reset_attempts'],len(cases)*51)
    io.require(steps_total<=a.limits(cohort)['control_steps'] and ledger['counts']['simulation_frames_completed']<=a.limits(cohort)['physical_frames'],'phase budget')
    result=dict(integrity='PASSED',cohort=cohort,manifest_id=m['manifest_id'],executions=len(cases),control_steps=steps_total,
        lifecycle=ledger,counters=dict(counts),independent_literal_PI_commands=queries,replay_fixed_policy_queries=queries,
        new_physics=0,new_fits=0,online_LLM_API_calls=0,guard=guard,wall_ns=perf_counter_ns()-start,
        examples_sha256=io.sha(out/'examples.jsonl.gz'),collection_sha256=completion['artifact_sha256'],
        limitations='No independent physics; macro replay shares unchanged primitive; literal PI/host/actuator/lifecycle are separate')
    io.write(out/'audit.json',result);return result
