"""Full-allocation saved-forecast endpoint scoring; no task-value claim."""
from pathlib import Path
from time import perf_counter_ns,time_ns
from decimal import Decimal,localcontext,ROUND_HALF_EVEN
from collections import defaultdict
import numpy as np
from src.analysis import paired_packet_io_v1 as a
from src.analysis.paired_packet_training_v1 import families
from src.probe.paired_packet_model_v1 import METHODS
from src.probe.paired_packet_query_v1 import PAIRS
io=a.io
HORIZONS=(8,16)


def endpoint_nm(pred,left,right):
    io.require(len(pred)==len(left)==len(right)==2 and all(np.isfinite(x) for v in (pred,left,right) for x in v),'finite public endpoint and saved forecast')
    with localcontext() as c:
        c.prec=80;error=[Decimal(str(p))-(Decimal(str(r))-Decimal(str(l))) for p,l,r in zip(pred,left,right)]
        loss=min(Decimal(1),(sum(x*x for x in error)/2).sqrt())
        return int((loss*Decimal(10)**9).to_integral_value(rounding=ROUND_HALF_EVEN))


def scores(data):
    result=[]
    for f in data:
        rec=f['saved_forecast'];valid=rec is not None and rec['forecast_error'] is None
        for left,right in PAIRS:
            pair=left+'__'+right
            for h in HORIZONS:
                available=f['packet_lengths'][left]>=h and f['packet_lengths'][right]>=h
                for method in METHODS:
                    reason='AVAILABLE' if available and valid else 'ENTRY_UNAVAILABLE' if rec is None else 'INVALID_FORECAST' if not valid else 'SHORT_OR_TERMINAL_PAIR'
                    value=endpoint_nm(rec['forecasts'][method][pair][h-1],f['packet_positions_xy'][left][h-1],f['packet_positions_xy'][right][h-1]) if reason=='AVAILABLE' else 10**9
                    result.append({k:f[k] for k in ('family_index','group','task','context','boundary','acquisition_action')}|dict(pair=pair,horizon=h,method=method,loss_nm=value,availability=reason))
    return result


def panels(rows):
    levels=((),('task',),('context',),('acquisition_action',),('boundary',),('horizon',),('task','context','acquisition_action','boundary','horizon'))
    output=[]
    for fields in levels:
        grouped=defaultdict(list)
        for r in rows:grouped[tuple(r[k] for k in fields)+(r['method'],)].append(r)
        for key,part in sorted(grouped.items(),key=lambda x:str(x[0])):
            bygroup=defaultdict(list)
            for r in part:bygroup[r['group']].append(r['loss_nm'])
            observed=defaultdict(list)
            for r in part:
                if r['availability']=='AVAILABLE':observed[r['group']].append(r['loss_nm'])
            value=float(np.mean([np.mean(v) for v in bygroup.values()]))/1e9
            output.append(dict(level=list(fields),strata=dict(zip(fields,key[:-1])),method=key[-1],mean_endpoint_loss_m=value,
                available_only_mean_endpoint_loss_m=None if not observed else float(np.mean([np.mean(v) for v in observed.values()]))/1e9,available_groups=len(observed),
                groups=len(bygroup),allocated_endpoints=len(part),available_endpoints=sum(r['availability']=='AVAILABLE' for r in part),missing_endpoints=sum(r['availability']!='AVAILABLE' for r in part)))
    return output


def whole_group_contrasts(rows,selected):
    indexed={(r['group'],r['family_index'],r['pair'],r['horizon'],r['method']):r['loss_nm'] for r in rows}
    out={};rng=np.random.default_rng(2026102860);draws=np.concatenate([rng.choice(np.array([j,j+3,j+6]),size=(10000,3),replace=True) for j in range(3)],axis=1)
    for baseline in ('ZERO','INSTANT'):
        groups=[]
        for g in range(9):
            delta=[r['loss_nm']-indexed[(g,r['family_index'],r['pair'],r['horizon'],baseline)] for r in rows if r['group']==g and r['method']==selected]
            io.require(len(delta)==72,'all allocated endpoints per independent group');groups.append(float(np.mean(delta))/1e9)
        distribution=np.asarray(groups)[draws].mean(axis=1);lo,hi=np.quantile(distribution,[.025,.975],method='linear')
        out[baseline]=dict(group_mean_selected_minus_baseline_m=groups,mean_difference_m=float(np.mean(groups)),bootstrap95_m=[float(lo),float(hi)])
    return out


def evaluate_split(path,split):
    io.require(split in ('CAL','QUAL'),'only saved out-of-training forecasts');a.checked(path);start=perf_counter_ns();root=Path(path).parent;out=root/(split.lower()+'_evaluation');out.mkdir(exist_ok=False)
    data=families(path,split);rows=scores(data);tables=panels(rows);io.write(out/'endpoint_scores.json',rows);io.write(out/'panels.json',tables)
    allmeans={r['method']:r['mean_endpoint_loss_m'] for r in tables if r['level']==[]}
    if split=='CAL':
        selected=min(('FIR','FREE_CAUSAL'),key=lambda kind:(sum(r['loss_nm'] for r in rows if r['method']==kind),kind!='FIR'))
        result=dict(split=split,status='CALIBRATION_FOR_GLOBAL_FAMILY_LOCK',selected_model=selected,full_allocation_mean_m=allmeans)
    else:
        lock=io.read(root/'model_lock.json');selected=lock['selected_model'];comparison=whole_group_contrasts(rows,selected)
        complete=[f for f in data if f['complete_three_role_H16']];allgroups=len(set(f['group'] for f in complete))==9
        available={task+'__'+ctx+'__'+anchor:sum(1 for f in data if f['task']==task and f['context']==ctx and f['acquisition_action']==anchor for l,r in PAIRS if f['packet_lengths'][l]>=16 and f['packet_lengths'][r]>=16)
            for task in io.TASKS for ctx in ('UNCHANGED','CHANGED') for anchor in ('IN_TASK','MOVE')}
        invalid=io.read(root/'qual/audit.json')['invalid_forecasts'];points={}
        for field,values in (('task',io.TASKS),('horizon',HORIZONS)):
            for v in values:
                means={kind:next(r['mean_endpoint_loss_m'] for r in tables if r['level']==[field] and r['strata']=={field:v} and r['method']==kind) for kind in (selected,'ZERO','INSTANT')}
                points[field+'__'+str(v)]=dict(means_m=means,below_both=all(means[selected]<means[b] for b in ('ZERO','INSTANT')))
        gates=dict(both_primary_CI_upper_negative=all(v['bootstrap95_m'][1]<0 for v in comparison.values()),all_task_and_horizon_points_below_both=all(v['below_both'] for v in points.values()),
            all9_groups_have_complete_family=allgroups,minimum_complete_pairs_per_cell=all(n>=3 for n in available.values()),zero_invalid_forecasts=invalid==0)
        result=dict(split=split,status='QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' if all(gates.values()) else 'CLOSED_NEGATIVE',selected_model=selected,
            full_allocation_mean_m=allmeans,co_primary=comparison,points=points,gates=gates,complete_pairs_by_task_context_anchor=available,invalid_forecasts=invalid)
    result.update(manifest_id=io.read(path)['manifest_id'],classification='KNOWN_INPUT_FORWARD_CONTRAST_NOT_ABSOLUTE_RESPONSE_OR_TASK_UTILITY',
        allocated_families=len(data),complete_three_role_H16_families=sum(f['complete_three_role_H16'] for f in data),endpoint_rows=len(rows),
        artifact_sha256={n:io.sha(out/n) for n in ('endpoint_scores.json','panels.json')},new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False)
    io.write(out/'result.json',result);return result


def lock(path):
    a.checked(path);root=Path(path).parent;io.require(not (root/'qual').exists(),'model selection locked before first QUAL attempt')
    r=io.read(root/'cal_evaluation/result.json');io.require(io.read(root/'cal_evaluation/audit.json')['integrity']=='PASSED','independently checked CAL before lock')
    names=('training/models.json','training/public_train_families.json','training/audit.json','cal/audit.json','cal/completion.json','cal_evaluation/result.json','cal_evaluation/endpoint_scores.json','cal_evaluation/panels.json','cal_evaluation/audit.json')
    value=dict(status='FROZEN_BEFORE_QUAL',selected_model=r['selected_model'],locked_unix_ns=time_ns(),artifact_sha256={n:io.sha(root/n) for n in names},selection_rule='ONE_GLOBAL_FIR_VS_FREE_CAUSAL_FULL_CAL_MEAN_TIE_FIR',no_hyperparameter_or_task_selection=True)
    io.write(root/'model_lock.json',value);return value
