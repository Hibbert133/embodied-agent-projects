"""Post-hoc input-accumulator arithmetic on complete, immutable saved streams.

None of the three references below predicts a new hand trajectory. In
particular, an applied-action replay is conditional on source-code priors,
not an independently measured hidden simulator state.
"""
from collections import Counter,defaultdict
import csv,gzip,json
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import command_target_sources_v1 as source
from src.analysis.short_probe_journal_audit_v1 import applied
from src.probe.nominal_command_target_v1 import INITIAL,target_update
io=source.io
PHASES=('FIXED_PROBE','PREFIX_TASK','POLICY','REPOSITION','WARM_PROBE','TAIL_TASK','TASK','APPROACH')
BINS=((1,8),(9,16),(17,32),(33,64),(65,500))
METRICS=('applied_hand_gap_mm','applied_initial_gap_change_mm','sent_hand_gap_mm',
    'sent_applied_difference_mm','noise_input_component_mm','transform_input_component_mm',
    'hand_displacement_mm','applied_workspace_clipped','sent_workspace_clipped','zero_noise_workspace_clipped')


def metadata(label,c):
    old=label=='OLD_NOMINAL_TRAIN'
    fields={'cohort':label,'task':c['task'],'group':c['unit']//9 if old else c['group'],
        'unit':str(c['unit']) if old else str(c['seed'])+'/'+c['context'],
        'seed':c['seed'],'context':'NOMINAL_TRAIN' if old else c['context'],
        'program':'NOMINAL_TRAIN' if old else c['program'],'planned_boundary':c['planned_boundary']}
    return fields|{'case_id':io.digest(fields)}


def norm_mm(v):return float(np.linalg.norm(v)*1000.)


def arithmetic(sent_before,applied_before,zero_before,command,actual,fault,before,after,initial_gap):
    """Three separately clipped input accumulators, with no re-fitted parameters."""
    s=target_update(sent_before,command);a=target_update(applied_before,actual)
    zero_command=applied(command,fault,np.zeros(3,dtype=np.float32));z=target_update(zero_before,zero_command)
    sq,aq,zq=(np.asarray(v['target']) for v in (s,a,z));hand=np.asarray(after[:3])
    noise=aq-zq;transform=zq-sq;gap=aq-hand
    result={'sent_target_after':s['target'],'applied_target_after':a['target'],'zero_noise_target_after':z['target'],
        'zero_noise_action_oracle':zero_command,'hand_after':hand.tolist(),'applied_minus_hand_xyz':gap.tolist(),
        'noise_input_component_xyz':noise.tolist(),'transform_input_component_xyz':transform.tolist(),
        'decomposition_roundoff_m':float(np.max(np.abs((aq-sq)-(noise+transform)))),
        'applied_hand_gap_mm':norm_mm(gap),'applied_initial_gap_change_mm':norm_mm(gap-initial_gap),
        'sent_hand_gap_mm':norm_mm(sq-hand),'sent_applied_difference_mm':norm_mm(aq-sq),
        'noise_input_component_mm':norm_mm(noise),'transform_input_component_mm':norm_mm(transform),
        'hand_displacement_mm':norm_mm(hand-np.asarray(before[:3]))}
    for prefix,value in (('sent',s),('applied',a),('zero_noise',z)):
        result[prefix+'_workspace_clip_axes']=value['workspace_clip_axes']
        result[prefix+'_workspace_clipped']=any(value['workspace_clip_axes'])
    return result


def stats(rows):
    return {name:float(np.mean([r[name] for r in rows])) if rows else None for name in METRICS}


def trace(label,case,events,initial):
    """Only consume events in saved order. Entry summaries precede probe data."""
    meta=metadata(label,case);before=list(initial);history=[before];q=list(INITIAL);qa=list(INITIAL);qz=list(INITIAL)
    initial_gap=np.asarray(INITIAL)-np.asarray(initial[:3]);fault=case['fault_oracle'] if label=='OLD_NOMINAL_TRAIN' else case['initial_fault_oracle']
    rows=[];entries=[];phase_counts=Counter();lifted=None;move_index=0
    for e in events:
        if e['event']=='FAULT_BOUNDARY':
            io.require(e['logical_step']==len(rows),'fault must be applied before the next recorded input');fault=e['new_fault_oracle']
        if e['event']=='AGENT_EVENT' and e['agent_event']=='PROBE_ENTRY':
            p=e['public_payload'];n=p['at_calls'];io.require(n==len(rows) and n>=3,'no future or fabricated entry history')
            io.require(p['entry_history']==history[-4:],'entry history must be the saved causal history')
            gap=np.asarray(qa)-np.asarray(before[:3]);entries.append(meta|{'source_event_sequence':e['sequence'],'at_calls':n,
                'sent_target':q,'applied_target':qa,'zero_noise_target':qz,'observed_hand':before[:3],
                'applied_hand_gap_mm':norm_mm(gap),'applied_initial_gap_change_mm':norm_mm(gap-initial_gap),
                'sent_applied_difference_mm':norm_mm(np.asarray(qa)-q),'last_hand_displacement_mm':norm_mm(np.asarray(history[-1][:3])-history[-2][:3]),
                'native_mocap_value_measured':False,'new_prediction_or_task_qualification':False})
        if e['event']!='STEP_COMPLETE':continue
        n=len(rows);io.require(e['logical_step']==n and e['noise_cursor_after']==n+1,'physical/noise clock alignment')
        phase=e['phase'];io.require(phase in PHASES,'unregistered source phase');phase_counts[phase]+=1
        if phase=='REPOSITION':
            move_index+=1
            if lifted is None:lifted=before[2]>=.235
            stage='POST_LIFT' if lifted else 'LIFT'
        else:stage='NOT_MOVEMENT'
        value=arithmetic(q,qa,qz,e['command'],e['executed_action_oracle'],fault,before,e['after']['observation'],initial_gap)
        row=meta|{'source_event_sequence':e['sequence'],'logical_step':n,'phase':phase,'phase_index':phase_counts[phase],
            'movement_index':move_index if phase=='REPOSITION' else None,'movement_stage':stage,
            'source_command':e['command'],'source_applied_action_oracle':e['executed_action_oracle'],
            'sent_target_before':q,'applied_target_before':qa,'zero_noise_target_before':qz,'hand_before':before[:3]}|value
        rows.append(row);q=value['sent_target_after'];qa=value['applied_target_after'];qz=value['zero_noise_target_after']
        before=list(e['after']['observation']);history.append(before)
        if phase=='REPOSITION':lifted=lifted or before[2]>=.235
    io.require(len(rows)==case['total_steps'] and len(entries)<=1,'one source trace/measurement entry')
    reason=case.get('stop_reason',case.get('collection_stop_reason'));warm=phase_counts['WARM_PROBE']
    # Nominal acquisition ends at its protocol horizon, so "success=False" is
    # not a failed task. Preserve the source outcome without re-labelling it.
    summary=meta|{'source_total_steps':len(rows),'source_success':case['success'],'source_stop_reason':reason,
        'source_task_tail_evaluated':label!='OLD_NOMINAL_TRAIN','measurement_entry_count':len(entries),'warm_probe_steps':warm,
        'complete_measurement':warm==8,'missing_measurement_reason':None if warm==8 else 'SHORT_EXECUTED_WINDOW' if warm else
            'NOT_SCHEDULED_PROGRAM' if label!='OLD_NOMINAL_TRAIN' and case['program'] in ('RAW_CONTINUE','DIRECT_C8','MOVE_INTEGRAL','LOCAL_PID_REFERENCE_RESET_NO_PROBE') else reason,
        'applied_workspace_clip_steps':sum(r['applied_workspace_clipped'] for r in rows),'source_phase_counts':dict(phase_counts),
        'final_sent_target':q,'final_applied_target':qa,'final_zero_noise_target':qz,
        'maximum_decomposition_roundoff_m':max((r['decomposition_roundoff_m'] for r in rows),default=None)}|stats(rows)
    stages=[]
    for phase in PHASES:
        for lo,hi in ((1,500),*BINS):
            part=[r for r in rows if r['phase']==phase and lo<=r['phase_index']<=hi]
            stages.append(meta|{'phase':phase,'stage':'ALL','bin_lo':lo,'bin_hi':hi,'steps':len(part),
                'missing_reason':None if part else 'PHASE_NOT_EXECUTED' if not phase_counts[phase] else 'SOURCE_SHORTER_THAN_BIN'}|stats(part))
    for stage in ('LIFT','POST_LIFT'):
        for lo,hi in BINS[:-1]:
            part=[r for r in rows if r['movement_stage']==stage and lo<=(r['movement_index'] or 0)<=hi]
            stages.append(meta|{'phase':'REPOSITION','stage':stage,'bin_lo':lo,'bin_hi':hi,'steps':len(part),
                'missing_reason':None if part else 'MOVEMENT_STAGE_OR_BIN_NOT_EXECUTED'}|stats(part))
    return rows,summary,stages,entries


def grouped(stage_rows):
    """Equal trajectory weights within group, then equal available group weights.

    Separate program/context/phase cells cannot double-count common MOVE data.
    Missing metrics stay null with explicit full and available denominators.
    """
    keys=('cohort','task','context','program','phase','stage','bin_lo','bin_hi');cells=defaultdict(list)
    for r in stage_rows:cells[tuple(r[k] for k in keys)].append(r)
    result=[]
    for key,rows in cells.items():
        groups=defaultdict(list)
        for r in rows:groups[r['group']].append(r)
        metrics={}
        for metric in METRICS:
            values=[float(np.mean([r[metric] for r in members if r[metric] is not None])) for members in groups.values() if any(r[metric] is not None for r in members)]
            metrics[metric]=float(np.mean(values)) if values else None
        result.append(dict(zip(keys,key))|{'allocated_trajectories':len(rows),'available_trajectories':sum(r['steps']>0 for r in rows),
            'allocated_groups':len(groups),'available_groups':len({r['group'] for r in rows if r['steps']>0}),
            'saved_steps':sum(r['steps'] for r in rows),'missing_reasons':dict(Counter(r['missing_reason'] for r in rows if r['missing_reason']))}|metrics)
    return result


def csv_write(path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False,separators=(',',':')) if type(v) in (dict,list) else v for k,v in r.items()} for r in rows)


def run(path):
    start=perf_counter_ns();m=source.checked(path);out=Path(path).parent
    trajectories=[];stages=[];entries=[];totals={};step_count=0
    with gzip.open(out/'step_diagnostics.jsonl.gz','xt',encoding='utf-8',newline='\n') as f:
        for label,folder,_,n,steps in source.cohorts():
            count=physical=0
            for c,events,initial in source.cases(label,folder):
                rows,summary,phase_rows,entry=trace(label,c,events,initial)
                for r in rows:f.write(json.dumps(r,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
                trajectories.append(summary);stages.extend(phase_rows);entries.extend(entry);count+=1;physical+=len(rows)
            io.require((count,physical)==(n,steps),'full cohort diagnostic');totals[label]={'executions':count,'saved_steps':physical};step_count+=physical
            print({'analyzed':label,'cases':count,'saved_steps':physical},flush=True)
    io.require(len(trajectories)==1752 and step_count==152128,'full registered population')
    io.write(out/'trajectory_summaries.json',trajectories);io.write(out/'measurement_entries.json',entries)
    with gzip.open(out/'phase_summaries.jsonl.gz','xt',encoding='utf-8',newline='\n') as f:
        for r in stages:f.write(json.dumps(r,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
    groups=grouped(stages);io.write(out/'grouped_tables.json',groups)
    for name,values in (('trajectories.csv',trajectories),('measurement_entries.csv',entries),('grouped_tables.csv',groups)):csv_write(out/name,values)
    io.write(out/'results.json',{'classification':'POST_HOC_DESCRIPTIVE_ONLY','cohorts':totals,'executions':len(trajectories),'saved_steps':step_count,
        'source_derived_targets_are_measured_native_values':False,'canonical_acquisition_program':'LOCAL_PID_KEEP',
        'entry_counts':dict(Counter(r['cohort'] for r in entries)),
        'unavailable_reasons':dict(Counter(r['missing_measurement_reason'] for r in trajectories if r['missing_measurement_reason'])),
        'new_environment_creations':0,'new_resets':0,'new_environment_steps':0,'new_physical_frames':0,'new_fits':0,'new_online_LLM_API_calls':0,
        'new_prediction_or_task_qualification':False,'publication_goal_complete':False})
    artifact={p.name:io.sha(p) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'}
    result={'integrity':'ANALYZED_PENDING_INDEPENDENT_AUDIT','manifest_id':m['manifest_id'],'artifact_sha256':artifact,
        'executions':len(trajectories),'saved_steps':step_count,'phase_rows':len(stages),'measurement_entries':len(entries),'wall_ns':perf_counter_ns()-start,
        'new_environment_steps':0,'new_fits':0,'new_online_LLM_API_calls':0}
    io.write(out/'completion.json',result);return result
