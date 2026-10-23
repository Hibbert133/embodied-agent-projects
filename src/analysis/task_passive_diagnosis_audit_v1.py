"""Independent arrays/raw-coefficients reconstruction of descriptive outputs."""
from collections import defaultdict
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
import json
import runpy
import numpy as np
from src.analysis import task_passive_diagnosis_v1 as allocation
from src.analysis.short_probe_journal_audit_v1 import applied
from src.probe.linear_command_preflight_v1 import make_query

io=allocation.io; ROOT=allocation.ROOT


def near(a,b,label):
    io.require(np.allclose(a,b,rtol=1e-9,atol=1e-18),label)


def independent_forecasts(s,u,bank):
    """Different extraction/matrix path; no new diagnostic core functions."""
    features={}; before=s[:-1]
    movements=np.diff(s[:,:3],axis=0)
    features['F43']=np.concatenate((before[2:],u[2:]),axis=1)
    features['H10']=np.concatenate((movements[1:-1],movements[:-2],u[2:]),axis=1)
    features['F20']=np.concatenate((before[2:,:3],movements[1:-1],movements[:-2],u[2:],before[2:,3:4],
        before[2:,4:7]-before[2:,:3],before[2:,-3:]-before[2:,:3]),axis=1)
    prior=np.diff(s[:,:2],axis=0)[2:-1]; predicted={'ZERO':np.zeros_like(prior),'PERSIST':prior.copy()}
    for name,model in bank.items():
        f=model.feature; x=features[f]; coefficient=np.asarray(model.coefficient); z=(x-np.asarray(model.mean))/np.asarray(model.scale)
        raw=z@coefficient[1:]+coefficient[0]
        start={'H10':6,'F20':9,'F43':39}[f]; gain=(coefficient[1+start:1+start+4]/np.asarray(model.scale)[start:start+4,None]).T
        change=u[3:]-u[2:-1]
        predicted[name+'/RAW']=raw[1:]
        predicted[name+'/XY_INCREMENT']=prior+change[:,:2]@gain[:,:2].T
        predicted[name+'/ALL_INCREMENT']=prior+change@gain.T
        predicted[name+'/LAST_RESIDUAL']=prior+raw[1:]-raw[:-1]
        # Original fixed-model interface checks actual first and last queries.
        for n in sorted({3,len(u)-1}):
            q=make_query(model.task,n,s[n-2:n+1],u[n]); near(raw[n-2],model.predict(q,u[n]),'old single-query interface differs')
    target=np.diff(s[:,:2],axis=0)[3:]
    return {k:np.mean((v-target)**2,axis=1) for k,v in predicted.items()}


def audit(folder):
    started=perf_counter_ns(); folder=Path(folder).resolve(); m=io.read(folder/'manifest.json'); complete=io.read(folder/'completion.json')
    io.require(complete['integrity']=='PASSED_FOR_DESCRIPTIVE_REVIEW','complete descriptive replay required')
    for n,h in m['input_sha256'].items(): io.require(io.sha(ROOT/n)==h,'original source changed')
    for n,h in complete['artifact_sha256'].items(): io.require(io.sha(folder/n)==h,'diagnostic output changed')
    parent,banks,_=allocation.source_inputs(); trajectories=io.read(folder/'trajectory_diagnostics.json'); registrations=io.read(folder/'registrations.json')
    bycase={r['case_id']:r for r in trajectories}; registers={r['case_id']:r for r in registrations}
    io.require(len(bycase)==len(registers)==len(trajectories)==1188,'all source trajectories')
    groups=iter(groupby(io.rows(folder/'step_diagnostics.jsonl.gz'),lambda r:r['case_id']))
    policy_phase=runpy.run_path(str(allocation.SOURCE/'result_delivery/describe_pi.py'))['policy_phase']
    steps_checked=fields=cases_checked=0
    parameter_rows={r['unit_id']:r for r in io.read(folder/'initial_C8_parameters.json')}
    identity={'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'deadzone_xy':[0.,0.]}
    for cohort in allocation.allocation.COHORTS:
        phase=cohort.lower(); source=iter(groupby(io.rows(allocation.SOURCE/phase/'events.jsonl.gz'),lambda r:r['case_id']))
        for c in io.rows(allocation.SOURCE/phase/'cases.jsonl.gz'):
            key,it=next(source); events=list(it); io.require(key==c['case_id'],'source case order')
            key,it=next(groups); saved=list(it); io.require(key==c['case_id'],'diagnostic case order')
            actual=[e for e in events if e['event']=='STEP_COMPLETE']; n=len(actual); io.require(len(saved)==n==c['total_steps']==registers[key]['available_step_rows'],'step denominator')
            s=np.asarray([c['initial']['observation'],*[e['after']['observation'] for e in actual]])
            u=np.asarray([e['command'] for e in actual],float).reshape(n,4)
            bank={k.split('/')[0]+'/'+v[0].feature:v[0] for k,v in banks[c['task']].items()}
            forecasts=independent_forecasts(s,u,bank) if n>=4 else None
            public=[e for e in events if e['event']=='AGENT_EVENT']; commands={e['sequence']:e['public_payload'] for e in public if e['agent_event']=='COMMAND'}
            plans={e['public_payload']['plan_sha256']:e['public_payload']['plan'] for e in public if e['agent_event']=='PI_PLAN'}
            if c['style']=='DIRECT_C8':
                saved_fit=next((e['public_payload']['fit'] for e in public if e['agent_event']=='FIT_RESULT' and e['public_payload']['at_calls']==8),None)
                pr=parameter_rows[c['unit_id']]
                if saved_fit is not None and 'matrix_xy' in saved_fit:
                    near(pr['matrix_relative_error_to_initial_injected_map'],np.linalg.norm(np.asarray(saved_fit['matrix_xy'])-c['initial_fault_oracle']['matrix_xy'])/np.linalg.norm(c['initial_fault_oracle']['matrix_xy']),'forward coefficient mapping')
                    near(pr['bias_error_norm_to_initial_injected_map'],np.linalg.norm(np.asarray(saved_fit['bias_xy'])-c['initial_fault_oracle']['bias_xy']),'injected bias mapping');fields+=2
            tape=allocation.allocation.noise(c['seed'],c['noise_namespace']); sums={}; counts=defaultdict(int); pi_sums=defaultdict(lambda:defaultdict(float)); pi_counts=defaultdict(int)
            for index,(row,e) in enumerate(zip(saved,actual)):
                io.require(row['logical_step']==index,'prediction/response cursor'); fields+=1
                near(row['actual_response_xy_m'],s[index+1,:2]-s[index,:2],'actual response changed'); fields+=2
                request=commands[e['global_command_sequence']]; raw=request['raw_policy']
                if raw is not None: io.require(row['policy_phase']==policy_phase(c['task'],s[index]),'policy phase mismatch')
                truth=c['destination_oracle'] if c['boundary_applied'] and index>=c['planned_boundary'] else c['initial_fault_oracle']
                io.require(applied(u[index],truth,tape[index])==e['executed_action_oracle'],'input transform/order mismatch')
                expected=None if index<3 else {k:float(v[index-3]) for k,v in forecasts.items()}
                if expected is None: io.require(row['prediction_mse_m2'] is None,'invented initial history')
                else:
                    io.require(set(row['prediction_mse_m2'])==set(expected),'all model comparisons retained')
                    for k,v in expected.items(): near(row['prediction_mse_m2'][k],v,'independent response error differs'); fields+=1
                discrepancy={}
                if request['pi_plan_sha256'] is not None:
                    plan=plans[request['pi_plan_sha256']]; base=plan['numbers']['base_command']; ref=np.clip(np.asarray(raw,np.float32),-1,1)
                    for name,eta in (('ZERO_NOISE_INPUT_MAP',np.zeros(3,np.float32)),('SAME_SAVED_NOISE_INPUT_MAP',tape[index])):
                        desired=np.asarray(applied(ref,identity,eta))[:2]; actual_input=np.asarray(applied(u[index],truth,eta))[:2]; base_input=np.asarray(applied(base,truth,eta))[:2]
                        a=float(np.mean((actual_input-desired)**2)); b=float(np.mean((base_input-desired)**2)); discrepancy[name]=a-b
                        for field,value in (('actual_sent_mse',a),('unexecuted_base_mse',b),('pi_minus_base_mse',a-b)):
                            near(row['input_discrepancy'][name][field],value,'input metric is not the saved input map'); fields+=1
                else: io.require(row['input_discrepancy'] is None,'invented PI metric')
                for window in row['windows']:
                    counts[window]+=1
                    if expected is not None:
                        if window not in sums: sums[window]=[0,defaultdict(float)]
                        sums[window][0]+=1
                        for k,v in expected.items(): sums[window][1][k]+=v
                    if discrepancy:
                        pi_counts[window]+=1
                        for k,v in discrepancy.items(): pi_sums[window][k]+=v
                steps_checked+=1
            result=bycase[key]; io.require(set(result['windows'])==set(counts),'window registration')
            for window,value in result['windows'].items():
                io.require(value['actual_steps']==counts[window] and value['prediction_steps']==sums.get(window,[0])[0],'window denominator')
                if window not in sums: io.require(value['mean_prediction_mse_m2'] is None,'missing error filled with zero')
                else:
                    for k,v in sums[window][1].items(): near(value['mean_prediction_mse_m2'][k],v/sums[window][0],'trajectory mean incorrect'); fields+=1
                io.require(value['pi_steps']==pi_counts[window],'PI window denominator')
                if not pi_counts[window]: io.require(value['mean_pi_minus_base_input_mse'] is None,'missing PI window filled')
                else:
                    for k,v in pi_sums[window].items(): near(value['mean_pi_minus_base_input_mse'][k],v/pi_counts[window],'PI trajectory mean incorrect'); fields+=1
            cases_checked+=1
            if cases_checked%120==0:print(json.dumps({'audited_cases':cases_checked,'actual_steps':steps_checked}),flush=True)
        io.require(next(source,None) is None,'unallocated source rows')
    io.require(next(groups,None) is None and steps_checked==153045,'complete source steps')
    cells=io.read(folder/'grouped_cells.json')
    for cell in cells:
        selected=[r for r in trajectories if r['cohort']==cell['cohort'] and r['style']==cell['style'] and r['time_constant_s']==cell['time_constant_s']
            and (cell['task']=='ALL' or r['task']==cell['task']) and (cell['context']=='ALL' or r['context']==cell['context'])]
        io.require(len(selected)==cell['allocated_trajectories'],'full group cell population')
        means=[]
        for group in sorted({r['group'] for r in selected}):
            valid=[r['windows'][cell['window']]['mean_prediction_mse_m2'] for r in selected if r['group']==group and cell['window'] in r['windows'] and r['windows'][cell['window']]['mean_prediction_mse_m2'] is not None]
            if valid: means.append({k:sum(r[k] for r in valid)/len(valid) for k in valid[0]})
        io.require(len(means)==cell['available_prediction_groups'],'missing groups not zero filled')
        if means:
            for k in means[0]: near(cell['group_mean_mse_m2'][k],sum(v[k] for v in means)/len(means),'independent whole-group weighting'); fields+=1
        else: io.require(cell['group_mean_mse_m2'] is None,'missing cells not null')
        pi_means=[]
        for group in sorted({r['group'] for r in selected}):
            valid=[r['windows'][cell['window']]['mean_pi_minus_base_input_mse'] for r in selected if r['group']==group and cell['window'] in r['windows'] and r['windows'][cell['window']]['mean_pi_minus_base_input_mse'] is not None]
            if valid:pi_means.append({k:sum(r[k] for r in valid)/len(valid) for k in valid[0]})
        io.require(len(pi_means)==cell['available_pi_groups'],'PI availability groups')
        if pi_means:
            for k in pi_means[0]:near(cell['group_mean_pi_minus_base_input_mse'][k],sum(v[k] for v in pi_means)/len(pi_means),'independent input discrepancy group weighting');fields+=1
        else:io.require(cell['group_mean_pi_minus_base_input_mse'] is None,'missing PI groups not null')
    for n,h in m['input_sha256'].items(): io.require(io.sha(ROOT/n)==h,'original hash changed')
    result={'integrity':'PASSED','classification':'POST_HOC_DESCRIPTIVE_ONLY','executions':1188,'actual_steps':steps_checked,
        'numeric_fields_checked':fields,'original_input_hashes_unchanged':True,'original_qualification_gate':'NOT_PASSED',
        'completion_sha256':io.sha(folder/'completion.json'),'auditor_sha256':io.sha(__file__),
        'new_environment_steps':0,'new_api_calls':0,'new_model_fits':0,'wall_ns':perf_counter_ns()-started,
        'scope':'Every saved forecast error/input discrepancy reconstructed from old coefficients and records; no counterfactual physical rollout or controller qualification'}
    io.write(folder/'audit.json',result); return result
