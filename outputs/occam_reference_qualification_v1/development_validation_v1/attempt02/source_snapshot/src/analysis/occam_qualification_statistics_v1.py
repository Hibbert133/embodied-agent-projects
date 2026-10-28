"""Whole-group preregistered task and prequential gates, never timestep inference."""
from pathlib import Path
from fractions import Fraction
from time import perf_counter_ns
import gzip,json
import numpy as np
from src.analysis import occam_reference_qualification_io_v1 as a
io=a.io


def validate_panels(panels):
    expected=a.population('QUAL');io.require(len(panels)==len(expected)==1404,'all1404 allocated programs')
    seen=set()
    for row,spec in zip(panels,expected):
        io.require({k:row[k] for k in a.KEYS}==spec and a.key(spec) not in seen,'exact unique QUAL order');seen.add(a.key(spec))
        n=row['total_steps'];loss=row['deadline_loss']
        io.require(type(row['success']) is bool and type(n) is int and 0<=n<=500 and type(loss) is int and loss==(n if row['success'] else 500),'actual cutoff loss and complete failure denominator')
        for k in ('mse','constant_mse'):io.require(row[k] is None or type(row[k]) is float and np.isfinite(row[k]) and row[k]>=0,'finite or explicitly missing predictive metric')
        io.require((row['mse'] is None)==(row['constant_mse'] is None),'same factual prediction denominator')


def draws():
    rng=np.random.default_rng(a.registry()['bootstrap_seed']);result=np.empty((10000,9),dtype=np.int64)
    for offset in range(3):
        ids=np.array([offset,offset+3,offset+6]);result[:,offset*3:(offset+1)*3]=ids[rng.integers(0,3,(10000,3))]
    return result


def quantile(values,numerator,denominator):
    ordered=sorted(values);position=Fraction((len(ordered)-1)*numerator,denominator);lo=position.numerator//position.denominator
    part=position-lo;return ordered[lo] if lo+1==len(ordered) else ordered[lo]*(1-part)+ordered[lo+1]*part


def interval(values):
    lo=quantile(values,1,40);hi=quantile(values,39,40)
    return dict(CI95=[float(lo),float(hi)],CI95_exact=[str(lo),str(hi)],upper_strictly_below_zero=hi<0)


def contrast(panels,left,right,indices):
    by={(r['program'],r['group'],r['task'],r['context']):r for r in panels};totals=[];success=[]
    for group in range(9):
        pairs=[(by[(left,group,t,c)],by[(right,group,t,c)]) for t in io.TASKS for c in ('UNCHANGED','CHANGED')]
        totals.append(sum(l['deadline_loss']-r['deadline_loss'] for l,r in pairs));success.append(sum(int(l['success'])-int(r['success']) for l,r in pairs))
    samples=[Fraction(sum(totals[int(g)] for g in row),54) for row in indices]
    return dict(left=left,right=right,denominator=54,independent_groups=9,group_integer_loss_differences=totals,
        mean_loss_difference=float(Fraction(sum(totals),54)),success_difference=sum(success),**interval(samples))


def prediction_gate(panels,indices):
    chosen=[r for r in panels if r['program']=='META_ADAPT__CONTINUE'];groups=[];tasks={}
    for group in range(9):
        usable=[r for r in chosen if r['group']==group and r['mse'] is not None]
        groups.append((sum((Fraction(r['mse'])-Fraction(r['constant_mse']) for r in usable),Fraction()),len(usable)))
    for task in io.TASKS:
        usable=[r for r in chosen if r['task']==task and r['mse'] is not None]
        value=None if not usable else sum((Fraction(r['mse'])-Fraction(r['constant_mse']) for r in usable),Fraction())/len(usable)
        tasks[task]=dict(allocated=18,available=len(usable),mean_MSE_difference=None if value is None else float(value),exact_difference=None if value is None else str(value))
    samples=[];unavailable=0
    for row in indices:
        n=sum(groups[int(g)][1] for g in row)
        if not n:unavailable+=1;continue
        samples.append(sum((groups[int(g)][0] for g in row),Fraction())/n)
    result=dict(allocated_trajectories=54,available_trajectories=sum(n for _,n in groups),task_points=tasks,
        group_available_counts=[n for _,n in groups],unavailable_bootstrap_draws=unavailable,
        missing_are_not_zero_targets=True,conditional_on_own_observed_windows=True)
    if unavailable or not samples:result.update(qualified=False,CI95=None,reason='INSUFFICIENT_FACTUAL_PREDICTIONS')
    else:
        estimate=interval(samples);result.update(**estimate,qualified=estimate['upper_strictly_below_zero'] and all(t['exact_difference'] is not None and Fraction(t['exact_difference'])<0 for t in tasks.values()),reason='FROZEN_GATE_EVALUATED')
    return result


def summarize(panels,indices):
    validate_panels(panels);io.require(np.shape(indices)==(10000,9),'all registered group resamples')
    for i,row in enumerate(np.asarray(indices).T):io.require(set(map(int,row))<=set((i//3,i//3+3,i//3+6)),'whole groups stay in boundary stratum')
    cfg=a.config();primary=[contrast(panels,cfg['primary_program'],right,indices) for right in cfg['primary_comparators']]
    secondary=[]
    for action in ('CONTINUE','VALIDATE8','MOVE_MEASURE'):
        for left,right in (('META_ADAPT','META_FROZEN'),('ERM_ADAPT','ERM_FROZEN'),('META_ADAPT','ERM_ADAPT')):
            secondary.append(contrast(panels,left+'__'+action,right+'__'+action,indices))
    table=[]
    for program in a.PROGRAMS:
        part=[r for r in panels if r['program']==program];usable=[r for r in part if r['mse'] is not None]
        table.append(dict(program=program,executions=len(part),success=sum(r['success'] for r in part),failure=sum(not r['success'] for r in part),
            mean_deadline_loss=sum(r['deadline_loss'] for r in part)/54,actual_steps=sum(r['total_steps'] for r in part),
            filter_updates=sum(r['filter_updates'] for r in part),prediction_available=len(usable),
            mean_trajectory_MSE=None if not usable else float(np.mean([r['mse'] for r in usable]))))
    return dict(primary=primary,secondary=secondary,programs=table,task_qualified=all(r['upper_strictly_below_zero'] for r in primary),
        prediction=prediction_gate(panels,indices),all_failures_retained=True,standard_reference_only=True,
        probability_calibration_qualified=False,A_mechanism_qualified=False,publication_goal_complete=False)


def compute(path):
    start=perf_counter_ns();path=Path(path).resolve();m=a.checked(path);root=path.parent/'qual';audit=io.read(root/'audit.json')
    io.require(audit['integrity']=='PASSED' and audit['counts']['executions']==1404,'complete independent deployment audit')
    indices=draws();out=path.parent/'statistics_v1';out.mkdir(exist_ok=False)
    with gzip.open(out/'bootstrap_indices.json.gz','xt',encoding='utf8') as f:json.dump(indices.tolist(),f,separators=(',',':'))
    result=summarize(audit['panels'],indices);result.update(integrity='PASSED',manifest_id=m['manifest_id'],
        source_audit_sha256=io.sha(root/'audit.json'),bootstrap_indices_sha256=io.sha(out/'bootstrap_indices.json.gz'),
        group_bootstrap_seed=a.registry()['bootstrap_seed'],new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
    io.write(out/'statistics.json',result);return result
