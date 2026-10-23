"""Independent gates, Fraction balance algebra and complete export accounting."""
from pathlib import Path
from collections import Counter
from fractions import Fraction as F
from math import dist,fsum,isclose
from time import perf_counter_ns
import csv
import numpy as np
from src.analysis import acquisition_anchor_diagnosis_io_v1 as source
io=source.io


def same(got,want,label='diagnostic'):
    if isinstance(want,dict):
        io.require(type(got) is dict and set(got)==set(want),'field set '+label);return sum(same(got[k],v,label+'/'+k) for k,v in want.items())
    if isinstance(want,(tuple,list)):
        io.require(isinstance(got,(list,tuple)) and len(got)==len(want),'length '+label);return sum(same(a,b,label) for a,b in zip(got,want))
    if type(want) in (float,int):io.require(type(got) in (float,int) and isclose(got,want,rel_tol=1e-11,abs_tol=1e-12),'number '+label)
    else:io.require(got==want,'value '+label)
    return 1


def conditions(h):
    p=h[-1];distance=max(abs(p[i]-x) for i,x in enumerate((0.,.6,.25)));clearance=dist(p[:3],p[4:7]);full=len(h)>=4
    movement=max(abs(h[j+1][k]-h[j][k]) for j in range(len(h)-4,len(h)-1) for k in range(3)) if full else None
    yes={'history':full,'position':distance<=.015,'clearance':clearance>=.1,'motion':None if not full else movement<=.003}
    return {'position_error_inf_m':distance,'clearance_m':clearance,'recent_motion_inf_m':movement,'checks':yes,
        'failed_conditions':[k for k,v in yes.items() if v is not True],'ready':all(v is True for v in yes.values()),
        'motion_missing_reason':None if full else 'FEWER_THAN_FOUR_REAL_RELOCATION_OBSERVATIONS'}


def rational_reference(fault):
    m=[[F(float(np.float32(v))) for v in row] for row in fault['matrix_xy']];b=[F(float(np.float32(v))) for v in fault['bias_xy']]
    d=m[0][0]*m[1][1]-m[0][1]*m[1][0]
    if any(v for v in fault['deadzone_xy']):return {'error_xy_m':None,'missing_reason':'NONZERO_DEADZONE_NONUNIQUE_REFERENCE'}
    if not d:return {'error_xy_m':None,'missing_reason':'SINGULAR_AFFINE_MATRIX'}
    u=((m[0][1]*b[1]-m[1][1]*b[0])/d/8,(m[1][0]*b[0]-m[0][0]*b[1])/d/8)
    if any(abs(8*v)>F(1,2) for v in u):return {'error_xy_m':None,'missing_reason':'REFERENCE_OUTSIDE_UNCLIPPED_PD_DOMAIN'}
    return {'error_xy_m':[float(v) for v in u],'missing_reason':None,'not_a_physical_equilibrium_or_noise_free_response':True}


def independent_chain(command,fault,noise):
    command=np.array(command,dtype=np.float32);matrix=np.array(fault['matrix_xy'],dtype=np.float32);bias=np.array(fault['bias_xy'],dtype=np.float32);deadzone=np.array(fault['deadzone_xy'],dtype=np.float32)
    latent=np.matmul(matrix,command[:2])+bias;transformed=command.copy()
    transformed[:2]=np.sign(latent)*np.maximum(np.abs(latent)-deadzone,0)/(1-deadzone)
    noisy=transformed.copy();noisy[0:3]=noisy[0:3]+np.array(noise,dtype=np.float32);last=np.clip(noisy,-1,1)
    return {'latent_xy_oracle':latent.tolist(),'transformed_action_oracle':transformed.tolist(),'actual_noise_xyz_oracle':np.array(noise,np.float32).tolist(),
        'before_final_clip_oracle':noisy.tolist(),'applied_action_oracle':last.tolist(),'final_clip_xyz_oracle':[bool(abs(v)>1) for v in noisy[:3]]}


def audit_case(case,events,exported,summary,stages,tape):
    raw=[e for e in events if e['event']=='STEP_COMPLETE'];public=[e for e in events if e['event']=='AGENT_EVENT'];fields=0
    commands={e['sequence']:e['public_payload'] for e in public if e['agent_event']=='COMMAND'}
    plans={e['public_payload']['sequence']:e['public_payload']['saved_plan']['pi_plan']['numbers'] for e in public if e['agent_event']=='PI_PLAN'}
    old=case['initial']['observation'];hist=[];is_lifted=False;relocation=[];cliptask=clipfinal=0
    for i,(e,s) in enumerate(zip(raw,exported)):
        io.require(e['logical_step']==i and e['noise_cursor_after']==i+1,'absolute source cursor')
        fault=case['destination_oracle'] if case['boundary_applied'] and i>=case['planned_boundary'] else case['initial_fault_oracle']
        chain=independent_chain(e['command'],fault,tape[i]);io.require(np.array_equal(np.array(chain['applied_action_oracle'],np.float32),np.array(e['executed_action_oracle'],np.float32)),'source action bytes')
        c=commands[e['global_command_sequence']];plan=plans[c['decision_sequence']] if e['raw_policy'] is not None else None
        expected={k:case[k] for k in ('group','task','seed','context','planned_boundary','action')}
        expected.update(logical_step=i,phase=e['phase'],before_xyz=old[:3],after_xyz=e['after']['observation'][:3],
            actual_hand_delta_xyz=[e['after']['observation'][j]-old[j] for j in range(3)],object_delta_xyz=[e['after']['observation'][j]-old[j] for j in range(4,7)],
            gripper_observation=old[3],command=e['command'],policy_action_clip=None if plan is None else max(abs(v) for v in e['raw_policy'])>1,
            task_correction_send_limit=None if plan is None else plan['send_limit_active'],relocation=None,**chain)
        if e['phase']=='REPOSITION':
            if not hist:hist=[old];is_lifted=old[2]>=.235
            target=[0.,.6,.25] if is_lifted else [hist[0][0],hist[0][1],.25]
            velocity=[0.,0.,0.] if len(hist)==1 else [old[j]-hist[-2][j] for j in range(3)]
            error=[target[j]-old[j] for j in range(3)];pd=[8*error[j]-16*velocity[j] for j in range(3)]
            io.require(np.array_equal(np.array(e['command'],np.float32),np.array([max(-.5,min(.5,v)) for v in pd]+[-1.],np.float32)),'separate PD formula')
            pre=conditions(hist);hist.append(e['after']['observation'])
            expected['relocation']={'index':len(relocation)+1,'stage':'LATERAL' if is_lifted else 'LIFT','active_target_xyz':target,'active_error_xyz_m':error,
                'raw_PD_xyz':pd,'PD_limit_active_xyz':[abs(v)>.5 for v in pd],'controller_velocity_xyz_m':None if len(hist)==2 else velocity,
                'controller_velocity_missing_reason':'REGISTERED_ZERO_DERIVATIVE_ON_FIRST_STEP_NOT_A_MEASURED_DISPLACEMENT' if len(hist)==2 else None,
                'before_gates':pre,'after_gates':conditions(hist),'balance_reference_oracle':rational_reference(fault)}
            relocation.append(expected);is_lifted=is_lifted or hist[-1][2]>=.235
        fields+=same(s,expected,'step');cliptask+=expected['task_correction_send_limit'] is True;clipfinal+=any(chain['final_clip_xyz_oracle']);old=e['after']['observation']
    io.require(len(raw)==len(exported)==case['total_steps'],'all saved source steps')
    metadata={k:case[k] for k in ('group','task','seed','context','planned_boundary','action','success','deadline_loss','total_steps','option_reason','boundary_reached','movement_steps','warm_probe_steps','complete_warm_window')}
    live=[e['public_payload'] for e in public if e['agent_event']=='TASK_MEMORY_SUSPEND'];returned=[e['public_payload'] for e in public if e['agent_event']=='TASK_MEMORY_RETURN'];late=relocation[-8:]
    metadata.update(final_relocation_gates=None if not relocation else relocation[-1]['relocation']['after_gates'],
        phase_missing_reason=None if relocation else 'NOT_A_MOVE_PROGRAM' if case['action']!='MOVE_MEASURE8' else 'EARLY_SUCCESS_NO_ACQUISITION',
        lift_steps=sum(s['relocation']['stage']=='LIFT' for s in relocation),lateral_steps=sum(s['relocation']['stage']=='LATERAL' for s in relocation),
        late_relocation_actual_n=len(late),late_active_error_xy_mean_m=None if not late else [fsum(s['relocation']['active_error_xyz_m'][j] for s in late)/len(late) for j in (0,1)],
        late_noise_xyz_mean_oracle=None if not late else [fsum(s['actual_noise_xyz_oracle'][j] for s in late)/len(late) for j in (0,1,2)],
        task_integral_at_suspend=None if not live else live[0]['memory']['integral_xy'],returned_task_integral=None if not returned else returned[0]['memory']['integral_xy'],
        first_move_command_jump_xy=None,first_return_task_command_jump_xy=None,task_correction_send_limit_steps=cliptask,actuator_final_clip_steps=clipfinal,
        balance_reference_oracle=None if not relocation else rational_reference(case['destination_oracle'] if case['boundary_applied'] else case['initial_fault_oracle']))
    if relocation:
        n=relocation[0]['logical_step']
        if n:metadata['first_move_command_jump_xy']=[raw[n]['command'][j]-raw[n-1]['command'][j] for j in (0,1)]
    if returned:
        n=returned[0]['at_calls']
        if 0<n<len(raw):metadata['first_return_task_command_jump_xy']=[raw[n]['command'][j]-raw[n-1]['command'][j] for j in (0,1)]
    fields+=same(summary,metadata,'trajectory')
    expect=[]
    for stage in ('LIFT','LATERAL'):
        for lo,hi in ((1,8),(9,16),(17,32),(33,64)):
            a=[s for s in relocation if lo<=s['relocation']['index']<=hi and s['relocation']['stage']==stage]
            b=[s['relocation']['after_gates']['recent_motion_inf_m'] for s in a if s['relocation']['after_gates']['recent_motion_inf_m'] is not None]
            expect.append({k:case[k] for k in ('group','task','seed','context','planned_boundary','action')}|{
                'stage':stage,'bin_lo':lo,'bin_hi':hi,'actual_n':len(a),'position_error_mean_m':None if not a else fsum(s['relocation']['after_gates']['position_error_inf_m'] for s in a)/len(a),
                'motion_mean_m':None if not b else fsum(b)/len(b),'PD_limit_step_fraction':None if not a else sum(any(s['relocation']['PD_limit_active_xyz']) for s in a)/len(a),
                'missing_reason':None if a else 'NO_ACTUAL_RELOCATION_IN_THIS_STAGE_AND_BIN'})
    return fields+same(stages,expect,'stages')


def audit(path):
    start=perf_counter_ns();path=path.resolve();m=source.checked(path);out=path.parent;done=io.read(out/'completion.json')
    io.require(done['manifest_id']==m['manifest_id'],'completion manifest')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'export bytes changed')
    native=source.SOURCE/'native';cases=list(io.rows(native/'cases.jsonl.gz'));events=list(io.rows(native/'events.jsonl.gz'))
    saved=list(io.rows(out/'step_diagnostics.jsonl.gz'));traj=io.read(out/'trajectory_diagnostics.json');stage=io.read(out/'stage_diagnostics.json');fields=cursor=0
    from src.analysis.memory_acquisition_io_v1 import noise
    for j,c in enumerate(cases):
        n=c['total_steps'];chunk=events[c['event_start_sequence']:c['event_end_sequence_exclusive']]
        fields+=audit_case(c,chunk,saved[cursor:cursor+n],traj[j],stage[j*8:j*8+8],noise(c['seed']));cursor+=n
    io.require(cursor==len(saved)==8836 and len(traj)==54 and len(stage)==432,'complete population')
    pairs=[]
    for c in (v for v in cases if v['action']=='MOVE_MEASURE8'):
        d=next(v for v in cases if v['action']=='CONTINUE' and all(v[k]==c[k] for k in ('group','task','context')))
        cost=c['movement_steps']+c['warm_probe_steps'];delta=c['deadline_loss']-d['deadline_loss']
        pairs.append({k:c[k] for k in ('group','task','seed','context','planned_boundary')}|{'L_move_minus_continue':delta,'actual_movement_and_probe_steps':cost,
            'remaining_loss_difference_after_paid_acquisition':delta-cost,'success_to_failure':d['success'] and not c['success'],'failure_to_success':not d['success'] and c['success'],
            'both_ended_before_decision':not c['boundary_reached'],'descriptive_algebra_not_causal_phase_attribution':True})
    masks=Counter('+'.join(t['final_relocation_gates']['failed_conditions']) or 'READY' for t in traj if t['final_relocation_gates'] is not None)
    groups=[]
    for g in (0,1,2):
        p=[v for v in pairs if v['group']==g];groups.append({'group':g,'paired_units':len(p),'mean_L_move_minus_continue':fsum(v['L_move_minus_continue'] for v in p)/len(p),
            'mean_actual_acquisition_steps':fsum(v['actual_movement_and_probe_steps'] for v in p)/len(p)})
    result={'classification':'POST_HOC_DESCRIPTIVE_ONLY','source_executions':54,'source_steps':8836,'source_task_failures':sum(not c['success'] for c in cases),
        'assigned_moves':18,'actual_move_cases':sum(c['movement_steps']>0 for c in cases),'full_windows':sum(c['complete_warm_window'] for c in cases),
        'final_gate_mask_counts_among_actual_moves':dict(masks),'paired_costs':pairs,'whole_groups':groups,
        'new_environment_steps':0,'new_resets':0,'new_physical_frames':0,'new_model_fits':0,'new_online_LLM_API_calls':0,
        'unexecuted_trajectories_generated':0,'no_control_or_threshold_changes':True,'publication_goal_complete':False}
    fields+=same(io.read(out/'results.json'),result,'all summaries')
    with (out/'move_cases.csv').open(encoding='utf-8-sig',newline='') as f:table=list(csv.DictReader(f))
    moves=[t for t in traj if t['action']=='MOVE_MEASURE8'];io.require(len(table)==len(moves)==18,'all exported moves')
    for c,t in zip(table,moves):
        gate=t['final_relocation_gates'];want={k:t[k] for k in ('group','task','seed','context','planned_boundary','success','deadline_loss','option_reason','movement_steps','warm_probe_steps','complete_warm_window','lift_steps','lateral_steps')}|{
            'final_position_error_m':None if gate is None else gate['position_error_inf_m'],'final_clearance_m':None if gate is None else gate['clearance_m'],
            'final_motion_m':None if gate is None else gate['recent_motion_inf_m'],'failed_conditions':None if gate is None else '+'.join(gate['failed_conditions']),'phase_missing_reason':t['phase_missing_reason']}
        io.require(set(c)==set(want),'CSV fields')
        for k,v in want.items():
            if v is None:io.require(c[k]=='','missing CSV reason/metric was filled')
            elif type(v) in (int,float):same(float(c[k]),v,'CSV '+k)
            else:io.require(c[k]==str(v),'CSV scalar '+k)
            fields+=1
    record={'integrity':'PASSED','source_executions':54,'source_steps':8836,'trajectory_stage_rows':432,'assigned_moves':18,'source_task_failures':8,
        'fields_checked':fields,'completion_sha256':io.sha(out/'completion.json'),'artifact_sha256':done['artifact_sha256'],'auditor_sha256':io.sha(__file__),
        'main_diagnostic_functions_not_called':True,'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0}
    io.write(out/'audit.json',record);return record
