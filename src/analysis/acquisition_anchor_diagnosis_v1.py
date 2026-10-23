"""Post-hoc readiness, command chain and cost accounting; no model fitting."""
from collections import Counter
from copy import deepcopy
from time import perf_counter_ns
import csv,gzip,json,math
import numpy as np
from src.analysis import acquisition_anchor_diagnosis_io_v1 as source
from src.analysis.capsule_record_json_v2 import normalize
io=source.io
ANCHOR=(0.,.6,.25)


def gates(history):
    io.require(bool(history) and all(len(o)==39 for o in history),'actual visible relocation history')
    o=history[-1];pos=max(abs(a-b) for a,b in zip(o[:3],ANCHOR));clear=math.dist(o[:3],o[4:7]);enough=len(history)>=4
    motion=None if not enough else max(abs(a-b) for u,v in zip(history[-4:-1],history[-3:]) for a,b in zip(u[:3],v[:3]))
    checks={'history':enough,'position':pos<=.015,'clearance':clear>=.10,'motion':None if motion is None else motion<=.003}
    return {'position_error_inf_m':pos,'clearance_m':clear,'recent_motion_inf_m':motion,'checks':checks,
        'failed_conditions':[k for k,v in checks.items() if v is not True], 'ready':all(v is True for v in checks.values()),
        'motion_missing_reason':None if enough else 'FEWER_THAN_FOUR_REAL_RELOCATION_OBSERVATIONS'}


def chain(command,fault,noise):
    u=np.asarray(command,np.float32);m=np.asarray(fault['matrix_xy'],np.float32);b=np.asarray(fault['bias_xy'],np.float32);z=np.asarray(fault['deadzone_xy'],np.float32)
    io.require(u.shape==(4,) and np.isfinite(u).all() and np.all(abs(u)<=1),'bounded saved command')
    io.require(m.shape==(2,2) and b.shape==z.shape==(2,) and np.asarray(noise).shape==(3,) and all(np.isfinite(v).all() for v in (m,b,z,np.asarray(noise))) and np.all((z>=0)&(z<1)),'finite exact actuator and noise shapes')
    latent=m@u[:2]+b;transformed=u.copy();transformed[:2]=np.sign(latent)*np.maximum(abs(latent)-z,0)/(1-z)
    noisy=transformed.copy();noisy[:3]+=np.asarray(noise,np.float32);applied=np.clip(noisy,-1,1)
    return {'latent_xy_oracle':latent.astype(float).tolist(),'transformed_action_oracle':transformed.astype(float).tolist(),
        'actual_noise_xyz_oracle':np.asarray(noise,np.float32).astype(float).tolist(),'before_final_clip_oracle':noisy.astype(float).tolist(),
        'applied_action_oracle':applied.astype(float).tolist(),'final_clip_xyz_oracle':[bool(v) for v in (abs(noisy[:3])>1)]}


def balance_reference(fault):
    """Algebraic zero-command reference, not a fitted plant or equilibrium claim."""
    m=np.asarray(fault['matrix_xy'],np.float32).astype(float);b=np.asarray(fault['bias_xy'],np.float32).astype(float)
    det=m[0,0]*m[1,1]-m[0,1]*m[1,0]
    if any(v!=0 for v in fault['deadzone_xy']):return {'error_xy_m':None,'missing_reason':'NONZERO_DEADZONE_NONUNIQUE_REFERENCE'}
    if det==0:return {'error_xy_m':None,'missing_reason':'SINGULAR_AFFINE_MATRIX'}
    e=[(-m[1,1]*b[0]+m[0,1]*b[1])/det/8.,(m[1,0]*b[0]-m[0,0]*b[1])/det/8.]
    if any(abs(8*v)>.5 for v in e):return {'error_xy_m':None,'missing_reason':'REFERENCE_OUTSIDE_UNCLIPPED_PD_DOMAIN'}
    return {'error_xy_m':[float(v) for v in e],'missing_reason':None,'not_a_physical_equilibrium_or_noise_free_response':True}


def case_analysis(case,events,tape):
    rows=[e for e in events if e['event']=='STEP_COMPLETE'];public=[e for e in events if e['event']=='AGENT_EVENT']
    commands={e['sequence']:e['public_payload'] for e in public if e['agent_event']=='COMMAND'}
    plans={e['public_payload']['sequence']:e['public_payload']['saved_plan']['pi_plan']['numbers'] for e in public if e['agent_event']=='PI_PLAN'}
    suspend=next((e['public_payload'] for e in public if e['agent_event']=='TASK_MEMORY_SUSPEND'),None)
    returned=next((e['public_payload'] for e in public if e['agent_event']=='TASK_MEMORY_RETURN'),None)
    before=case['initial']['observation'];history=None;lifted=False;records=[];relocation=[];warm=0
    for n,e in enumerate(rows):
        io.require(e['logical_step']==n and e['noise_cursor_after']==n+1,'source noise cursor')
        fault=case['destination_oracle'] if case['boundary_applied'] and n>=case['planned_boundary'] else case['initial_fault_oracle']
        applied=chain(e['command'],fault,tape[n]);io.require(applied['applied_action_oracle']==e['executed_action_oracle'],'float32 source execution differs')
        c=commands[e['global_command_sequence']];numbers=plans.get(c['decision_sequence']) if e['raw_policy'] is not None else None
        rec={k:case[k] for k in ('group','task','seed','context','planned_boundary','action')}
        rec.update(logical_step=n,phase=e['phase'],before_xyz=before[:3],after_xyz=e['after']['observation'][:3],
            actual_hand_delta_xyz=[a-b for a,b in zip(e['after']['observation'][:3],before[:3])],
            object_delta_xyz=[a-b for a,b in zip(e['after']['observation'][4:7],before[4:7])],gripper_observation=before[3],
            command=e['command'],policy_action_clip=None if numbers is None else any(abs(v)>1 for v in e['raw_policy']),
            task_correction_send_limit=None if numbers is None else numbers['send_limit_active'],
            relocation=None,**applied)
        if e['phase']=='REPOSITION':
            if history is None:history=[list(before)];lifted=before[2]>=.235
            index=len(relocation)+1;target=list(ANCHOR if lifted else (*history[0][:2],.25))
            xyz=np.asarray(before[:3]);velocity=np.asarray(before[:3])-np.asarray(history[-2][:3]) if len(history)>=2 else np.zeros(3)
            unbounded=8.*(np.asarray(target)-xyz)-16.*velocity
            expected=np.r_[np.clip(unbounded,-.5,.5),-1.].astype(np.float32).astype(float).tolist()
            io.require(expected==e['command'],'fixed identity PD differs from saved command')
            prior=gates(history);history.append(e['after']['observation']);post=gates(history)
            rec['relocation']={'index':index,'stage':'LATERAL' if lifted else 'LIFT','active_target_xyz':target,
                'active_error_xyz_m':(np.asarray(target)-xyz).tolist(),'raw_PD_xyz':unbounded.tolist(),
                'PD_limit_active_xyz':[bool(v) for v in (abs(unbounded)>.5)],
                'controller_velocity_xyz_m':None if len(history)==2 else velocity.tolist(),
                'controller_velocity_missing_reason':'REGISTERED_ZERO_DERIVATIVE_ON_FIRST_STEP_NOT_A_MEASURED_DISPLACEMENT' if len(history)==2 else None,
                'before_gates':prior,'after_gates':post,'balance_reference_oracle':balance_reference(fault)}
            relocation.append(rec);lifted=lifted or e['after']['observation'][2]>=.235
        if e['phase']=='WARM_PROBE':warm+=1
        records.append(rec);before=e['after']['observation']
    io.require(len(records)==case['total_steps'] and len(relocation)==case['movement_steps'] and warm==case['warm_probe_steps'],'complete phase counts')
    summary={k:case[k] for k in ('group','task','seed','context','planned_boundary','action','success','deadline_loss','total_steps','option_reason','boundary_reached','movement_steps','warm_probe_steps','complete_warm_window')}
    late=relocation[-8:];last=relocation[-1]['relocation'] if relocation else None
    summary.update(final_relocation_gates=None if last is None else last['after_gates'],
        phase_missing_reason=None if relocation else 'NOT_A_MOVE_PROGRAM' if case['action']!='MOVE_MEASURE8' else 'EARLY_SUCCESS_NO_ACQUISITION',
        lift_steps=sum(r['relocation']['stage']=='LIFT' for r in relocation),lateral_steps=sum(r['relocation']['stage']=='LATERAL' for r in relocation),
        late_relocation_actual_n=len(late),late_active_error_xy_mean_m=None if not late else np.mean([r['relocation']['active_error_xyz_m'][:2] for r in late],axis=0).tolist(),
        late_noise_xyz_mean_oracle=None if not late else np.mean([r['actual_noise_xyz_oracle'] for r in late],axis=0).tolist(),
        task_integral_at_suspend=None if suspend is None else suspend['memory']['integral_xy'],
        returned_task_integral=None if returned is None else returned['memory']['integral_xy'],
        first_move_command_jump_xy=None,first_return_task_command_jump_xy=None,
        task_correction_send_limit_steps=sum(r['task_correction_send_limit'] is True for r in records),
        actuator_final_clip_steps=sum(any(r['final_clip_xyz_oracle']) for r in records))
    if relocation:
        first=relocation[0]['logical_step'];summary['first_move_command_jump_xy']=[rows[first]['command'][j]-rows[first-1]['command'][j] for j in (0,1)] if first else None
        fault=case['destination_oracle'] if case['boundary_applied'] else case['initial_fault_oracle'];summary['balance_reference_oracle']=balance_reference(fault)
    else:summary['balance_reference_oracle']=None
    if returned is not None:
        index=returned['at_calls']
        if index<len(rows) and index>0:summary['first_return_task_command_jump_xy']=[rows[index]['command'][j]-rows[index-1]['command'][j] for j in (0,1)]
    stages=[]
    for stage in ('LIFT','LATERAL'):
        for lo,hi in ((1,8),(9,16),(17,32),(33,64)):
            part=[r for r in relocation if r['relocation']['stage']==stage and lo<=r['relocation']['index']<=hi]
            stages.append({**{k:case[k] for k in ('group','task','seed','context','planned_boundary','action')},'stage':stage,'bin_lo':lo,'bin_hi':hi,'actual_n':len(part),
                'position_error_mean_m':None if not part else float(np.mean([r['relocation']['after_gates']['position_error_inf_m'] for r in part])),
                'motion_mean_m':None if not any(r['relocation']['after_gates']['recent_motion_inf_m'] is not None for r in part) else float(np.mean([r['relocation']['after_gates']['recent_motion_inf_m'] for r in part if r['relocation']['after_gates']['recent_motion_inf_m'] is not None])),
                'PD_limit_step_fraction':None if not part else sum(any(r['relocation']['PD_limit_active_xyz']) for r in part)/len(part),
                'missing_reason':None if part else 'NO_ACTUAL_RELOCATION_IN_THIS_STAGE_AND_BIN'})
    return records,summary,stages


def paired_cost(rows):
    result=[]
    for move in (r for r in rows if r['action']=='MOVE_MEASURE8'):
        direct=next(r for r in rows if r['action']=='CONTINUE' and all(r[k]==move[k] for k in ('group','task','context')))
        acquired=move['movement_steps']+move['warm_probe_steps'];diff=move['deadline_loss']-direct['deadline_loss']
        result.append({k:move[k] for k in ('group','task','seed','context','planned_boundary')}|{
            'L_move_minus_continue':diff,'actual_movement_and_probe_steps':acquired,'remaining_loss_difference_after_paid_acquisition':diff-acquired,
            'success_to_failure':direct['success'] and not move['success'],'failure_to_success':not direct['success'] and move['success'],
            'both_ended_before_decision':not move['boundary_reached'],'descriptive_algebra_not_causal_phase_attribution':True})
    return result


def jsonl(path,rows):
    with gzip.open(path,'xt',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(normalize(row),sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')


def run(path):
    start=perf_counter_ns();path=path.resolve();m=source.checked(path);out=path.parent;native=source.SOURCE/'native'
    from src.analysis.memory_acquisition_io_v1 import noise
    cases=list(io.rows(native/'cases.jsonl.gz'));events=list(io.rows(native/'events.jsonl.gz'));steps=[];summaries=[];stages=[]
    for c in cases:
        r,s,t=case_analysis(c,events[c['event_start_sequence']:c['event_end_sequence_exclusive']],noise(c['seed']));steps.extend(r);summaries.append(s);stages.extend(t)
    io.require(len(cases)==54 and len(steps)==8836 and len(stages)==54*8,'full source population')
    pair=paired_cost(summaries);moves=[s for s in summaries if s['action']=='MOVE_MEASURE8'];final_masks=Counter('+'.join(s['final_relocation_gates']['failed_conditions']) or 'READY' for s in moves if s['final_relocation_gates'] is not None)
    bygroup=[]
    for g in (0,1,2):
        part=[r for r in pair if r['group']==g]
        bygroup.append({'group':g,'paired_units':len(part),'mean_L_move_minus_continue':float(np.mean([r['L_move_minus_continue'] for r in part])),
            'mean_actual_acquisition_steps':float(np.mean([r['actual_movement_and_probe_steps'] for r in part]))})
    result={'classification':'POST_HOC_DESCRIPTIVE_ONLY','source_executions':54,'source_steps':8836,'source_task_failures':sum(not s['success'] for s in summaries),
        'assigned_moves':18,'actual_move_cases':sum(s['movement_steps']>0 for s in moves),'full_windows':sum(s['complete_warm_window'] for s in moves),
        'final_gate_mask_counts_among_actual_moves':dict(final_masks),'paired_costs':pair,'whole_groups':bygroup,
        'new_environment_steps':0,'new_resets':0,'new_physical_frames':0,'new_model_fits':0,'new_online_LLM_API_calls':0,
        'unexecuted_trajectories_generated':0,'no_control_or_threshold_changes':True,'publication_goal_complete':False}
    jsonl(out/'step_diagnostics.jsonl.gz',steps);io.write(out/'trajectory_diagnostics.json',summaries);io.write(out/'stage_diagnostics.json',stages);io.write(out/'results.json',result)
    with (out/'move_cases.csv').open('x',encoding='utf-8-sig',newline='') as f:
        table=[]
        for s in moves:
            gate=s['final_relocation_gates'];table.append({k:s[k] for k in ('group','task','seed','context','planned_boundary','success','deadline_loss','option_reason','movement_steps','warm_probe_steps','complete_warm_window','lift_steps','lateral_steps')}|{
                'final_position_error_m':None if gate is None else gate['position_error_inf_m'],'final_clearance_m':None if gate is None else gate['clearance_m'],
                'final_motion_m':None if gate is None else gate['recent_motion_inf_m'],'failed_conditions':None if gate is None else '+'.join(gate['failed_conditions']),'phase_missing_reason':s['phase_missing_reason']})
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    source.checked(path);names=('step_diagnostics.jsonl.gz','trajectory_diagnostics.json','stage_diagnostics.json','results.json','move_cases.csv')
    io.write(out/'completion.json',{'integrity':'EXPORTED_FOR_INDEPENDENT_AUDIT','manifest_id':m['manifest_id'],'artifact_sha256':{n:io.sha(out/n) for n in names},'wall_ns':perf_counter_ns()-start,
        'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0});return result
