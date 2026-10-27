"""Separate journal/PI/actuator audit and immutable legacy command specification.

No independent physics is simulated. Macro replay shares the frozen primitive.
Live risk decisions use separate numerical inference, not the deployment actor.
"""
from collections import Counter
from copy import deepcopy
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import gzip,json
import numpy as np
from src.analysis import learned_acquisition_native_io_v1 as a
from src.analysis import correction_transfer_independent_v1 as ind
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.short_probe_journal_audit_v1 import applied,ledger_add,simulation,check_ledger,check_observation,physical_rows_equal,PHYSICAL
from src.analysis.task_passive_audit_v1 import audit_pi
from src.analysis.release_learning_guard_v1 import read_only
from src.probe import correction_scope_program_v1 as actor
from src.probe import correction_scope_model_v1 as model
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
io=a.io


def same(x,y,message='independent native record mismatch'):io.require(io.digest(normalize(x))==io.digest(normalize(y)),message)


def check_noise_commitment(event,tape):
    same(event['tape_sha256_oracle'],io.digest(tape.tolist()))
    same(event['noise_namespace_oracle'],202610272,'native namespace, not historical allocation')


def expected_decision(spec,node):
    pre=node['stage']=='PRE'
    if spec['program']=='DYNAMIC_FORCED_REFERENCE':
        action,rate=a.reference(spec);index=('CONTINUE','VALIDATE8','MOVE_MEASURE').index(action) if pre else (.125,.5,2.,8.).index(rate)
        scores=[1.]*(3 if pre else 4);scores[index]=0.;model_id='FORCED_REFERENCE_V1';kind='FORCED_REFERENCE'
    else:
        bundle=io.read(a.ASSETS/'bundle.json');m=bundle['precritic' if pre else 'receiver']
        scores=ind.prior.literal_predict(m,a.ASSETS,node) if pre else ind.receiver(m,a.ASSETS,node)['scores'][0].tolist()
        index=ind.prior.first_minimum(scores);model_id=m['sha256'];kind='FROZEN_MODEL'
    return dict(schema='LIVE_RISK_DECISION_V1',stage=node['stage'],action=index if pre else None,rate=None if pre else index,
        scores=scores,model_sha256=model_id,input_sha256=io.digest(node),kind=kind)


def command_replay(spec,case,steps):
    from src.rollout.task_registry import create_task_policy
    policy=create_task_policy(spec['task']);cursor=queries=event=0
    def fixed(observation):
        nonlocal queries
        queries+=1;return np.asarray(policy.get_action(np.array(observation,copy=True)),np.float32)
    def emit(kind,payload):
        nonlocal event
        result=dict(normalize(payload),sequence=event,saved_ns=event+1);event+=1;return result
    def step(saved):
        nonlocal cursor
        io.require(cursor<len(steps),'no unexecuted trajectory in command specification replay');r=steps[cursor]
        for key in ('command','phase','raw_policy'):same(saved[key],r[key],'immutable legacy command specification '+key)
        cursor+=1;return StepReceipt(StepObservation(**r['after']),cursor)
    action=case['selected_action'] or 'CONTINUE';rate=.5 if case['selected_rate'] is None else case['selected_rate']
    result=actor.run(spec['task'],StepObservation(**case['initial']),spec['planned_boundary'],action,rate,fixed,step,emit,bank=None)
    same(cursor,len(steps));same(queries,case['policy_queries'])
    for key in ('success','terminated','truncated','total_steps','deadline_loss','stop_reason','policy_queries','movement_steps','measurement_steps','final_memory'):
        same(result['outcome'][key],case[key],'actual execution of selected action/rate '+key)
    return queries

def reconstruct(spec,case,events,private,ledger):
    from src.analysis.continuous_state_witness_v1 import verify_witness,compare_witnesses
    spec=dict(spec)
    selected_action=case['selected_action'];selected_rate=case['selected_rate']
    spec.update(acquisition_action=selected_action or 'CONTINUE',time_constant_s=.5 if selected_rate is None else selected_rate)
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
        elif k=='NOISE_COMMITMENT':check_noise_commitment(e,tape)
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
                legacy=spec['program']=='LEGACY_REFERENCE'
                if legacy:
                    ra,rr=a.reference(spec);same(v['acquisition_action'],ra);same(v['time_constant_s'],rr)
                else:
                    expected_node=ind.prior.literal_node(v);same(p['node'],expected_node,'actual canonical public query')
                    same(v['acquisition_action'],'CONTINUE' if v['stage']=='PRE' else spec['acquisition_action']);same(v['time_constant_s'],.5)
                same(v['memory']['integral_xy'],integral);same(v['memory']['task'],spec['task'])
                same(v['memory']['time_constant_s'],spec['time_constant_s'] if legacy and v['stage']=='POST' else .5)
                io.require(v['stage'] not in forecasts,'repeated forecast stage');forecasts[v['stage']]=dict(view=v,input_event=e,forecast_event=None)
            elif name=='FORECAST':
                parent=local.get(p['input_sequence']);io.require(parent is not None and parent['agent_event']=='FORECAST_INPUT' and p['input_sequence']==p['sequence']-1,'unsaved forecast input')
                stage=parent['public_payload']['value']['stage'];io.require(forecasts[stage]['forecast_event'] is None,'repeat forecast')
                forecasts[stage]['forecast_event']=e
                if spec['program']=='LEGACY_REFERENCE':same(p['forecast'],None)
                else:
                    node=parent['public_payload']['node'];expected=expected_decision(spec,node)
                    ind.equal_tree(expected,p['forecast'],'independent live model decision')
            elif name=='ACQUISITION_CHOICE':
                io.require('PRE' in forecasts and forecasts['PRE']['forecast_event']['saved_ns']<e['saved_ns'],'acquisition before forecast');same(p['action'],spec['acquisition_action'])
                if spec['program']!='LEGACY_REFERENCE':
                    dec=forecasts['PRE']['forecast_event']['public_payload'];same(p['forecast_sequence'],dec['sequence'])
                    same(p['action'],('CONTINUE','VALIDATE8','MOVE_MEASURE')[dec['forecast']['action']])
            elif name=='TASK_MEMORY_RETURN':returned=p; same(p['memory']['integral_xy'],integral)
            elif name=='RATE_PLAN':
                io.require(returned is not None and rate_pending is None,'rate before return');same(p['rate'],spec['time_constant_s']);same(p['memory_mode'],'CARRY');rate_pending=p
                if spec['program']!='LEGACY_REFERENCE':
                    io.require('POST' in forecasts and forecasts['POST']['forecast_event'] is not None,'rate before saved returned-node decision')
                    decision=forecasts['POST']['forecast_event']['public_payload'];same(p['decision_sequence'],decision['sequence'])
                    same(p['rate'],(.125,.5,2.,8.)[decision['forecast']['rate']])
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
    queries=[]
    for stage in ('PRE','POST'):
        f=forecasts.get(stage)
        queries.append(dict(spec={k:spec[k] for k in a.KEYS},stage=stage,available=f is not None,
            view=None if f is None else f['view'],decision=None if f is None else f['forecast_event']['public_payload']['forecast'],
            actual_selected_action=case['selected_action'],actual_selected_rate=case['selected_rate'],
            classification='RECORDED_PRECHOICE_QUERY_NOT_A1_ASSIGNED_RATE_TARGET'))
    return ledger,steps,bylabel,public,queries


def audit(path):
    from src.probe import learned_acquisition_actor_v1 as deployed
    from src.probe.frozen_risk_client_v1 import FrozenRiskClient
    from src.analysis import correction_scope_risk_reference_v1 as main_risk
    from src.analysis import transfer_risk_math_v1 as main_network
    path=Path(path).resolve();m=a.checked(path);out=path.parent/'native';start=perf_counter_ns();completion=io.read(out/'completion.json')
    io.require(completion['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial allocation cannot qualify')
    for name,digest in completion['artifact_sha256'].items():io.require(io.sha(out/name)==digest,'native collection immutable '+name)
    summary=io.read(out/'summary.json');cases=list(io.rows(out/'cases.jsonl.gz'));specs=a.population();same(len(cases),54)
    outer=iter(groupby(io.rows(out/'events.jsonl.gz'),a.case_key));priv=iter(groupby(io.rows(out/'witnesses.jsonl.gz'),a.case_key))
    sequence=psequence=stamp=pstamp=replay_queries=total_steps=0;ledger=dict(counts={},by_phase={});guard={};units={};contexts={};counts=Counter();chains=[];divergences=[]
    def denied(*args,**kwargs):raise RuntimeError('deployed actor/client/main risk inference disabled during independent native audit')
    with read_only(guard),patch.object(deployed,'run',denied),patch.object(FrozenRiskClient,'__call__',denied),patch.object(main_risk,'predict',denied),patch.object(main_network,'forward',denied),gzip.open(out/'decision_queries.jsonl.gz','xt',encoding='utf8') as stream:
        for spec,case in zip(specs,cases):
            a.validate_spec(spec)
            for name in a.KEYS:same(case[name],spec[name])
            key,it=next(outer);events=list(it);pk,pit=next(priv);private=list(pit);same(key,a.case_key(spec));same(pk,key)
            for rows,is_private in ((events,False),(private,True)):
                for e in rows:
                    for k in (*a.KEYS,*a.IDENTITY):same(e[k],spec[k] if k in spec else m[k])
                    if is_private:io.require(e['sequence']==psequence and e['saved_ns']>=pstamp,'private native chronology');psequence+=1;pstamp=e['saved_ns']
                    else:io.require(e['sequence']==sequence and e['saved_ns']>=stamp,'public native chronology');sequence+=1;stamp=e['saved_ns']
            same(events[0]['event'],'CASE_ALLOCATION');last=events.pop();same(last['event'],'CASE_COMPLETE');same(last['case_record_sha256'],io.digest(case))
            same(case['event_start_sequence'],events[0]['sequence']);same(case['event_end_sequence_exclusive'],last['sequence'])
            ledger,steps,witnesses,public,queries=reconstruct(spec,case,events[1:],private,ledger)
            replay_queries+=command_replay(spec,case,steps);total_steps+=len(steps)
            same(sum(e['agent_event']=='ACQUISITION_CHOICE' for e in public),int(case['pre_forecast'] is not None))
            same(sum(e['agent_event']=='RATE_PLAN' for e in public),int(case['post_forecast'] is not None))
            live=sum(e['agent_event']=='FORECAST' and e['public_payload']['forecast'] is not None and e['public_payload']['forecast']['kind']=='FROZEN_MODEL' for e in public)
            same(case['live_model_calls'],live);counts['actual_neural_decision_calls']+=live
            u=a.unit_key(spec);units.setdefault(u,{})[spec['program']]=(steps,witnesses,case)
            for q in queries:stream.write(json.dumps(normalize(q),separators=(',',':'),allow_nan=False)+'\n')
            if spec['program']=='LEARNED_JOINT_BANK0':
                pre=case['pre_forecast'];contexts[(spec['group'],spec['task'],spec['context'])]=None if pre is None else next(e['public_payload'] for e in public if e['agent_event']=='FORECAST' and e['public_payload']['sequence']==pre['forecast_sequence'])['forecast']
                counts['nondefault_neural_programs']+=int(case['selected_action'] not in (None,'CONTINUE') or case['selected_rate'] not in (None,.5))
                tails=[r for r in steps if r['phase']=='TAIL_TASK']
                if case['selected_action']=='MOVE_MEASURE' and case['measurement_steps']>0 and case['post_forecast'] is not None and tails:
                    chains.append(dict(spec=spec,actual_movement_steps=case['movement_steps'],actual_measurement_steps=case['measurement_steps'],actual_tail_steps=len(tails),
                        selected_rate=case['selected_rate'],saved_postdecision_sequence=case['post_forecast']['forecast_sequence']))
        io.require(next(outer,None) is None and next(priv,None) is None,'no unallocated native records')
        for unit,programs in units.items():
            same(set(programs),set(a.PROGRAMS));left,lw,lc=programs['LEGACY_REFERENCE'];right,rw,rc=programs['DYNAMIC_FORCED_REFERENCE']
            same(len(left),len(right));io.require(physical_rows_equal(left,right,len(left)),'new forced interface changed actual physical execution')
            for label in ('INITIAL','FINAL'):
                same(lw[label]['witness']['native_sha256'],rw[label]['witness']['native_sha256'],'forced native state match')
                same(lw[label]['witness']['comparison_python_sha256'],rw[label]['witness']['comparison_python_sha256'],'forced RNG/python state match')
            counts['forced_full_physical_pairs']+=1
            for program in ('DYNAMIC_FORCED_REFERENCE','LEARNED_JOINT_BANK0'):
                candidate,_,c=programs[program];n=min(lc['planned_boundary'],len(left));io.require(physical_rows_equal(left,candidate,n),'common native prefix changed');counts['common_prefix_pairs']+=1
            learned,_,lcase=programs['LEARNED_JOINT_BANK0']
            different=next((i for i,(x,y) in enumerate(zip(left,learned)) if np.asarray(x['command'],np.float32).tobytes()!=np.asarray(y['command'],np.float32).tobytes()),None)
            if different is not None:
                io.require(different>=lc['planned_boundary'],'model altered the common prefix')
                divergences.append(dict(unit=list(unit),first_actual_command_difference=different,reference_command=left[different]['command'],learned_command=learned[different]['command']))
        for group in range(3):
            for task in ('push-v3','reach-v3','door-open-v3'):
                left=contexts[(group,task,'UNCHANGED')];right=contexts[(group,task,'CHANGED')]
                same(left,right,'hidden condition changed pre-observation model decision');counts['hidden_context_prequery_pairs']+=1
                counts['live_hidden_context_prequery_pairs']+=int(left is not None)
    same(summary['control_steps'],total_steps);same(summary['events'],sequence);same(summary['private_records'],psequence);same(summary['lifecycle'],ledger)
    same(summary['network_guard']['attempted_network_calls'],0);same(summary['forbidden_fit_guard']['attempts'],0)
    same(summary['live_model_calls'],counts['actual_neural_decision_calls']);same(ledger['counts']['reset_attempts'],2754)
    io.require(total_steps<=27000 and ledger['counts']['simulation_frames_completed']<=1512000 and replay_queries<=27000,'native full budgets')
    same(counts['forced_full_physical_pairs'],18);same(counts['common_prefix_pairs'],36);same(counts['hidden_context_prequery_pairs'],9)
    software_complete=True;behavior=bool(counts['nondefault_neural_programs'] and divergences and chains)
    gate=dict(status='PASSED_NATIVE_INTEGRATION_ONLY' if software_complete and behavior else 'NATIVE_BEHAVIOR_CHAIN_NOT_ESTABLISHED',
        all54_records_checked=True,forced_full_physical_pairs=18,common_prefix_pairs=36,hidden_context_prequery_pairs=9,
        nondefault_neural_programs=counts['nondefault_neural_programs'],actual_command_divergence_cases=len(divergences),complete_neural_MOVE_measure_correct_tail_chains=len(chains),
        zero_budget_continuity_leakage_weight_change_violations=True,task_gain_qualified=False,algorithm_novelty_established=False,publication_goal_complete=False)
    io.write(out/'native_gate.json',gate);io.write(out/'actual_closed_loop_chains.json',chains);io.write(out/'actual_command_divergences.json',divergences)
    result=dict(integrity='PASSED',manifest_id=m['manifest_id'],executions=54,control_steps=total_steps,lifecycle=ledger,counters=dict(counts),
        independent_literal_PI_commands=replay_queries,audit_fixed_policy_queries=replay_queries,source_macro_and_legacy_actor_shared=True,
        main_actor_and_main_risk_inference_disabled=True,guard=guard,wall_ns=perf_counter_ns()-start,collection_sha256=completion['artifact_sha256'],
        query_sha256=io.sha(out/'decision_queries.jsonl.gz'),native_gate_sha256=io.sha(out/'native_gate.json'),
        new_physics=0,new_model_fits=0,online_LLM_API_calls=0,limitations='Recorded-feedback command specification replay, no independent physics; native qualification is not task-gain qualification')
    io.write(out/'audit.json',result);return result
