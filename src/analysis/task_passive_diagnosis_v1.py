"""Complete-population descriptive replay; no environment, policy query or fit."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
import gzip
import json
import numpy as np
from src.analysis import task_passive_io_v1 as allocation
from src.analysis import command_contrast_io_v1 as model_source
from src.analysis import passive_response_diagnostic_v1 as core

io=allocation.io; ROOT=allocation.ROOT
SOURCE=allocation.OUTPUT/'task_passive_20261022T032948Z_67fefc4da922'
OUTPUT=ROOT/'outputs/task_passive_diagnosis/analysis_v1'
OWN=('src/analysis/passive_response_diagnostic_v1.py','src/analysis/task_passive_diagnosis_v1.py',
    'scripts/analyze_task_passive_diagnosis_v1.py','tests/test_passive_response_diagnostic_v1.py')


def source_inputs():
    parent=allocation.load_manifest(SOURCE/'manifest.json'); closure=io.read(SOURCE/'result_delivery/closure.json')
    io.require(closure['integrity']=='PASSED' and closure['qualification_gate']=='NOT_PASSED','preserve negative source result')
    io.require(io.sha(SOURCE/'evaluation/qual.json')==closure['qualification_statistics_sha256'],'original comparisons changed')
    inputs={p.relative_to(ROOT).as_posix():io.sha(p) for p in (SOURCE/'manifest.json',SOURCE/'selection.json',
        SOURCE/'evaluation/dev.json',SOURCE/'evaluation/qual.json',SOURCE/'result_delivery/closure.json')}
    for phase in ('software_native','dev','qual'):
        folder=SOURCE/phase; c=io.read(folder/'completion.json'); a=io.read(folder/'audit.json')
        io.require(a['integrity']=='PASSED' and a['completion_sha256']==io.sha(folder/'completion.json'),'source audit binding')
        for name,h in c['artifact_sha256'].items():
            p=folder/name; io.require(io.sha(p)==h,'closed original changed'); inputs[p.relative_to(ROOT).as_posix()]=h
        for name in ('completion.json','audit.json'): inputs[(folder/name).relative_to(ROOT).as_posix()]=io.sha(folder/name)
    banks,_,models=model_source.source_models(); inputs.update(models)
    return parent,banks,inputs


def new_acc(names):
    return {'actual_steps':0,'prediction_steps':0,'mse_sum':{k:0. for k in names},'pi_steps':0,
        'input_delta_sum':{'ZERO_NOISE_INPUT_MAP':0.,'SAME_SAVED_NOISE_INPUT_MAP':0.},
        'input_actual_sum':{'ZERO_NOISE_INPUT_MAP':0.,'SAME_SAVED_NOISE_INPUT_MAP':0.},
        'input_base_sum':{'ZERO_NOISE_INPUT_MAP':0.,'SAME_SAVED_NOISE_INPUT_MAP':0.},
        'input_worse_pi_steps':0,'input_better_pi_steps':0,'raw_policy_queries':0,'raw_xy_clip_steps':0,
        'base_xy_clip_pi_steps':0,'pi_send_limit_steps':0,'actuator_final_clip_steps':0,
        'consecutive_policy_pairs':0,'reference_switches':0,'reference_jump_sum_m':0.}


def add(acc,row):
    acc['actual_steps']+=1
    if row['prediction_mse_m2'] is not None:
        acc['prediction_steps']+=1
        for k,v in row['prediction_mse_m2'].items(): acc['mse_sum'][k]+=v
    if row['input_discrepancy'] is not None:
        acc['pi_steps']+=1
        for k,v in row['input_discrepancy'].items():
            acc['input_delta_sum'][k]+=v['pi_minus_base_mse']; acc['input_actual_sum'][k]+=v['actual_sent_mse']; acc['input_base_sum'][k]+=v['unexecuted_base_mse']
        d=row['input_discrepancy']['SAME_SAVED_NOISE_INPUT_MAP']['pi_minus_base_mse']
        acc['input_worse_pi_steps']+=int(d>0); acc['input_better_pi_steps']+=int(d<0)
    for k in ('raw_policy_queries','raw_xy_clip_steps','base_xy_clip_pi_steps','pi_send_limit_steps','actuator_final_clip_steps'): acc[k]+=row[k]
    if row['reference_jump_m'] is not None:
        acc['consecutive_policy_pairs']+=1; acc['reference_jump_sum_m']+=row['reference_jump_m']; acc['reference_switches']+=int(row['reference_phase_switch'])


def finish(acc):
    r=dict(acc); n=acc['prediction_steps']; p=acc['pi_steps']; ref=acc['consecutive_policy_pairs']
    r['mean_prediction_mse_m2']={k:v/n for k,v in acc['mse_sum'].items()} if n else None
    r['prediction_missing_reason']=None if n else 'NO_COMMON_N_GE_3_RESPONSE'
    for source,target in (('input_delta_sum','mean_pi_minus_base_input_mse'),('input_actual_sum','mean_actual_sent_input_mse'),('input_base_sum','mean_shadow_base_input_mse')):
        r[target]={k:v/p for k,v in acc[source].items()} if p else None
    r['pi_missing_reason']=None if p else 'NO_PI_COMMAND_IN_THIS_WINDOW'
    r['mean_reference_jump_m']=acc['reference_jump_sum_m']/ref if ref else None
    return r


def describe_case(case,events,models):
    steps=[e for e in events if e['event']=='STEP_COMPLETE']; n=len(steps)
    io.require(n==case['total_steps'],'complete physical trace')
    states=np.asarray([case['initial']['observation'],*[s['after']['observation'] for s in steps]])
    commands=np.asarray([s['command'] for s in steps],np.float32).astype(float).reshape(n,4)
    actual_errors=None
    names=['ZERO','PERSIST']+[key+'/'+v for key in models for v in core.VARIANTS]
    if n>=4:
        target,predicted=core.forecast_batch(states,commands,models)
        actual_errors={k:np.mean((v-target)**2,axis=1) for k,v in predicted.items()}
    public=[e for e in events if e['event']=='AGENT_EVENT']; local={e['sequence']:e['public_payload'] for e in public if e['agent_event']=='COMMAND'}
    plans={e['public_payload']['plan_sha256']:e['public_payload']['plan'] for e in public if e['agent_event']=='PI_PLAN'}
    fits=[e['public_payload']['fit'] for e in public if e['agent_event']=='FIT_RESULT' and e['public_payload']['at_calls']==8]
    movement=next((e['public_payload'] for e in public if e['agent_event']=='MOVE_ENTRY'),None)
    anchor=None if movement is None else np.asarray(movement['anchor']); lifted=None if anchor is None else movement['before']['observation'][2]>=anchor[2]-.015
    tape=allocation.noise(case['seed'],case['noise_namespace']); previous_policy=None; move_index=0
    acc={}; rows=[]
    for index,s in enumerate(steps):
        io.require(index==s['logical_step'] and s['noise_cursor_after']==index+1,'noise/history cursor')
        truth=case['destination_oracle'] if case['boundary_applied'] and index>=case['planned_boundary'] else case['initial_fault_oracle']
        applied,clipped=core.apply32(commands[index],truth,tape[index])
        io.require(np.array_equal(applied,np.asarray(s['executed_action_oracle'],np.float32)),'float32 input-map/noise/order mismatch')
        saved=local[s['global_command_sequence']]; raw=saved['raw_policy']; phase='NO_POLICY_QUERY'; jump=None; switched=None
        if raw is not None:
            phase=core.policy_phase(case['task'],states[index]); reference=states[index,:3]+np.asarray(raw)[:3]/core.GAINS[case['task']]
            if previous_policy is not None and previous_policy[0]+1==index:
                jump=float(np.linalg.norm(reference-previous_policy[1])); switched=phase!=previous_policy[2]
            previous_policy=(index,reference,phase)
        discrepancy=None; base_clip=False; send_clip=False
        if saved['pi_plan_sha256'] is not None:
            plan=plans[saved['pi_plan_sha256']]; query=plan['query']; base,base_clip=core.encode_base(query['controller'],raw)
            io.require(np.array_equal(base,np.asarray(plan['numbers']['base_command'],np.float32)) and query['step']==index
                and query['current']['observation']==states[index].tolist(),'saved current PI base differs')
            discrepancy=core.input_discrepancy(commands[index],base,raw,truth,tape[index]); send_clip=plan['numbers']['send_limit_active']
        windows=['ALL','COMMAND/'+s['phase'],'EXPOSURE/'+('DESTINATION' if case['context']=='CHANGED' and case['boundary_applied'] and index>=case['planned_boundary'] else 'INITIAL_BIAS')]
        if raw is not None: windows.append('POLICY/'+phase)
        segment=lift=None
        if s['phase']=='REPOSITION':
            io.require(anchor is not None,'movement has actual entry'); move_index+=1; segment=core.movement_segment(move_index)
            lift='AFTER_LIFT' if lifted else 'LIFT'; windows+=['MOVE_SEGMENT/'+segment,'MOVE_STAGE/'+lift]
            lifted=lifted or states[index+1,2]>=anchor[2]-.015
        row={'logical_step':index,'command_phase':s['phase'],'policy_phase':phase,'windows':windows,
            'actual_response_xy_m':(states[index+1,:2]-states[index,:2]).tolist(),
            'prediction_mse_m2':None if index<3 else {k:float(v[index-3]) for k,v in actual_errors.items()},
            'prediction_missing_reason':'NEEDS_REAL_FOUR_OBSERVATIONS' if index<3 else None,
            'input_discrepancy':discrepancy,'raw_policy_queries':int(raw is not None),'raw_xy_clip_steps':int(raw is not None and np.any(abs(np.asarray(raw)[:2])>1)),
            'base_xy_clip_pi_steps':int(base_clip),'pi_send_limit_steps':int(send_clip),'actuator_final_clip_steps':int(clipped),
            'reference_jump_m':jump,'reference_phase_switch':switched,
            'reference_missing_reason':None if jump is not None else 'NO_CONSECUTIVE_POLICY_REFERENCE',
            'movement_segment':segment,'movement_stage':lift}
        for w in windows:
            if w not in acc: acc[w]=new_acc(names)
            add(acc[w],row)
        rows.append(row)
    if not n: acc['ALL']=new_acc(names)
    summary={k:case[k] for k in ('cohort','case_id','unit_id','group','task','context','style','time_constant_s','success','deadline_loss','total_steps','boundary_applied','boundary_missing_reason')}
    summary.update(windows={k:finish(v) for k,v in acc.items()},c8_fit=fits[0] if fits else None,
        c8_missing_reason=None if fits else 'PROGRAM_WITHOUT_C8' if case['style'] in ('NO_PROBE','RAW_TASK_PI') else case['stop_reason'])
    return summary,rows


def summarize(trajectories):
    cells=[]
    for cohort in allocation.COHORTS:
        programs=sorted({(r['style'],r['time_constant_s']) for r in trajectories if r['cohort']==cohort},key=str)
        for style,ti in programs:
            for task in (None,*core.TASKS):
                for context in (None,'UNCHANGED','CHANGED'):
                    selected=[r for r in trajectories if r['cohort']==cohort and r['style']==style and r['time_constant_s']==ti and (task is None or r['task']==task) and (context is None or r['context']==context)]
                    windows=sorted(set().union(*(r['windows'] for r in selected))) if selected else ['ALL']
                    for window in windows:
                        allocated=sorted({r['group'] for r in selected}); group_values=[]; pi_groups=[]
                        for g in allocated:
                            available=[r['windows'][window] for r in selected if r['group']==g and window in r['windows']]
                            valid=[r['mean_prediction_mse_m2'] for r in available if r['mean_prediction_mse_m2'] is not None]
                            if valid: group_values.append({'group':g,'trajectory_means':len(valid),'mse_m2':{k:float(np.mean([v[k] for v in valid])) for k in valid[0]}})
                            pi=[r['mean_pi_minus_base_input_mse'] for r in available if r['mean_pi_minus_base_input_mse'] is not None]
                            if pi: pi_groups.append({'group':g,'trajectory_means':len(pi),'pi_minus_base_input_mse':{k:float(np.mean([v[k] for v in pi])) for k in pi[0]}})
                        cells.append({'cohort':cohort,'style':style,'time_constant_s':ti,'task':task or 'ALL','context':context or 'ALL','window':window,
                            'allocated_trajectories':len(selected),'allocated_groups':len(allocated),'available_prediction_groups':len(group_values),
                            'available_pi_groups':len(pi_groups),'group_values':group_values,'pi_group_values':pi_groups,
                            'group_mean_mse_m2':{k:float(np.mean([v['mse_m2'][k] for v in group_values])) for k in group_values[0]['mse_m2']} if group_values else None,
                            'group_mean_pi_minus_base_input_mse':{k:float(np.mean([v['pi_minus_base_input_mse'][k] for v in pi_groups])) for k in pi_groups[0]['pi_minus_base_input_mse']} if pi_groups else None,
                            'missing_reason':None if group_values else 'NO_ALLOCATED_CASES' if not selected else 'NO_ELIGIBLE_FOUR_OBSERVATION_RESPONSE'})
    return cells


def run():
    started=perf_counter_ns(); parent,banks,inputs=source_inputs()
    code={n:io.sha(ROOT/n) for n in OWN}; now=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder=OUTPUT/('passive_diagnosis_'+now+'_'+io.git('rev-parse','HEAD')[:12]); folder.mkdir(parents=True,exist_ok=False)
    manifest={'classification':'POST_HOC_DESCRIPTIVE_ONLY','source_run':SOURCE.relative_to(ROOT).as_posix(),
        'analysis_git_base':io.git('rev-parse','HEAD'),'analysis_source_sha256':code,'input_sha256':inputs,
        'forecast_variants':list(core.VARIANTS),'common_population':'Actual step n>=3; four real observations; no fabricated initial displacement',
        'models':'All 18 frozen LINEAR predictors; two source banks x three features x three tasks; no selection or refitting',
        'new_environment_steps':0,'new_api_calls':0,'new_model_fits':0,'source_qualification_gate':'NOT_PASSED'}
    manifest['analysis_manifest_id']=io.digest(manifest); io.write(folder/'manifest.json',manifest)
    trajectories=[]; registrations=[]; parameters=[]; canonical={}; expected_steps=0; raw_rows=0; failure=None; current=None; network={}
    try:
        with io.forbid_online_calls(network),gzip.open(folder/'step_diagnostics.jsonl.gz','xt',encoding='utf-8') as out:
            for cohort in allocation.COHORTS:
                phase=cohort.lower(); specs=allocation.population(cohort,io.read(SOURCE/'selection.json')['selected_time_constants_s'] if cohort=='QUAL' else None)
                cases=list(io.rows(SOURCE/phase/'cases.jsonl.gz')); io.require(len(cases)==len(specs),'all source executions retained')
                grouped=iter(groupby(io.rows(SOURCE/phase/'events.jsonl.gz'),lambda e:e['case_id']))
                for c,spec in zip(cases,specs):
                    current=c['case_id']
                    for k,v in spec.items(): io.require(c[k]==v,'population/order drift')
                    key,it=next(grouped); io.require(key==current,'case journal order'); events=list(it)
                    models={k.split('/')[0]+'/'+v[0].feature:v[0] for k,v in banks[c['task']].items()}
                    result,steps=describe_case(c,events,models); trajectories.append(result); expected_steps+=c['total_steps']
                    registrations.append({**{k:c[k] for k in ('case_id','cohort','group','task','context','style','time_constant_s','total_steps','success','stop_reason')},'available_step_rows':len(steps),'missing_reason':None if steps else 'ZERO_LENGTH_TRACE'})
                    fit=result['c8_fit']
                    if c['style'] not in ('NO_PROBE','RAW_TASK_PI'):
                        if c['unit_id'] not in canonical:
                            io.require(c['style']=='DIRECT_C8','canonical initial C8 source')
                            canonical[c['unit_id']]=fit
                            truth=c['initial_fault_oracle']; a=np.asarray(fit['matrix_xy']) if fit and 'matrix_xy' in fit else None
                            parameters.append({'unit_id':c['unit_id'],'cohort':cohort,'group':c['group'],'task':c['task'],'context':c['context'],
                                'canonical_program':'DIRECT_C8','valid':fit['valid'] if fit else None,
                                'matrix_relative_error_to_initial_injected_map':float(np.linalg.norm(a-truth['matrix_xy'])/np.linalg.norm(truth['matrix_xy'])) if a is not None else None,
                                'bias_error_norm_to_initial_injected_map':float(np.linalg.norm(np.asarray(fit['bias_xy'])-truth['bias_xy'])) if a is not None else None,
                                'missing_reason':result['c8_missing_reason'],'scope':'Evaluator injected-input coefficients, not a physical plant or causal task diagnosis'})
                        else: io.require(io.digest(fit)==io.digest(canonical[c['unit_id']]),'common initial C8 fit differs')
                    meta={k:c[k] for k in ('cohort','case_id','group','task','context','style','time_constant_s')}
                    for step in steps: out.write(json.dumps({**meta,**step},ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n'); raw_rows+=1
                    if len(trajectories)%60==0: print(json.dumps({'registered':len(trajectories),'actual_steps':raw_rows}),flush=True)
                io.require(next(grouped,None) is None,'extra source case')
        io.require(len(trajectories)==1188 and expected_steps==raw_rows==153045,'full population/phase counts')
        cells=summarize(trajectories)
        io.write(folder/'registrations.json',registrations); io.write(folder/'trajectory_diagnostics.json',trajectories)
        io.write(folder/'initial_C8_parameters.json',parameters); io.write(folder/'grouped_cells.json',cells)
        for name,h in inputs.items(): io.require(io.sha(ROOT/name)==h,'source changed during diagnostic')
        for name,h in code.items(): io.require(io.sha(ROOT/name)==h,'analysis code changed during run')
        result={'integrity':'PASSED_FOR_DESCRIPTIVE_REVIEW','classification':'POST_HOC_DESCRIPTIVE_ONLY','executions':1188,'actual_recorded_steps':raw_rows,
            'common_prediction_steps':sum(max(r['total_steps']-3,0) for r in trajectories),'canonical_initial_C8_units':len(canonical),
            'trajectory_windows':sum(len(r['windows']) for r in trajectories),'grouped_cells':len(cells),
            'network_guard':network,'new_environment_steps':0,'new_api_calls':0,'new_model_fits':0,'wall_ns':perf_counter_ns()-started,
            'analysis_manifest_id':manifest['analysis_manifest_id'],'source_qualification_gate_unchanged':'NOT_PASSED'}
        io.write(folder/'completion.json',{**result,'artifact_sha256':{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()}})
        print(str(folder),flush=True); return folder
    except BaseException as error:
        failure={'status':'FAILED_ANALYSIS_PRESERVED','case_id':current,'type':type(error).__name__,'message':str(error),
            'completed_registrations':len(trajectories),'step_rows':raw_rows,'new_environment_steps':0,'new_api_calls':0,'new_model_fits':0}
        io.write(folder/'failure.json',failure); raise
