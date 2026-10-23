"""Independent arithmetic/reduction; source journal adapter is shared and disclosed."""
from collections import Counter,defaultdict
from math import fsum,sqrt,isclose
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import command_target_sources_v1 as source
io=source.io
METRICS=('applied_hand_gap_mm','applied_initial_gap_change_mm','sent_hand_gap_mm',
    'sent_applied_difference_mm','noise_input_component_mm','transform_input_component_mm',
    'hand_displacement_mm','applied_workspace_clipped','sent_workspace_clipped','zero_noise_workspace_clipped')
PHASES=('FIXED_PROBE','PREFIX_TASK','POLICY','REPOSITION','WARM_PROBE','TAIL_TASK','TASK','APPROACH')
BINS=((1,8),(9,16),(17,32),(33,64),(65,500))


def same(actual,expected,path='value'):
    if type(expected) is dict:
        io.require(type(actual) is dict and set(actual)==set(expected),'audit keys '+path)
        return sum(same(actual[k],v,path+'/'+k) for k,v in expected.items())
    if type(expected) in (list,tuple):
        io.require(type(actual) in (list,tuple) and len(actual)==len(expected),'audit length '+path)
        return sum(same(a,b,path+f'/{i}') for i,(a,b) in enumerate(zip(actual,expected)))
    if type(expected) is float:
        io.require(type(actual) in (float,int) and isclose(actual,expected,rel_tol=1e-10,abs_tol=1e-9),'audit float '+path)
    else:io.require(type(actual) is type(expected) and actual==expected,'audit value '+path)
    return 1


def update(target,command):
    low=(-.5,.4,.05);high=(.5,1.,.5);result=[];clips=[]
    for t,u,lo,hi in zip(target,command,low,high):
        delta=float(np.float32(np.float32(u)*np.float32(.01)))
        requested=t+delta;value=min(hi,max(lo,requested));result.append(value);clips.append(value!=requested)
    return result,clips


def noiseless(command,fault):
    u=np.array(command,dtype=np.float32);matrix=np.array(fault['matrix_xy'],dtype=np.float32)
    latent=np.dot(matrix,u[:2])+np.array(fault['bias_xy'],dtype=np.float32)
    zone=np.array(fault['deadzone_xy'],dtype=np.float32)
    for j in (0,1):u[j]=np.sign(latent[j])*max(np.float32(0),np.float32(abs(latent[j])-zone[j]))/np.float32(1-zone[j])
    return [float(min(np.float32(1),max(np.float32(-1),x))) for x in u]


def minus(a,b):return [x-y for x,y in zip(a,b)]
def length(v):return sqrt(fsum(x*x for x in v))*1000.
def averages(rows):return {k:fsum(float(r[k]) for r in rows)/len(rows) if rows else None for k in METRICS}


def identity(label,c):
    old=label=='OLD_NOMINAL_TRAIN';v={'cohort':label,'task':c['task'],'group':c['unit']//9 if old else c['group'],
        'unit':str(c['unit']) if old else str(c['seed'])+'/'+c['context'],'seed':c['seed'],
        'context':'NOMINAL_TRAIN' if old else c['context'],'program':'NOMINAL_TRAIN' if old else c['program'],'planned_boundary':c['planned_boundary']}
    v['case_id']=io.digest(v);return v


def audit_trace(label,c,events,initial,recorded_steps):
    base=identity(label,c);s=[0.,.6,.2];a=s.copy();z=s.copy();h=initial[:3];hist=[initial];gap0=minus(a,h)
    fault=c['fault_oracle'] if label=='OLD_NOMINAL_TRAIN' else c['initial_fault_oracle'];phase_counts=Counter();rows=[];entries=[];fields=0;lifted=None;mi=0
    for e in events:
        if e['event']=='FAULT_BOUNDARY':
            io.require(e['logical_step']==len(rows),'independent fault clock');fault=e['new_fault_oracle']
        if e['event']=='AGENT_EVENT' and e['agent_event']=='PROBE_ENTRY':
            p=e['public_payload'];io.require(p['at_calls']==len(rows) and p['entry_history']==hist[-4:],'independent causal entry history')
            gap=minus(a,h)
            entries.append(base|{'source_event_sequence':e['sequence'],'at_calls':len(rows),'sent_target':s.copy(),'applied_target':a.copy(),'zero_noise_target':z.copy(),
                'observed_hand':h.copy(),'applied_hand_gap_mm':length(gap),'applied_initial_gap_change_mm':length(minus(gap,gap0)),
                'sent_applied_difference_mm':length(minus(a,s)),'last_hand_displacement_mm':length(minus(hist[-1][:3],hist[-2][:3])),
                'native_mocap_value_measured':False,'new_prediction_or_task_qualification':False})
        if e['event']!='STEP_COMPLETE':continue
        io.require(e['logical_step']==len(rows) and e['noise_cursor_after']==len(rows)+1,'independent input clock')
        phase=e['phase'];phase_counts[phase]+=1
        if phase=='REPOSITION':
            mi+=1
            if lifted is None:lifted=h[2]>=.235
            stage='POST_LIFT' if lifted else 'LIFT'
        else:stage='NOT_MOVEMENT'
        sn,sc=update(s,e['command']);an,ac=update(a,e['executed_action_oracle']);u0=noiseless(e['command'],fault);zn,zc=update(z,u0)
        hn=e['after']['observation'][:3];g=minus(an,hn);noise=minus(an,zn);trans=minus(zn,sn)
        row=base|{'source_event_sequence':e['sequence'],'logical_step':len(rows),'phase':phase,'phase_index':phase_counts[phase],
            'movement_index':mi if phase=='REPOSITION' else None,'movement_stage':stage,
            'source_command':e['command'],'source_applied_action_oracle':e['executed_action_oracle'],
            'sent_target_before':s.copy(),'applied_target_before':a.copy(),'zero_noise_target_before':z.copy(),'hand_before':h.copy(),
            'sent_target_after':sn,'applied_target_after':an,'zero_noise_target_after':zn,'zero_noise_action_oracle':u0,
            'hand_after':hn,'applied_minus_hand_xyz':g,'noise_input_component_xyz':noise,'transform_input_component_xyz':trans,
            'decomposition_roundoff_m':max(abs(x-y-w) for x,y,w in zip(minus(an,sn),noise,trans)),
            'applied_hand_gap_mm':length(g),'applied_initial_gap_change_mm':length(minus(g,gap0)),'sent_hand_gap_mm':length(minus(sn,hn)),
            'sent_applied_difference_mm':length(minus(an,sn)),'noise_input_component_mm':length(noise),'transform_input_component_mm':length(trans),
            'hand_displacement_mm':length(minus(hn,h)),'sent_workspace_clip_axes':sc,'applied_workspace_clip_axes':ac,'zero_noise_workspace_clip_axes':zc,
            'sent_workspace_clipped':any(sc),'applied_workspace_clipped':any(ac),'zero_noise_workspace_clipped':any(zc)}
        saved=next(recorded_steps,None);io.require(saved is not None,'missing diagnostic saved step');fields+=same(saved,row,base['case_id']+'/'+str(len(rows)))
        rows.append(row);s=sn;a=an;z=zn;h=hn;hist.append(e['after']['observation'])
        if phase=='REPOSITION':lifted=lifted or h[2]>=.235
    reason=c.get('stop_reason',c.get('collection_stop_reason'));warm=phase_counts['WARM_PROBE']
    missing=None if warm==8 else 'SHORT_EXECUTED_WINDOW' if warm else 'NOT_SCHEDULED_PROGRAM' if label!='OLD_NOMINAL_TRAIN' and c['program'] in ('RAW_CONTINUE','DIRECT_C8','MOVE_INTEGRAL','LOCAL_PID_REFERENCE_RESET_NO_PROBE') else reason
    summary=base|{'source_total_steps':len(rows),'source_success':c['success'],'source_stop_reason':reason,
        'source_task_tail_evaluated':label!='OLD_NOMINAL_TRAIN','measurement_entry_count':len(entries),'warm_probe_steps':warm,'complete_measurement':warm==8,
        'missing_measurement_reason':missing,'applied_workspace_clip_steps':sum(r['applied_workspace_clipped'] for r in rows),
        'source_phase_counts':dict(phase_counts),'final_sent_target':s,'final_applied_target':a,'final_zero_noise_target':z,
        'maximum_decomposition_roundoff_m':max((r['decomposition_roundoff_m'] for r in rows),default=None)}|averages(rows)
    stages=[]
    for phase in PHASES:
        for lo,hi in ((1,500),*BINS):
            part=[r for r in rows if r['phase']==phase and lo<=r['phase_index']<=hi]
            stages.append(base|{'phase':phase,'stage':'ALL','bin_lo':lo,'bin_hi':hi,'steps':len(part),
                'missing_reason':None if part else 'PHASE_NOT_EXECUTED' if not phase_counts[phase] else 'SOURCE_SHORTER_THAN_BIN'}|averages(part))
    for stage in ('LIFT','POST_LIFT'):
        for lo,hi in BINS[:-1]:
            part=[r for r in rows if r['movement_stage']==stage and lo<=(r['movement_index'] or 0)<=hi]
            stages.append(base|{'phase':'REPOSITION','stage':stage,'bin_lo':lo,'bin_hi':hi,'steps':len(part),
                'missing_reason':None if part else 'MOVEMENT_STAGE_OR_BIN_NOT_EXECUTED'}|averages(part))
    io.require(len(rows)==c['total_steps'],'independent whole trace count');return summary,stages,entries,fields


def group_tables(rows):
    keys=('cohort','task','context','program','phase','stage','bin_lo','bin_hi');cells={}
    for r in rows:cells.setdefault(tuple(r[k] for k in keys),[]).append(r)
    result=[]
    for key,members in cells.items():
        groups={g:[r for r in members if r['group']==g] for g in {r['group'] for r in members}}
        values={}
        for k in METRICS:
            means=[]
            for g in sorted(groups):
                observed=[float(r[k]) for r in groups[g] if r[k] is not None]
                if observed:means.append(fsum(observed)/len(observed))
            values[k]=fsum(means)/len(means) if means else None
        result.append(dict(zip(keys,key))|{'allocated_trajectories':len(members),'available_trajectories':sum(r['steps']>0 for r in members),
            'allocated_groups':len(groups),'available_groups':len({r['group'] for r in members if r['steps']>0}),
            'saved_steps':sum(r['steps'] for r in members),'missing_reasons':dict(Counter(r['missing_reason'] for r in members if r['missing_reason']))}|values)
    return result


def audit(path):
    start=perf_counter_ns();m=source.checked(path);out=Path(path).parent;done=io.read(out/'completion.json')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'analysis artifact digest '+n)
    saved_steps=iter(io.rows(out/'step_diagnostics.jsonl.gz'));saved_stages=iter(io.rows(out/'phase_summaries.jsonl.gz'))
    summaries=iter(io.read(out/'trajectory_summaries.json'));entries=iter(io.read(out/'measurement_entries.json'));allstages=[];count=steps=fields=entry_count=0
    for label,folder,_,n,expected_steps in source.cohorts():
        nc=ns=0
        for c,events,initial in source.cases(label,folder):
            summary,stages,es,checked=audit_trace(label,c,events,initial,saved_steps);fields+=checked
            fields+=same(next(summaries,None),summary)
            for r in stages:fields+=same(next(saved_stages,None),r)
            for r in es:fields+=same(next(entries,None),r)
            allstages.extend(stages);entry_count+=len(es);nc+=1;ns+=c['total_steps']
        io.require((nc,ns)==(n,expected_steps),'independent full cohort denominator');count+=nc;steps+=ns
        print({'audited':label,'cases':nc,'saved_steps':ns},flush=True)
    io.require(all(next(it,None) is None for it in (saved_steps,saved_stages,summaries,entries)),'extra derived rows')
    fields+=same(io.read(out/'grouped_tables.json'),group_tables(allstages))
    io.require((count,steps)==(1752,152128) and done['phase_rows']==len(allstages) and done['measurement_entries']==entry_count,'independent full outputs')
    source.checked(path)
    result={'integrity':'PASSED','manifest_id':m['manifest_id'],'executions':count,'saved_steps':steps,'phase_rows':len(allstages),
        'measurement_entries':entry_count,'independently_checked_fields':fields,'independent_arithmetic_and_reductions':True,
        'shared_read_only_source_journal_adapter':True,'source_derived_applied_target_measured_in_native_data':False,
        'artifact_sha256':done['artifact_sha256'],'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'new_fits':0,'new_online_LLM_API_calls':0,
        'prediction_task_or_publication_qualification':False}
    io.write(out/'independent_audit.json',result);return result
