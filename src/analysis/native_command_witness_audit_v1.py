"""Independent execution arithmetic and native measurements; no environment/fits."""
from collections import Counter,defaultdict
from copy import deepcopy
from math import sqrt,fsum
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import native_command_witness_io_v1 as a
from src.analysis.command_target_sources_v1 import GroupedJournal
from src.analysis.short_probe_journal_audit_v1 import applied,ledger_add,simulation
from src.analysis.acquisition_reference_audit_v1 import replay,independent_raw
from src.analysis.response_action_audit_v1 import same
io=a.io


def target(before,command):
    requested=[float(t)+float(np.float32(np.float32(u)*np.float32(.01))) for t,u in zip(before,command)]
    after=[min(hi,max(lo,x)) for x,lo,hi in zip(requested,(-.5,.4,.05),(.5,1.,.5))]
    return {'target':after,'requested_target':requested,'workspace_clip_axes':[x!=y for x,y in zip(requested,after)]}


def public_state(task,n,q):return {'schema':'PUBLIC_NOMINAL_COMMAND_TARGET_V1','task':task,'completed_commands':n,'target':list(q),
    'source':'DECLARED_RESET_PRIOR_AND_PAST_SENT_COMMANDS','assumption':'IDENTITY_INPUT_ZERO_EXECUTION_NOISE',
    'is_observed_private_state':False,'physical_state_qualified':False,'probability_or_safety_guarantee':False}


def distance(a,b):return sqrt(fsum((x-y)**2 for x,y in zip(a,b)))*1000.


def audit_case(spec,c,events,private,export,ledger):
    a.validate_spec(spec);same({k:c[k] for k in a.KEYS},spec);same(c['ledger_before'],ledger)
    io.require(c['completed'] and c['environment_closed'] and c['error'] is c['close_error'] is None,'complete native case')
    io.require(c['captures']==c['restores']==0,'no undo or state capture')
    byseq={e['sequence']:e for e in events};steps=[];public=[];plan=None;intent=None;fault=a.initial_fault();n=0;boundary=0;sent=[0.,.6,.2]
    noise=a.noise(spec);before_native={};after_native={};initials=[p for p in private if p['label']=='INITIAL'];finals=[p for p in private if p['label']=='FINAL']
    io.require(len(initials)==len(finals)==1 and len(private)==2*c['total_steps']+2,'full native measurement denominator')
    initial=initials[0];address=(initial['model_address_oracle'],initial['data_address_oracle']);actual=initial['mocap_pos_oracle'][0]
    same(actual,[0.,.6,.2]);same(initial['at_calls'],0);same(initial['mocap_dtype_oracle'],'<f8')
    for p in private:
        io.require(p['event']=='NATIVE_TARGET_VALUES' and p['evaluator_only'] is True and p['permitted_training_input_or_label'] is False,'private measurement purpose')
        same((p['model_address_oracle'],p['data_address_oracle']),address,'same native world')
        io.require(np.isclose(p['simulation_time'],initial['simulation_time']+.0125*p['at_calls'],atol=1e-9,rtol=0),'private clock')
        anchor=byseq[p['last_public_event']['sequence']];same(p['last_public_event']['saved_ns'],anchor['saved_ns']);io.require(anchor['saved_ns']<p['saved_ns'],'native witness ordered after anchor')
        if p['label']=='BEFORE_STEP':io.require(p['at_calls'] not in before_native,'duplicate before witness');before_native[p['at_calls']]=p
        elif p['label']=='AFTER_STEP':io.require(p['at_calls'] not in after_native,'duplicate after witness');after_native[p['at_calls']]=p
        else:io.require(p['label'] in ('INITIAL','FINAL'),'unknown private phase')
    expected_export={'schema':'PUBLIC_COMMAND_WITNESS_TRAJECTORY_V1','task':spec['task'],'initial_observation':c['initial']['observation'],'steps':[]}
    target_errors=[];sent_errors=[];native_clips=0;pending_reset=None
    for e in events:
        kind=e['event']
        if kind=='LIFECYCLE_RESET_INTENT':
            same(e['before'],ledger);io.require(pending_reset is None,'nested reset');pending_reset=e
            ledger=ledger_add(ledger,e['phase'],'reset_attempts',1)
        elif kind=='LIFECYCLE_RESET_COMPLETE':
            same(e['intent_sequence'],pending_reset['sequence']);ledger=simulation(ledger,e['phase'],100,500);ledger=ledger_add(ledger,e['phase'],'reset_completed',1)
            same(e['after'],ledger,'whole reset frames');pending_reset=None
        elif kind=='FACTORY_COMPLETE':same(e['ledger'],ledger)
        elif kind=='CONTROLLED_INITIAL':same(e['observation'],c['initial']['observation']);same(e['ledger'],ledger)
        elif kind=='NOISE_COMMITMENT':same(e['at_calls'],0);same(e['tape_sha256_oracle'],io.digest(noise.tolist()))
        elif kind=='FAULT_BOUNDARY':
            same(e['logical_step'],n);same(n,spec['planned_boundary']);same(e['old_fault_oracle'],fault);same(e['new_fault_oracle'],a.destination(spec))
            same(e['before'],e['after'],'fault change cannot undo state');fault=e['new_fault_oracle'];boundary+=1;io.require(boundary==1,'single boundary')
        elif kind=='AGENT_EVENT':public.append(e)
        elif kind=='PUBLIC_SENT_TARGET_PLAN':
            same(e['at_calls'],n);io.require(plan is None,'one target plan before each actual command');command=byseq[e['actor_command_sequence']]
            io.require(command['event']=='AGENT_EVENT' and command['agent_event']=='COMMAND' and command['sequence']<e['sequence'],'saved actor command before public target plan')
            u=command['public_payload']['command'];numbers=target(sent,u)
            expected={'schema':'PUBLIC_NOMINAL_TARGET_PLAN_V1','before_sha256':io.digest(public_state(spec['task'],n,sent)),
                'command':np.asarray(u,np.float32).tolist(),'numbers':numbers,'after':public_state(spec['task'],n+1,numbers['target'])}
            same(e['plan'],expected,'independent public nominal arithmetic');plan=e
        elif kind=='STEP_INTENT':
            io.require(intent is None and plan is not None and plan['sequence']<e['sequence'],'durable public plan before physical intent')
            same(e['logical_step'],n);same(e['command'],plan['plan']['command']);same(e['global_command_sequence'],plan['actor_command_sequence'])
            same(e['ledger_before'],ledger);intent=e
        elif kind=='STEP_COMPLETE':
            io.require(intent is not None and plan is not None,'saved physical intent');same(e['intent_sequence'],intent['sequence'])
            same(e['logical_step'],n);same(e['noise_cursor_after'],n+1);same(e['command'],intent['command'])
            same(e['executed_action_oracle'],applied(e['command'],fault,noise[n]),'float32 transform then noise then final clip')
            b=before_native[n];p=after_native[n+1];same(b['mocap_pos_oracle'],[actual],'native target continuity')
            io.require(b['saved_ns']<e['execution_started_ns']<=e['completed_ns']<p['saved_ns'],'native before/after physical action order')
            same(b['simulation_time'],e['simulation_time_before']);same(p['simulation_time'],e['simulation_time_after'])
            predicted=target(actual,e['executed_action_oracle']);observed=p['mocap_pos_oracle'][0]
            target_errors.append(max(abs(x-y) for x,y in zip(predicted['target'],observed)));native_clips+=any(predicted['workspace_clip_axes'])
            sent=plan['plan']['numbers']['target'];sent_errors.append(distance(sent,observed))
            prior=c['initial']['observation'] if n==0 else steps[-1]['after']['observation']
            expected_export['steps'].append({'logical_step':n,'command':e['command'],'observation_before':prior,
                'observation_after':e['after']['observation'],'reference_after':public_state(spec['task'],n+1,sent)})
            ledger=simulation(ledger,'CONTROL',1,5);same(e['ledger_before'],intent['ledger_before']);same(e['ledger_after'],ledger)
            io.require(np.isclose(e['simulation_time_after'],initial['simulation_time']+.0125*(n+1),atol=1e-9,rtol=0),'independent physical clock')
            steps.append(e);actual=observed;n+=1;intent=None
        elif kind=='PUBLIC_SENT_TARGET_COMMIT':
            io.require(plan is not None and intent is None,'commit after physical action');same(e['at_calls'],n);same(e['plan_sequence'],plan['sequence']);same(e['reference'],public_state(spec['task'],n,sent));plan=None
    io.require(pending_reset is None and plan is None and intent is None,'unconsumed physical operation')
    same(n,c['total_steps']);same(c['host_attempts'],n);same(c['host_returned'],n);same(c['boundary_applied'],bool(boundary));same(finals[0]['at_calls'],n)
    same(finals[0]['mocap_pos_oracle'],[actual]);same(c['ledger_before_close'],ledger);same(c['ledger_after_close'],ledger)
    same(export,expected_export,'strict public projection without oracle or future-result fields');same(io.digest(export),c['public_trajectory_sha256'])
    replay_counts=replay(spec,c,public,steps,None);raw_counts=independent_raw(spec,c,public,steps)
    io.require(not replay_counts['independent_c4_c8_refits'] and not raw_counts['reference_updates'],'no response identification or reference adoption')
    entries=[e['public_payload'] for e in public if e['agent_event']=='PROBE_ENTRY'];io.require(len(entries)<=1,'single real measurement')
    entry=entries[0] if entries else None;at=None if entry is None else entry['at_calls']
    row={**spec,'total_steps':n,'success':c['success'],'deadline_loss':c['deadline_loss'],'complete_warm_window':c['complete_warm_window'],
        'warm_probe_steps':c['warm_probe_steps'],'stop_reason':c['stop_reason'],'entry_at_calls':at,
        'max_native_target_error_m':max(target_errors,default=None),'all_native_target_updates_bit_exact':all(v==0 for v in target_errors) if target_errors else None,
        'native_workspace_clip_steps':int(native_clips),'mean_sent_native_gap_mm':fsum(sent_errors)/n if n else None,
        'entry_sent_native_gap_mm':sent_errors[at-1] if at is not None else None,
        'entry_native_hand_coordinate_gap_mm':distance(after_native[at]['mocap_pos_oracle'][0],steps[at-1]['after']['observation'][:3]) if at is not None else None,
        'independent_policy_queries':replay_counts['independent_policy_queries']}
    return row,ledger,steps,before_native,after_native


def audit(path):
    start=perf_counter_ns();m=a.checked(path);out=Path(path).parent/'native';done=io.read(out/'completion.json')
    io.require(done['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','complete one-shot native collection')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'native raw record changed '+n)
    identity={k:m[k] for k in a.IDENTITY};journal=GroupedJournal(io.rows(out/'events.jsonl.gz'),a.KEYS,identity)
    priv=GroupedJournal(io.rows(out/'private_targets.jsonl.gz'),a.KEYS,identity);exports=iter(io.rows(out/'public_trajectories.jsonl.gz'))
    ledger={'counts':{},'by_phase':{}};rows=[];pairs={};pair_count=0
    cases=iter(io.rows(out/'cases.jsonl.gz'))
    for spec in a.population():
        c=next(cases,None);io.require(c is not None,'all 18 allocated cases');events=journal.take_case(c);private=priv.take_case(c)
        same(events[-1]['event'],'CASE_COMPLETE');same(events[-1]['case_record_sha256'],io.digest(c));same(events[0]['sequence'],c['event_start_sequence']);same(events[-1]['sequence'],c['event_end_sequence_exclusive'])
        row,ledger,steps,before,after=audit_case(spec,c,events,private,next(exports,None),ledger);rows.append(row)
        key=(spec['group'],spec['task'])
        if key in pairs:
            old=pairs.pop(key);n=min(spec['planned_boundary'],len(steps),len(old[0]))
            for j in range(n):
                for field in ('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(steps[j][field],old[0][j][field],'paired actual prefix')
                same(before[j]['mocap_pos_oracle'],old[1][j]['mocap_pos_oracle']);same(after[j+1]['mocap_pos_oracle'],old[2][j+1]['mocap_pos_oracle'])
            pair_count+=1
        else:pairs[key]=(steps,before,after)
    journal.finish();priv.finish();io.require(next(cases,None) is None and next(exports,None) is None and not pairs,'no extra/missing native case/export/pair')
    summary=io.read(out/'summary.json');same(summary['lifecycle'],ledger);same(summary['events'],journal.count);same(summary['private_target_records'],priv.count)
    same(summary['executions'],18);same(summary['control_steps'],sum(r['total_steps'] for r in rows));same(summary['network_guard'],{'attempted_network_calls':0});same(summary['fitting_guard'],{'attempted_fits':0})
    limits=a.config()['limits'];io.require(ledger['counts']['reset_attempts']==limits['all_resets'] and ledger['counts']['simulation_frames_completed']<=limits['physical_frames'] and summary['control_steps']<=9000,'full physical budget')
    coverage={task+'/'+context:sum(r['complete_warm_window'] for r in rows if r['task']==task and r['context']==context) for task in io.TASKS for context in ('UNCHANGED','CHANGED')}
    gate=all(r['all_native_target_updates_bit_exact'] for r in rows) and all(n>=1 for n in coverage.values())
    io.write(out/'trajectory_audit.json',rows)
    result={'integrity':'PASSED','native_contract':'PASSED' if gate else 'NOT_QUALIFIED','manifest_id':m['manifest_id'],'executions':18,
        'control_steps':summary['control_steps'],'all_resets':ledger['counts']['reset_attempts'],'physical_frames':ledger['counts']['simulation_frames_completed'],
        'paired_prefixes':pair_count,'private_target_records':priv.count,'complete_windows_by_task_context':coverage,
        'all_native_target_updates_bit_exact':all(r['all_native_target_updates_bit_exact'] for r in rows),'max_native_target_error_m':max((r['max_native_target_error_m'] for r in rows if r['max_native_target_error_m'] is not None),default=None),
        'task_failures_preserved':sum(not r['success'] for r in rows),'independent_extra_policy_queries':sum(r['independent_policy_queries'] for r in rows),
        'artifact_sha256':done['artifact_sha256'],'trajectory_audit_sha256':io.sha(out/'trajectory_audit.json'),'wall_ns':perf_counter_ns()-start,
        'shared_grouped_source_reader':True,'new_environment_steps':0,'new_model_fits':0,'online_LLM_API_calls':0,
        'new_predictor_task_or_safety_qualification':False,'publication_goal_complete':False}
    a.checked(path);io.write(out/'audit.json',result);return result
