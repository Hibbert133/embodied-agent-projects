"""Read-only physical ledger audit, separate PID/memory formulas and record replay."""
from pathlib import Path
from copy import deepcopy
from dataclasses import asdict
from collections import Counter
from time import perf_counter_ns
import math
import numpy as np
from src.analysis import acquisition_reference_io_v1 as allocation
from src.analysis.response_action_audit_v1 import same,audit_pi
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe import acquisition_reference_program_v1 as actor
io=allocation.io


def physical_audit(spec,case,events,private,ledger_before):
    from src.analysis.short_probe_journal_audit_v1 import applied,check_ledger,ledger_add,simulation,check_observation
    from src.analysis.continuous_state_witness_v1 import verify_witness,compare_witnesses
    for k,v in spec.items(): same(case[k],v,'allocation mismatch')
    io.require(case['completed'] and case['environment_closed'] and case['error'] is None and case['close_error'] is None,'incomplete execution retained but cannot pass')
    same(case['ledger_before'],ledger_before); same(case['initial_fault_oracle'],allocation.initial_fault()); same(case['destination_oracle'],allocation.destination(spec))
    same(case['captures'],0); same(case['restores'],0)
    ledger=deepcopy(ledger_before); current=initial=clock=command=intent=reset=None; first_clock=None
    steps=[]; public=[]; local={}; factories=0; resets=Counter(); tape=allocation.noise(spec); fault=allocation.initial_fault(); boundary=None
    allowed={'CASE_ALLOCATION','FACTORY_INTENT','FACTORY_COMPLETE','LIFECYCLE_RESET_INTENT','LIFECYCLE_RESET_COMPLETE','CONTROLLED_INITIAL',
        'NOISE_COMMITMENT','AGENT_EVENT','STEP_INTENT','STEP_COMPLETE','PHYSICAL_BOUNDARY','FAULT_BOUNDARY'}
    for e in events:
        kind=e['event']; io.require(kind in allowed,'unknown host mutation: '+kind)
        if kind=='CASE_ALLOCATION':
            io.require(current is None and factories==0,'late/repeat allocation');same(e['assignment'],'FIXED_STANDARD_COMPLETE_PROGRAM');same(e['no_online_method_selection'],True)
        elif kind=='FACTORY_INTENT':
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
            same(e['noise_namespace_oracle'],150012 if spec['cohort']=='SOFTWARE_NATIVE' else 150002); same(e['tape_sha256_oracle'],io.digest(tape.tolist()))
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
    relocated=[e for e in public if e['agent_event']=='RELOCATION_EVIDENCE']
    if relocated:labels+=['POST_RELOCATION']
    moved=[e for e in public if e['agent_event'] in ('TASK_MEMORY_RETURN','POST_MOVE_TASK_ENTRY')]
    if moved: labels+=['POST_ACQUISITION']
    labels+=['FINAL']; same([p['label'] for p in private],labels,'missing/extra private witness')
    refs=[]
    for p in private:
        io.require(p['event']=='STATE_WITNESS','unknown private event'); same(p['ledger_before'],p['ledger_after'],'witness advanced physics')
        anchor=next((e for e in events if e['sequence']==p['source_anchor_sequence']),None)
        io.require(anchor is not None and anchor['saved_ns']==p['source_anchor_saved_ns']<=p['started_ns']<=p['completed_ns']<=p['saved_ns'],'private chronology')
        verify_witness(p['witness'],full_sha256=p['source_witness']['python_semantic_sha256'],native_sha256=p['source_witness']['native_sha256'])
        at=0 if p['label']=='INITIAL' else spec['planned_boundary'] if p['label'].startswith('INTERVENTION_') else relocated[0]['public_payload']['at_calls'] if p['label']=='POST_RELOCATION' else moved[0]['public_payload']['at_calls'] if p['label']=='POST_ACQUISITION' else len(steps)
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
    return ledger,steps,public


def replay(spec,case,public,steps,nominal):
    from src.rollout.task_registry import create_task_policy
    policy=create_task_policy(spec['task']);cursor=event_cursor=0;current=deepcopy(case['initial']);counts=Counter()
    def query(observation):
        same(observation,current['observation'],'fixed policy current observation');counts['independent_policy_queries']+=1
        return np.asarray(policy.get_action(np.asarray(observation).copy()),np.float32)
    def emit(kind,payload):
        nonlocal event_cursor
        e=public[event_cursor];event_cursor+=1;p=e['public_payload'];same(kind,e['agent_event'])
        same(normalize(payload),{k:v for k,v in p.items() if k not in ('sequence','saved_ns')},'full saved transcript '+kind)
        if kind=='FIT_INTENT':counts['independent_c4_c8_refits']+=1
        if kind=='FIT_RESULT':counts['independent_c4_c8_nfev']+=int(p['fit'].get('nfev',0))
        return deepcopy(p)
    def step(saved):
        nonlocal cursor,current
        e=steps[cursor];same(saved['sequence'],next(v['public_payload']['sequence'] for v in public if v['sequence']==e['global_command_sequence']))
        same(saved['command'],e['command']);same(saved['before'],current);same(saved['raw_policy'],e['raw_policy']);cursor+=1;current=deepcopy(e['after'])
        return StepReceipt(StepObservation(**current),cursor)
    r=actor.run(spec['task'],StepObservation(**case['initial']),spec['planned_boundary'],spec['program'],nominal if actor.is_legacy(spec['program']) else None,query,step,emit)
    same(cursor,len(steps));same(event_cursor,len(public))
    for k,v in r['outcome'].items():same(case[k],v,'outcome mismatch '+k)
    same(case['c4_c8_fit_attempts'],counts.get('independent_c4_c8_refits',0));same(case['c4_c8_fit_results'],case['c4_c8_fit_attempts'])
    same(case['c4_c8_optimizer_nfev'],counts.get('independent_c4_c8_nfev',0));return counts


def readiness(history,anchor):
    return len(history)>=4 and max(abs(x-y) for x,y in zip(history[-1][:3],anchor))<=.015 and math.dist(history[-1][:3],history[-1][4:7])>=.1 and all(max(abs(x-y) for x,y in zip(u[:3],v[:3]))<=.003 for u,v in zip(history[-4:-1],history[-3:]))


def pid_numbers(history,anchor,lifted,old,method):
    """Separate scalar conditional-integral arithmetic for RAW relocation."""
    p=history[-1][:3];target=anchor if lifted else [*history[0][:2],anchor[2]]
    delta=[0.,0.,0.] if len(history)<2 else [p[j]-history[-2][j] for j in range(3)]
    error=[target[j]-p[j] for j in range(3)];feedback=[8.*error[j]-16.*delta[j] for j in range(3)];updated=list(old)
    if method.endswith('_PID'):
        for j in range(2):
            candidate=float(min(.5,max(-.5,old[j]+.32*error[j])));change=candidate-old[j]
            if not ((feedback[j]+candidate>.5 and change>0) or (feedback[j]+candidate<-.5 and change<0)):updated[j]=candidate
    command=np.asarray([min(.5,max(-.5,feedback[j]+(updated[j] if j<2 else 0.))) for j in range(3)]+[-1.],np.float32).tolist()
    return updated,command


def independent_raw(spec,case,public,steps):
    io.require(not actor.is_legacy(spec['program']),'RAW-specific independent memory check')
    current=deepcopy(case['initial']);at=0;integral=[0.,0.];controller={'source':'UNCORRECTED','matrix_xy':[[1.,0.],[0.,1.]],'offset':[0.,0.,0.,0.]}
    plan=next_integral=None;suspended=False;history=[];anchor=None;lifted=False;relocation_integral=[0.,0.];updated=None;reference=None;return_event=None;adopt_plan=None;counts=Counter()
    def memory():return {'schema':'TASK_MEMORY_OPTION_V1','task':spec['task'],'completed_steps':at,'current':current,'controller':controller,'integral_xy':integral,'time_constant_s':.5}
    for e in public:
        kind=e['agent_event'];p=e['public_payload'];same(p['at_calls'],at,'independent memory clock')
        if kind=='PI_PLAN':
            io.require(plan is None and not suspended,'unsaved/suspended PI');plan=p['saved_plan']
            same(plan['before_memory_sha256'],io.digest(memory()));same(plan['pi_plan_sha256'],io.digest(plan['pi_plan']));same(plan['pi_plan']['query']['controller'],controller)
        elif kind=='COMMAND':
            s=steps[at];same(p['before'],current)
            if p['raw_policy'] is not None:
                io.require(plan is not None and not suspended,'task step without saved memory plan')
                next_integral,c=audit_pi(plan['pi_plan'],p['command'],integral,spec['task'],at,current,p['raw_policy']);counts.update(c)
            else:
                io.require(suspended and plan is None,'non-task command outside actual acquisition')
                if p['phase']=='REPOSITION':
                    io.require(updated is not None,'missing saved relocation integral update')
                    want,command=pid_numbers(history,anchor,lifted,relocation_integral,actor.method(spec['program']));same(updated,want);same(p['command'],command,'independent PID send')
                    relocation_integral=list(updated);updated=None;counts['relocation_steps']+=1
                else:
                    io.require(p['phase']=='WARM_PROBE' and reference is not None,'unavailable new measurement')
                    j=counts['probe_steps'];directions=((.4,0,0,0),(0,.4,0,0),(-.4,0,0,0),(0,-.4,0,0));io.require(j<8,'repeated probe')
                    same(p['command'],np.asarray(directions[j%4],np.float32).tolist());counts['probe_steps']+=1
                history.append(s['after']['observation']);lifted=lifted or history[-1][2]>=anchor[2]-.015
            current=deepcopy(s['after']);at+=1
        elif kind=='TASK_MEMORY_COMMIT':
            io.require(plan is not None and next_integral is not None,'task commit before receipt')
            integral=list(next_integral);same(p['memory'],memory());plan=next_integral=None
        elif kind=='ACQUISITION_CHOICE':
            same(p['before_memory'],memory());action='CONTINUE' if spec['program']=='RAW_CONTINUE' else actor.method(spec['program'])
            same(p['action'],action);same(p['behavior_probabilities'],[float(a==action) for a in actor.FIRST_ACTIONS])
        elif kind=='TASK_MEMORY_SUSPEND':
            io.require(not suspended,'repeat task suspension');same(p['memory'],memory());same(p['token'],{'schema':'TASK_MEMORY_SUSPEND_V1','memory_sha256':io.digest(memory()),'at_completed_steps':at});suspended=True
            history=[list(current['observation'])]
        elif kind=='REACQUIRE_CHOICE':
            io.require(suspended and history,'acquisition without task suspension');o=history[0];method=actor.method(spec['program'])
            anchor=[0.,.6,.25] if method.startswith('FIXED_') else [min(.45,max(-.45,o[0])),min(.95,max(.45,o[1])),min(.45,max(.25,o[6]+.12))]
            same(p['anchor'],anchor);same(p['relocation_method'],method);lifted=o[2]>=anchor[2]-.015
        elif kind=='INTEGRAL_UPDATE':
            io.require(suspended and updated is None and counts['relocation_steps']<64 and not readiness(history,anchor),'invalid relocation update')
            same(p['integral_before'],relocation_integral);updated=pid_numbers(history,anchor,lifted,relocation_integral,actor.method(spec['program']))[0];same(p['integral_after'],updated)
        elif kind=='RELOCATION_EVIDENCE':
            reference={'integral_xy':relocation_integral,'at_anchor':readiness(history,anchor),
                'controller':{'source':'RELOCATION_INTEGRAL_REFERENCE','matrix_xy':[[1.,0.],[0.,1.]],'offset':[relocation_integral[0],relocation_integral[1],0.,0.]},
                'parameter_estimate_qualified':False,'task_utility_demonstrated':False}
            same({k:p[k] for k in reference},reference,'separate relocation reference')
        elif kind=='PROBE_ENTRY':
            io.require(readiness(history,anchor),'probe before real anchor readiness');same(p['entry_history'],history[-4:])
        elif kind=='TASK_MEMORY_RETURN':
            io.require(plan is None,'pending task plan at return');same(p['memory'],memory(),'silent integral reset or stale state at return');suspended=False;return_event=p
        elif kind=='TAIL_CHOICE':
            io.require(return_event is not None,'tail before actual return');same(p['parent_return_sequence'],return_event['sequence']);same(p['before_memory_sha256'],io.digest(memory()))
            requested='KEEP' if actor.mode(spec['program']) is None else 'REFERENCE_'+actor.mode(spec['program'])
            valid_reference=counts['probe_steps']==8 or (spec['program'].endswith('_NO_PROBE') and reference is not None and reference['at_anchor'])
            chosen=requested if valid_reference and requested!='KEEP' else 'KEEP'
            same(p['requested_action'],requested);same(p['action'],chosen);same(p['behavior_probabilities'],[float(a==chosen) for a in actor.TAIL_ACTIONS])
        elif kind=='REFERENCE_UPDATE_PLAN':
            io.require(reference is not None and reference['at_anchor'] and (counts['probe_steps']==8 or spec['program'].endswith('_NO_PROBE')) and not suspended,'reference before registered actual acquisition')
            same(p['evidence'],reference);mode=actor.mode(spec['program']);io.require(mode in ('RESET','CARRY'),'reference arm required')
            after=deepcopy(memory());after['controller']={**reference['controller'],'source':'ESTIMATED_AFFINE'};after['integral_xy']=[0.,0.] if mode=='RESET' else list(integral)
            adopt_plan={'schema':'RELOCATION_REFERENCE_UPDATE_V1','mode':mode,'before_memory_sha256':io.digest(memory()),'after_memory':after,'evidence_sha256':io.digest(reference),
                'parameter_identification_qualified':False,'task_benefit_established':False,'bumpless_transfer_established':False}
            same(p['plan'],adopt_plan,'independent reference/memory map')
        elif kind=='REFERENCE_UPDATE_COMMIT':
            io.require(adopt_plan is not None,'reference commit without saved plan');controller=deepcopy(adopt_plan['after_memory']['controller']);integral=list(adopt_plan['after_memory']['integral_xy'])
            same(p['memory'],memory());adopt_plan=None;counts['reference_updates']+=1
    io.require(plan is None and updated is None and adopt_plan is None and not suspended,'unconsumed numerical operation');same(case['final_memory'],memory())
    same(bool(counts['reference_updates']),case['reference_update_applied']);same(counts['pi_plans'],case['policy_queries']);same(at,len(steps));return counts


def audit(path,cohort):
    path=Path(path).resolve();m=allocation.checked(path);out=path.parent/cohort.lower();start=perf_counter_ns();done=io.read(out/'completion.json')
    io.require(done['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial allocation cannot pass')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'collection bytes changed '+n)
    specs=allocation.population(cohort);cases=list(io.rows(out/'cases.jsonl.gz'));events=list(io.rows(out/'events.jsonl.gz'));private=list(io.rows(out/'witnesses.jsonl.gz'))
    same(len(cases),len(specs));nominal,_=allocation.source_models()
    for stream in (events,private):
        stamp=-1
        for i,e in enumerate(stream):
            same(e['sequence'],i);io.require(e['saved_ns']>=stamp,'journal chronology');stamp=e['saved_ns']
            for k in allocation.IDENTITY:same(e[k],m[k])
    ledger={'counts':{},'by_phase':{}};counts=Counter();end=0;prefix={};local={};reloc={};actual_modes=Counter();consumed_private=0
    from src.analysis.continuous_state_witness_v1 import compare_witnesses
    for spec,case in zip(specs,cases):
        same({k:case[k] for k in allocation.KEYS},spec);same(case['event_start_sequence'],end)
        chunk=events[end:case['event_end_sequence_exclusive']];marker=events[case['event_end_sequence_exclusive']];same(marker['event'],'CASE_COMPLETE');same(marker['case_record_sha256'],io.digest(case));end=marker['sequence']+1
        for e in chunk:same({k:e[k] for k in allocation.KEYS},spec)
        priv=[p for p in private if all(p[k]==spec[k] for k in allocation.KEYS)];consumed_private+=len(priv)
        ledger,steps,public=physical_audit(spec,case,chunk,priv,ledger)
        costs=replay(spec,case,public,steps,nominal[spec['task']]);counts.update(costs)
        if not actor.is_legacy(spec['program']):counts.update(independent_raw(spec,case,public,steps))
        counts['control_steps']+=len(steps);key=(spec['group'],spec['task'],spec['context'],'C8' if actor.is_legacy(spec['program']) else 'RAW')
        if key in prefix:
            ref=prefix[key];io.require(compare_witnesses(priv[0]['witness'],ref['private'][0]['witness'])['comparison_equal'],'initial private state differs')
            n=min(spec['planned_boundary'],len(ref['steps']),len(steps))
            for a,b in zip(steps[:n],ref['steps'][:n]):
                for k in ('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(a[k],b[k],'same-source physical prefix differs')
            counts['common_prefix_pairs']+=1
        else:prefix[key]={'steps':steps,'private':priv}
        if spec['program'].startswith('LOCAL_PID_'):
            rk=(spec['group'],spec['task'],spec['context']);rp=next((p for p in priv if p['label']=='POST_RELOCATION'),None)
            n=len(steps) if rp is None else rp['logical_step']
            if rk in reloc:
                old=reloc[rk];same(n,old['n']);same(rp is None,old['return'] is None)
                for a,b in zip(steps[:n],old['steps'][:n]):
                    for k in ('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(a[k],b[k],'warm/no-probe common relocation differs')
                if rp is not None:io.require(compare_witnesses(rp['witness'],old['return']['witness'])['comparison_equal'],'common pre-probe private state differs')
                counts['common_pre_probe_pairs']+=1
            else:reloc[rk]={'steps':steps,'return':rp,'n':n}
        if spec['program'] in ('LOCAL_PID_KEEP','LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_CARRY'):
            lk=(spec['group'],spec['task'],spec['context']);ret=next((p for p in priv if p['label']=='POST_ACQUISITION'),None)
            if lk in local:
                old=local[lk];same(ret is None,old['return'] is None,'post-acquisition availability differs')
                n=len(steps) if ret is None else ret['logical_step'];same(n,old['n'])
                for a,b in zip(steps[:n],old['steps'][:n]):
                    for k in ('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(a[k],b[k],'common real local-PID acquisition differs')
                if ret is not None:io.require(compare_witnesses(ret['witness'],old['return']['witness'])['comparison_equal'],'same acquisition state/RNG differs')
                counts['common_post_acquisition_pairs']+=1
            else:local[lk]={'steps':steps,'return':ret,'n':len(steps) if ret is None else ret['logical_step']}
        if case['reference_update_applied']:actual_modes[case['reference_update_mode']]+=1
    same(end,len(events));same(consumed_private,len(private));summary=io.read(out/'summary.json')
    same(summary['lifecycle'],ledger);same(summary['control_steps'],counts['control_steps']);same(summary['executions'],len(specs));same(summary['events'],len(events));same(summary['private_records'],len(private))
    same(summary['c4_c8_fit_attempts'],counts['independent_c4_c8_refits']);same(summary['network_guard'],{'attempted_network_calls':0});same(summary['online_LLM_API_calls'],0)
    limits=allocation.limits(cohort);io.require(counts['control_steps']<=limits['control_steps'] and ledger['counts']['reset_attempts']==limits['all_resets'] and ledger['counts']['simulation_frames_attempted']<=limits['physical_frames'],'whole phase budget')
    io.require(counts['independent_c4_c8_refits']<=limits['c4_c8_fit_attempts'],'independent replay fit budget')
    native='NOT_APPLICABLE' if cohort!='SOFTWARE_NATIVE' else 'PASSED' if actual_modes['RESET'] and actual_modes['CARRY'] and counts['independent_c4_c8_refits'] else 'FAILED_COVERAGE'
    result={'integrity':'PASSED','cohort':cohort,'native_software_contract':native,'executions':len(specs),'costs':dict(counts),'actual_reference_modes':dict(actual_modes),
        'collection_completion_sha256':io.sha(out/'completion.json'),'artifact_sha256':done['artifact_sha256'],'wall_ns':perf_counter_ns()-start,
        'new_environment_steps':0,'new_response_training':0,'new_online_LLM_API_calls':0,'standard_reference_not_new_algorithm':True,'publication_goal_complete':False}
    io.write(out/'audit.json',result);return result
