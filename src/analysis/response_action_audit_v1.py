"""Read-only full-journal audit and separate PI arithmetic reconstruction.

Replays recorded observations through the public program and frozen fixed policy,
and separately reconstructs lifecycle, actuator order and saved PI arithmetic.
It does not reproduce physics or establish physical safety.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import response_action_io_v1 as allocation
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import response_action_program_v1 as actor
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt

from src.analysis.response_action_rank_audit_v1 import audit_rank

io=allocation.io


def same(a,b,message='record differs'):
    io.require(io.digest(normalize(a))==io.digest(normalize(b)),message)


def audit_pi(plan,command,state,task,step,current,raw):
    """Independent formula; never calls PIPlan.numbers or its consumer."""
    io.require(set(plan)==set(('schema','query','dt_s','integral_limit_command','antiwindup','numbers',
        'physical_response_qualified','safety_guarantee','task_benefit_established')),'strict saved PI plan')
    q=plan['query']; io.require(set(q)==set(('schema','task','step','current','raw_policy','controller','integral_before','time_constant_s')),'strict PI query')
    same(q['schema'],'TASK_PI_QUERY_V1'); same(plan['schema'],'TASK_PI_SAVED_PLAN_V1')
    same(q['task'],task); same(q['step'],step); same(q['current'],current); same(q['raw_policy'],raw); same(q['integral_before'],state)
    for k in ('physical_response_qualified','safety_guarantee','task_benefit_established'): same(plan[k],False)
    same(plan['dt_s'],.0125); same(plan['integral_limit_command'],2.)
    same(plan['antiwindup'],'PROJECT_ACTUAL_FLOAT32_SEND_MINUS_BOUNDED_BASE')
    c=q['controller']; io.require(set(c)==set(('source','matrix_xy','offset')),'strict saved controller')
    io.require(c['source'] in ('UNCORRECTED','ESTIMATED_AFFINE'),'forbidden controller source')
    ti=q['time_constant_s']; io.require(ti in (.125,.5,2.,8.) and type(ti) in (int,float),'unregistered integral rate')
    m=np.asarray(c['matrix_xy'],float); offset=np.asarray(c['offset'],float); r=np.asarray(raw,np.float32)
    io.require(m.shape==(2,2) and offset.shape==(4,) and np.isfinite(m).all() and np.isfinite(offset).all(),'numeric saved inverse')
    base=np.clip(r,-1,1).astype(float); base[:2]=m@base[:2]+offset[:2]; base=np.clip(base,-1,1).astype(np.float32).astype(float)
    error=r[:2].astype(float)/allocation.GAINS[task]; rate=m@(allocation.GAINS[task]*error)/ti
    proposed=np.asarray(state)+.0125*rate; bounded=np.clip(proposed,-2,2)
    unbounded=base[:2]+bounded; limited=np.clip(unbounded,-1,1)
    sent=base.copy(); sent[:2]=limited; sent=sent.astype(np.float32).astype(float); after=sent[:2]-base[:2]
    expected={'position_error_xy_m':error.tolist(),'base_command':base.tolist(),'integral_rate_command_per_s':rate.tolist(),
        'integral_proposed':proposed.tolist(),'integral_bounded':bounded.tolist(),'unclipped_xy_command':unbounded.tolist(),
        'sent_command':sent.tolist(),'integral_after_receipt':after.tolist(),'integral_limit_active':bool(np.any(proposed!=bounded)),
        'send_roundoff_xy':(sent[:2]-limited).tolist(),'send_limit_active':bool(np.any(unbounded!=limited))}
    same(plan['numbers'],expected,'independent PI arithmetic differs'); same(command,sent.tolist(),'saved plan did not drive execution')
    return after.tolist(),{'pi_plans':1,'pi_changed_command_steps':int(np.any(sent!=base)),
        'pi_send_limit_steps':int(np.any(unbounded!=limited)),'pi_integral_limit_steps':int(np.any(proposed!=bounded))}


def replay_program(spec,initial,public,steps,nominal,rank_model):
    """Record callbacks only: no world construction, reset, advance or API."""
    from src.rollout.task_registry import create_task_policy
    policy=create_task_policy(spec['task']); cursor=pi=0; current=deepcopy(initial); counts=Counter(); integral=[0.,0.]; pending=None;rank_pending=None;history=[initial['observation']]
    def fixed(observation):
        same(observation,current['observation'],'stale policy observation'); counts['policy_queries']+=1
        return np.asarray(policy.get_action(np.array(observation,copy=True)),np.float32)
    def emit(kind,payload):
        nonlocal cursor,pending,integral,rank_pending
        io.require(cursor<len(public),'unrecorded public event'); event=public[cursor]; value=event['public_payload']
        same(kind,event['agent_event'],'public program state differs')
        same(payload,{k:v for k,v in value.items() if k not in ('sequence','saved_ns')},'causal public replay differs at '+kind)
        if kind=='FIT_INTENT': counts['independent_c4_c8_refits']+=1
        if kind=='FIT_RESULT': counts['independent_c4_c8_nfev']+=int(value['fit'].get('nfev',0))
        if kind=='PI_PLAN':
            io.require(pending is None,'unconsumed earlier PI plan'); pending=value
            same(value['plan']['query']['integral_before'],integral,'virtual/reset task integral')
        if kind=='RANK_PLAN':
            io.require(rank_pending is None,'unconsumed earlier rank plan');rank_pending=value
        if kind=='RANK_VALIDATED':
            io.require(rank_pending is not None,'validation without saved plan')
            same(value['plan_sequence'],rank_pending['sequence']);same(value['plan_sha256'],rank_pending['plan_sha256'])
            counts['independent_response_model_forward_evaluations']+=value['response_model_forward_evaluations']
            counts['independent_kinematic_proxy_evaluations']+=value['kinematic_proxy_evaluations']
        if kind=='COMMAND' and value.get('rank_plan_sha256') is not None:
            io.require(rank_pending is not None,'rank command without saved plan')
            same(value['decision_sequence'],rank_pending['sequence']);same(value['rank_plan_sha256'],io.digest(rank_pending['plan']))
            counts.update(audit_rank(rank_pending['plan'],value['command'],spec,current,history,value['raw_policy'],rank_model))
            rank_pending=None
        if kind=='COMMAND' and value['pi_plan_sha256'] is not None:
            io.require(pending is not None,'unsaved PI plan')
            same(value['decision_sequence'],pending['sequence']); same(value['pi_plan_sha256'],io.digest(pending['plan']))
            integral,newcounts=audit_pi(pending['plan'],value['command'],integral,spec['task'],value['at_calls'],current,value['raw_policy'])
            counts.update(newcounts)
        if kind=='PI_STATE_COMMIT':
            io.require(pending is not None,'integral commit without saved plan/receipt')
            same(value['plan_sequence'],pending['sequence']); same(value['integral_after'],integral); pending=None
        cursor+=1; return deepcopy(value)
    def respond(saved):
        nonlocal pi,current
        io.require(pi<len(steps),'unrecorded physics'); actual=steps[pi]
        same(saved['command'],actual['command']); same(saved['raw_policy'],actual['raw_policy']); same(saved['phase'],actual['phase'])
        current=actual['after'];history.append(current['observation']); pi+=1; return StepReceipt(StepObservation(**current),pi)
    p=actor.from_spec(spec)
    result=actor.run(spec['task'],StepObservation(**initial),nominal if p.uses_c8 else None,spec['planned_boundary'],p,fixed,respond,emit,rank_model)
    io.require(pi==len(steps) and cursor==len(public) and pending is None and rank_pending is None,'unconsumed record or plan')
    same(result['outcome']['policy_queries'],counts['policy_queries']); same(result['outcome']['integral_final'],integral)
    return result['outcome'],dict(counts)


def audit_case(spec,case,events,private,nominal,ledger_before,rank_model=None):
    from src.analysis.short_probe_journal_audit_v1 import applied,check_ledger,ledger_add,simulation,check_observation
    from src.analysis.continuous_state_witness_v1 import verify_witness,compare_witnesses
    for k,v in spec.items(): same(case[k],v,'allocation mismatch')
    io.require(case['completed'] and case['environment_closed'] and case['error'] is None and case['close_error'] is None,'incomplete execution retained but cannot pass')
    same(case['ledger_before'],ledger_before); same(case['initial_fault_oracle'],allocation.initial_fault()); same(case['destination_oracle'],allocation.destination(spec))
    same(case['captures'],0); same(case['restores'],0)
    ledger=deepcopy(ledger_before); current=initial=clock=command=intent=reset=None; first_clock=None
    steps=[]; public=[]; local={}; factories=0; resets=Counter(); tape=allocation.noise(spec['seed'],spec['noise_namespace']); fault=allocation.initial_fault(); boundary=None
    allowed={'FACTORY_INTENT','FACTORY_COMPLETE','LIFECYCLE_RESET_INTENT','LIFECYCLE_RESET_COMPLETE','CONTROLLED_INITIAL',
        'NOISE_COMMITMENT','AGENT_EVENT','STEP_INTENT','STEP_COMPLETE','PHYSICAL_BOUNDARY','FAULT_BOUNDARY'}
    for e in events:
        kind=e['event']; io.require(kind in allowed,'unknown host mutation: '+kind)
        if kind=='FACTORY_INTENT':
            io.require(factories==0 and current is None,'repeat factory'); same(e['ledger'],ledger); factories=1
        elif kind=='LIFECYCLE_RESET_INTENT':
            phase=e['phase']; io.require(reset is None and current is None,'nested or mid-task reset')
            io.require((factories==1 and phase=='GOAL_GENERATION' and resets[phase]<50) or
                (factories==2 and phase=='CONTROLLED_RESET' and resets[phase]==0),'unallocated reset')
            same(e['before'],ledger); ledger=ledger_add(ledger,phase,'reset_attempts',1); reset=e
        elif kind=='LIFECYCLE_RESET_COMPLETE':
            io.require(reset is not None and e['intent_sequence']==reset['sequence'] and e['phase']==reset['phase'],'orphan reset')
            ledger=simulation(ledger,e['phase'],100,500); ledger=ledger_add(ledger,e['phase'],'reset_completed',1)
            same(e['after'],ledger); resets[e['phase']]+=1; reset=None
        elif kind=='FACTORY_COMPLETE':
            io.require(factories==1 and resets['GOAL_GENERATION']==50 and reset is None,'factory accounting'); same(e['ledger'],ledger); factories=2
        elif kind=='CONTROLLED_INITIAL':
            io.require(current is None and factories==2 and resets['CONTROLLED_RESET']==1,'exactly one controlled reset')
            same(e['ledger'],ledger); same(e['task'],spec['task']); same(e['observation'],case['initial']['observation'])
            initial=current=deepcopy(case['initial']); check_observation(current); first_clock=clock=e['simulation_time']
        elif kind=='NOISE_COMMITMENT':
            io.require(current is not None and not public and e['at_calls']==0,'late replacement of noise')
            same(e['noise_namespace_oracle'],spec['noise_namespace']); same(e['tape_sha256_oracle'],io.digest(tape.tolist()))
        elif kind=='AGENT_EVENT':
            io.require(current is not None and command is None and intent is None,'public event inside a pending action')
            p=e['public_payload']; io.require(p['sequence']==len(public) and p['at_calls']==len(steps) and p['saved_ns']<=e['saved_ns'],'public chronology')
            public.append(e); local[p['sequence']]=e
            if e['agent_event']=='COMMAND':
                io.require(not any(current[k] for k in ('success','terminated','truncated')) and len(steps)<500,'step after end/cap')
                same(p['before'],current); io.require(p['decision_sequence']<p['sequence'] and p['decision_sequence'] in local,'future/unsaved decision')
                sent=np.asarray(p['command'],np.float32); io.require(sent.shape==(4,) and np.isfinite(sent).all() and np.all(abs(sent)<=1),'invalid send')
                same(p['command'],sent.tolist()); command=e
        elif kind=='STEP_INTENT':
            io.require(command is not None and intent is None and e['logical_step']==len(steps),'unsaved/duplicate action')
            if len(steps)>=spec['planned_boundary']: io.require(boundary is not None,'missed hidden boundary')
            same(e['global_command_sequence'],command['sequence']); same(e['command'],command['public_payload']['command'])
            same(e['phase'],command['public_payload']['phase']); same(e['ledger_before'],ledger); intent=e
        elif kind=='STEP_COMPLETE':
            io.require(command is not None and intent is not None and e['logical_step']==len(steps) and e['noise_cursor_after']==len(steps)+1,'response/noise cursor')
            same(e['intent_sequence'],intent['sequence']); same(e['global_command_sequence'],command['sequence'])
            for k in ('command','phase','raw_policy'): same(e[k],command['public_payload'][k])
            io.require(command['saved_ns']<=intent['saved_ns']<=e['execution_started_ns']<=e['completed_ns']<=e['saved_ns'],'choice saved after physical outcome')
            same(e['ledger_before'],ledger); ledger=simulation(ledger,'CONTROL',1,5); same(e['ledger_after'],ledger)
            io.require(np.isclose(e['simulation_time_before'],clock,atol=1e-10,rtol=0) and np.isclose(e['simulation_time_after']-clock,.0125,atol=1e-10,rtol=0),'physical clock discontinuity')
            same(e['executed_action_oracle'],applied(e['command'],fault,tape[len(steps)]),'float32 transform/noise/final-clip order')
            check_observation(e['after']); same(e['after']['success'],bool(e['info'].get('success',False)))
            io.require(np.isfinite(e['reward']),'nonfinite reward'); steps.append(e); current=e['after']; clock=e['simulation_time_after']; command=intent=None
        elif kind=='PHYSICAL_BOUNDARY':
            io.require(len(steps) in (4,8) and e['logical_step']==len(steps),'invalid physical boundary')
            same(e['noise_past_sha256'],io.digest(tape[:len(steps)].tolist())); same(e['simulation_time'],clock)
        elif kind=='FAULT_BOUNDARY':
            io.require(boundary is None and command is None and intent is None and len(steps)==spec['planned_boundary']==e['logical_step']
                and not any(current[k] for k in ('success','terminated','truncated')),'repeat/late/nonlive boundary')
            same(e['old_fault_oracle'],fault); fault=allocation.destination(spec); same(e['new_fault_oracle'],fault)
            same(e['changed_oracle'],spec['context']=='CHANGED'); same(e['before'],e['after'],'boundary changed state/RNG/time'); boundary=e
    io.require(command is None and intent is None and reset is None,'unfinished physical action')
    same(case['final'],current); same(case['ledger_before_close'],ledger); same(case['ledger_after_close'],ledger); check_ledger(ledger)
    same(case['boundary_applied'],boundary is not None)
    missing=None if boundary is not None else 'EARLY_SUCCESS' if current['success'] else 'ENVIRONMENT_ENDED' if current['terminated'] or current['truncated'] else case['stop_reason']
    same(case['boundary_missing_reason'],missing)
    io.require(len(steps)==case['total_steps']==case['host_attempts']==case['host_returned']==case['physical_rows_count']<=500,'step costs differ')
    labels=['INITIAL']+(['INTERVENTION_PRE','INTERVENTION_POST'] if boundary is not None else [])
    moved=[e for e in public if e['agent_event']=='POST_MOVE_TASK_ENTRY']
    if moved: labels+=['POST_MOVEMENT']
    labels+=['FINAL']; same([p['label'] for p in private],labels,'missing/extra private witness'); same(case['movement_available'],bool(moved))
    refs=[]
    for p in private:
        io.require(p['event']=='STATE_WITNESS','unknown private event'); same(p['ledger_before'],p['ledger_after'],'witness advanced physics')
        anchor=next((e for e in events if e['sequence']==p['source_anchor_sequence']),None)
        io.require(anchor is not None and anchor['saved_ns']==p['source_anchor_saved_ns']<=p['started_ns']<=p['completed_ns']<=p['saved_ns'],'private chronology')
        verify_witness(p['witness'],full_sha256=p['source_witness']['python_semantic_sha256'],native_sha256=p['source_witness']['native_sha256'])
        at=0 if p['label']=='INITIAL' else spec['planned_boundary'] if p['label'].startswith('INTERVENTION_') else moved[0]['public_payload']['at_calls'] if p['label']=='POST_MOVEMENT' else len(steps)
        same(p['logical_step'],at); same(p['source_witness']['noise_past_sha256'],io.digest(tape[:at].tolist()))
        same(p['source_witness']['simulation_time'],first_clock if at==0 else steps[at-1]['simulation_time_after'])
        expected=next(e['ledger'] for e in events if e['event']=='CONTROLLED_INITIAL') if at==0 else steps[at-1]['ledger_after']
        same(p['ledger_before'],expected,'private physical ledger')
        refs.append({'label':p['label'],'sequence':p['sequence'],'logical_step':at,'native_sha256':p['witness']['native_sha256'],
            'comparison_python_sha256':p['witness']['comparison_python_sha256']})
    same(case['state_witness_refs'],refs)
    if boundary is not None:
        pair=[p for p in private if p['label'].startswith('INTERVENTION_')]
        io.require(compare_witnesses(pair[0]['witness'],pair[1]['witness'])['comparison_equal'],'boundary state witness mismatch')
        io.require(pair[0]['saved_ns']<boundary['saved_ns']<pair[1]['saved_ns'],'boundary witness order')
    outcome,costs=replay_program(spec,initial,public,steps,nominal,rank_model)
    for k,v in outcome.items(): same(case[k],v,'outcome/cost replay mismatch: '+k)
    same(case['c4_c8_fit_attempts'],costs.get('independent_c4_c8_refits',0)); same(case['c4_c8_fit_results'],case['c4_c8_fit_attempts'])
    same(case['c4_c8_optimizer_nfev'],costs.get('independent_c4_c8_nfev',0))
    same(case['response_model_forward_evaluations'],10*case['rank_steps'] if spec['style']=='F20_RANK' else 0)
    same(case['kinematic_proxy_evaluations'],10*case['rank_steps'] if spec['style']=='KINEMATIC_RANK' else 0)
    same(case['inference_accounting']['intents'],case['rank_steps']);same(case['inference_accounting']['validated'],case['rank_steps'])
    same(case['computation_counters_complete'],True)
    return ledger,{'steps':steps,'private':private,'costs':costs,'movement_end':None if not moved else moved[0]['public_payload']['at_calls']}


def audit(path,cohort):
    path=Path(path).resolve(); m=allocation.load_manifest(path); started=perf_counter_ns(); io.require(cohort in allocation.COHORTS,'audit cohort')
    folder=path.parent/cohort.lower(); completion=io.read(folder/'completion.json')
    io.require(completion['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial collection cannot pass')
    for n,h in completion['artifact_sha256'].items(): io.require(io.sha(folder/n)==h,'collection bytes changed: '+n)
    selected=io.read(path.parent/'selection.json')['selected_F20_weight'] if cohort=='QUAL' else None
    specs=allocation.population(cohort,selected); cases=list(io.rows(folder/'cases.jsonl.gz')); same(len(cases),len(specs))
    outer=iter(groupby(io.rows(folder/'events.jsonl.gz'),lambda e:e['case_id'])); priv=iter(groupby(io.rows(folder/'witnesses.jsonl.gz'),lambda e:e['case_id']))
    nominal,rank_models,_=allocation.source_models(); ledger={'counts':{},'by_phase':{}}; sequence=psequence=stamp=pstamp=0; counts=Counter(); coverage=Counter()
    unit=None; initial_reference=c8_reference=move_reference=None; checks=Counter()
    from src.analysis.continuous_state_witness_v1 import compare_witnesses
    from src.analysis.short_probe_journal_audit_v1 import physical_rows_equal
    for spec,case in zip(specs,cases):
        key,it=next(outer); events=list(it); pk,pit=next(priv); ps=list(pit); same(key,spec['case_id']); same(pk,key)
        for rows,private in ((events,False),(ps,True)):
            for e in rows:
                for k in (*io.IDENTITY,*allocation.KEYS): same(e[k],m[k] if k in io.IDENTITY else spec[k])
                if private:
                    io.require(e['sequence']==psequence and e['saved_ns']>=pstamp,'private journal sequence/time'); psequence+=1; pstamp=e['saved_ns']
                else:
                    io.require(e['sequence']==sequence and e['saved_ns']>=stamp,'journal sequence/time'); sequence+=1; stamp=e['saved_ns']
        for k in io.IDENTITY: same(case[k],m[k])
        if cohort=='QUAL':
            io.require(io.read(path.parent/'selection.json')['locked_ns']<events[0]['saved_ns'],'qualification preceded parameter lock')
        receipt=events.pop(); same(receipt['event'],'CASE_COMPLETE'); same(receipt['case_record_sha256'],io.digest(case))
        same(case['event_start_sequence'],events[0]['sequence']); same(case['event_end_sequence_exclusive'],receipt['sequence'])
        same(receipt['total_steps'],case['total_steps']); same(receipt['deadline_loss'],case['deadline_loss'])
        ledger,result=audit_case(spec,case,events,ps,nominal[spec['task']],ledger,rank_models[spec['task']] if spec['style']=='F20_RANK' else None)
        counts.update(result['costs']); counts['control_steps']+=len(result['steps']); counts['successes']+=int(case['success'])
        if result['costs'].get('pi_plans',0):coverage[allocation.spec_id(spec)]+=1
        if result['costs'].get('rank_plans',0):coverage[allocation.spec_id(spec)+'/'+spec['task']]+=1
        if spec['unit_id']!=unit:
            unit=spec['unit_id']; initial_reference=ps[0]; c8_reference=move_reference=None
        else:
            io.require(compare_witnesses(initial_reference['witness'],ps[0]['witness'])['comparison_equal'],'paired initial state differs'); checks['initial_pairs']+=1
        if actor.from_spec(spec).uses_c8:
            if c8_reference is None: c8_reference=result
            else:
                n=min(8,len(c8_reference['steps'])); io.require(physical_rows_equal(c8_reference['steps'],result['steps'],n),'common C8 prefix differs'); checks['c8_prefix_pairs']+=1
        if spec['style'].startswith('MOVE_'):
            if move_reference is None: move_reference=result
            else:
                same(result['movement_end'],move_reference['movement_end'],'common movement availability differs')
                n=result['movement_end'] if result['movement_end'] is not None else min(len(result['steps']),len(move_reference['steps']))
                io.require(physical_rows_equal(result['steps'],move_reference['steps'],n),'common movement physical prefix differs')
                if result['movement_end'] is not None:
                    a=next(p for p in result['private'] if p['label']=='POST_MOVEMENT'); b=next(p for p in move_reference['private'] if p['label']=='POST_MOVEMENT')
                    io.require(compare_witnesses(a['witness'],b['witness'])['comparison_equal'],'common post-movement state differs')
                checks['movement_pairs']+=1
    io.require(next(outer,None) is None and next(priv,None) is None,'extra unallocated records')
    summary=io.read(folder/'summary.json'); same(summary['lifecycle'],ledger); same(summary['control_steps'],counts['control_steps'])
    same(summary['executions'],len(specs)); same(summary['events'],sequence); same(summary['private_records'],psequence)
    same(summary['online_c4_c8_fit_attempts'],counts['independent_c4_c8_refits']); same(summary['new_api_calls'],0); same(summary['network_guard'],{'attempted_network_calls':0})
    same(summary['response_model_forward_evaluations_completed'],counts['independent_response_model_forward_evaluations'])
    same(summary['kinematic_proxy_evaluations_completed'],counts['independent_kinematic_proxy_evaluations'])
    if cohort=='QUAL': same(summary['selection_sha256'],io.sha(path.parent/'selection.json'))
    limits=allocation.limits(cohort)
    io.require(counts['control_steps']<=limits['control_steps'] and ledger['counts']['reset_attempts']==limits['all_resets']
        and ledger['counts']['simulation_frames_attempted']<=limits['physical_frames'],'whole-study budget')
    io.require(counts['independent_response_model_forward_evaluations']<=limits['response_model_forward_evaluations']
        and counts['independent_kinematic_proxy_evaluations']<=limits['kinematic_proxy_evaluations']
        and counts['independent_rank_raw_coefficient_forecasts']<=limits['independent_rank_raw_coefficient_forecasts'],'prediction computation budget')
    contract='NOT_APPLICABLE'
    if cohort=='SOFTWARE_NATIVE':
        expected=[allocation.program_id(p.style,p.time_constant_s,p.regularization_weight) for p in allocation.programs(cohort) if p.uses_pi]
        expected += [allocation.program_id(p.style,p.time_constant_s,p.regularization_weight)+'/'+task for p in allocation.programs(cohort) if p.uses_rank for task in allocation.GAINS]
        contract='PASSED' if all(coverage[p]>0 for p in expected) else 'INCOMPLETE_NO_REPLACEMENT'
    v={**{k:m[k] for k in io.IDENTITY},'cohort':cohort,'integrity':'PASSED','native_software_contract':contract,
        'executions':len(cases),'costs':dict(counts),'lifecycle':ledger,'common_prefix_checks':dict(checks),
        'pi_actual_effect_coverage':dict(coverage),'new_environment_steps':0,'new_api_calls':0,'new_response_predictor_training':0,
        'completion_sha256':io.sha(folder/'completion.json'),'auditor_sha256':io.sha(__file__),'rank_auditor_sha256':io.sha(allocation.ROOT/'src/analysis/response_action_rank_audit_v1.py'),'wall_ns':perf_counter_ns()-started,
        'scope':'Read-only program replay and independent raw-coefficient rank/PI/actuator/cost reconstruction; source-generated witnesses, not physics reproduction or safety proof'}
    io.write(folder/'audit.json',v); return v
