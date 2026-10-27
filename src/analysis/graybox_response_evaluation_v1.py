"""Complete allocation endpoint loss; one finite CAL choice before new QUAL."""
from pathlib import Path
from time import perf_counter_ns,time_ns
from fractions import Fraction
import numpy as np
from src.analysis import graybox_response_io_v1 as a
from src.analysis.graybox_response_training_v1 import families
from src.analysis.history_response_evaluation_v1 import endpoint_nm,panels
from src.probe.graybox_response_model_v1 import methods,BASELINES,SELECTED
io=a.io;HORIZONS=(8,16);PAIRS=(('ZERO','PLUS'),('ZERO','MINUS'),('PLUS','MINUS'))

def scores(data,names):
    out=[]
    for f in data:
        rec=f['saved_forecast']
        for l,r in PAIRS:
            pair=l+'__'+r
            for h in HORIZONS:
                available=min(f['packet_lengths'][l],f['packet_lengths'][r])>=h
                for method in names:
                    valid=rec is not None and rec['forecast_error'] is None and method not in rec['method_errors'] and method in rec['forecasts']
                    reason='ENTRY_UNAVAILABLE' if rec is None else 'INVALID_FORECAST' if not valid else 'SHORT_OR_TERMINAL_PAIR' if not available else 'AVAILABLE'
                    loss=endpoint_nm(rec['forecasts'][method][pair][h-1],f['packet_positions_xy'][l][h-1],f['packet_positions_xy'][r][h-1]) if reason=='AVAILABLE' else 10**9
                    out.append({k:f[k] for k in ('family_index','group','task','context','boundary','acquisition_action')}|dict(pair=pair,horizon=h,method=method,loss_nm=loss,availability=reason))
    return out

def choose_q(rows):
    values=[]
    for i in range(3):
        part=[r for r in rows if r['method']=='GRAY_Q'+str(i)];groups=sorted(set(r['group'] for r in part));io.require(len(groups)==3,'all3 CAL groups')
        value=sum(Fraction(sum(r['loss_nm'] for r in part if r['group']==g),sum(r['group']==g for r in part)) for g in groups)/3;values.append(value)
    index=min(range(3),key=lambda i:(values[i],i))
    return index,[dict(numerator=v.numerator,denominator=v.denominator,unit='NM') for v in values]

def contrasts(rows):
    indexed={(r['group'],r['family_index'],r['pair'],r['horizon'],r['method']):r['loss_nm'] for r in rows};rng=np.random.default_rng(2026103060)
    draws=np.concatenate([rng.choice([j,j+3,j+6],size=(10000,3),replace=True) for j in range(3)],axis=1);out={}
    for baseline in BASELINES:
        values=[]
        for g in range(9):
            delta=[r['loss_nm']-indexed[(g,r['family_index'],r['pair'],r['horizon'],baseline)] for r in rows if r['method']==SELECTED and r['group']==g]
            io.require(len(delta)==72,'all allocated group endpoints');values.append(float(Fraction(sum(delta),72*10**9)))
        boot=np.array(values)[draws].mean(axis=1);lo,hi=np.quantile(boot,[.025,.975],method='linear')
        out[baseline]=dict(group_mean_selected_minus_baseline_m=values,mean_difference_m=float(np.mean(values)),bootstrap95_m=[float(lo),float(hi)])
    return out

def evaluate_split(path,split):
    io.require(split in ('CAL','QUAL'),'saved out-of-training forecasts only');a.checked(path);start=perf_counter_ns();root=Path(path).parent;out=root/(split.lower()+'_evaluation');out.mkdir(exist_ok=False)
    bank,_=a.phase_model(path,split);data=families(path,split);rows=scores(data,methods(bank));tables=panels(rows);io.write(out/'endpoint_scores.json',rows);io.write(out/'panels.json',tables)
    means={p['method']:p['mean_endpoint_loss_m'] for p in tables if p['level']==[]};invalid=io.read(root/split.lower()/'audit.json')['invalid_forecasts']
    if split=='CAL':
        index,selection=choose_q(rows);result=dict(split=split,status='CAL_NUMERICAL_FAILURE_NO_QUAL' if invalid else 'FINITE_PROCESS_CALIBRATION',selected_model=SELECTED,selected_q_index=index,selected_q=a.Q_CHOICES[index],
            exact_selection_scores=selection,full_allocation_mean_m=means,invalid_forecasts=invalid)
    else:
        pairs={t+'__'+c+'__'+p:sum(min(f['packet_lengths'][l],f['packet_lengths'][r])>=16 for f in data if f['task']==t and f['context']==c and f['acquisition_action']==p for l,r in PAIRS)
            for t in io.TASKS for c in ('UNCHANGED','CHANGED') for p in ('IN_TASK','MOVE')}
        points={}
        for field,values in (('task',io.TASKS),('horizon',HORIZONS)):
            for v in values:
                mm={m:next(p['mean_endpoint_loss_m'] for p in tables if p['level']==[field] and p['strata']=={field:v} and p['method']==m) for m in methods(bank)}
                points[field+'__'+str(v)]=dict(means_m=mm,below_all_references=all(mm[SELECTED]<mm[b] for b in BASELINES))
        comparison=contrasts(rows);gates=dict(all_five_primary_CI_upper_negative=all(v['bootstrap95_m'][1]<0 for v in comparison.values()),
            all_task_and_horizon_points_below_all=all(v['below_all_references'] for v in points.values()),all9_groups_have_complete_family={f['group'] for f in data if f['complete_three_role_H16']}==set(range(9)),
            minimum_complete_pairs_per_cell=min(pairs.values())>=3,zero_invalid_forecasts=invalid==0)
        result=dict(split=split,status='QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' if all(gates.values()) else 'CLOSED_NEGATIVE',selected_model=SELECTED,selected_q_index=bank['selected_q_index'],
            selected_q=a.Q_CHOICES[bank['selected_q_index']],full_allocation_mean_m=means,co_primary=comparison,points=points,gates=gates,complete_pairs_by_task_context_anchor=pairs,invalid_forecasts=invalid)
    result.update(manifest_id=io.read(path)['manifest_id'],classification='STANDARD_KNOWN_INPUT_CONTRAST_REFERENCE_NOT_ABSOLUTE_PHYSICS_OR_TASK_GAIN',
        allocated_families=len(data),complete_three_role_H16_families=sum(f['complete_three_role_H16'] for f in data),endpoint_rows=len(rows),
        artifact_sha256={n:io.sha(out/n) for n in ('endpoint_scores.json','panels.json')},wall_ns=perf_counter_ns()-start,
        new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0,publication_goal_complete=False)
    io.write(out/'result.json',result);return result

def lock(path):
    a.checked(path);root=Path(path).parent;io.require(not (root/'qual').exists(),'CAL lock before any QUAL attempt')
    r=io.read(root/'cal_evaluation/result.json');io.require(io.read(root/'cal_evaluation/audit.json')['integrity']=='PASSED' and r['invalid_forecasts']==0,'audited numerically valid CAL')
    names=('training/models.json','training/public_nominal_traces.json','training/public_train_families.json','training/completion.json','training/audit.json',
        'nominal/audit.json','train/audit.json','cal/audit.json','cal/completion.json','cal_evaluation/result.json','cal_evaluation/endpoint_scores.json','cal_evaluation/panels.json','cal_evaluation/audit.json')
    value=dict(status='FROZEN_BEFORE_QUAL',selected_model=SELECTED,selected_q_index=r['selected_q_index'],selected_q=r['selected_q'],locked_unix_ns=time_ns(),locked_monotonic_ns=perf_counter_ns(),
        artifact_sha256={n:io.sha(root/n) for n in names},selection_rule='EXACT_EQUAL_GROUP_COMPLETE_ALLOCATION_LOSS_AMONG3_FIXED_Q_STABLE_INDEX_TIES',no_other_model_or_task_selection=True)
    io.write(root/'model_lock.json',value);return value
