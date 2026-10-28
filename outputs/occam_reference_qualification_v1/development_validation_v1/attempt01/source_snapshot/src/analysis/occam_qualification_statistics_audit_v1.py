"""Independent scalar/Fraction statistics with all production statistics disabled."""
from fractions import Fraction
from pathlib import Path
from time import perf_counter_ns
from contextlib import ExitStack
from unittest.mock import patch
import gzip,json,math
import numpy as np
from src.analysis import occam_reference_qualification_io_v1 as a
io=a.io


def verify(panels,indices,saved):
    require=io.require;expected={tuple(s[k] for k in a.KEYS) for s in a.population('QUAL')}
    actual={tuple(p[k] for k in a.KEYS) for p in panels}
    require(len(panels)==len(actual)==len(expected)==1404 and actual==expected,'all independent allocation cells, no duplicate/missing unit')
    for row in panels:require(type(row['success']) is bool and row['deadline_loss']==(row['total_steps'] if row['success'] else 500),'full integer loss')
    require(len(indices)==10000 and all(len(row)==9 for row in indices),'exact registered draws')
    for row in indices:
        for col,g in enumerate(row):require(type(g) is int and g in (col//3,col//3+3,col//3+6),'independent whole-group strata')
    # PRNG is a shared library; no production draw or statistical function used.
    generator=np.random.Generator(np.random.PCG64(2026102873));reference=np.empty((10000,9),int)
    for offset in range(3):reference[:,3*offset:3*offset+3]=np.array([offset,offset+3,offset+6])[generator.integers(0,3,size=(10000,3))]
    require(reference.tolist()==indices,'registered fixed PRNG draws')
    lookup={(p['program'],p['group'],p['task'],p['context']):p for p in panels};fields=0
    def same(x,y,message):
        nonlocal fields
        fields+=1
        if type(x) is float or type(y) is float:require(x is not None and y is not None and math.isclose(x,y,rel_tol=1e-12,abs_tol=1e-12),message)
        else:require(x==y,message)
    def endpoints(values):
        values=sorted(values);result=[]
        for numerator in (1,39):
            pos=Fraction(numerator*9999,40);whole=pos.numerator//pos.denominator;rem=pos-whole
            result.append(values[whole]*(1-rem)+values[min(whole+1,9999)]*rem)
        return result
    for name in ('primary','secondary'):
        for item in saved[name]:
            differences=[];success=0
            for group in range(9):
                value=0
                for task in io.TASKS:
                    for context in ('UNCHANGED','CHANGED'):
                        l=lookup[item['left'],group,task,context];r=lookup[item['right'],group,task,context]
                        value+=l['deadline_loss']-r['deadline_loss'];success+=int(l['success'])-int(r['success'])
                differences.append(value)
            samples=[Fraction(sum(differences[g] for g in row),54) for row in indices];lo,hi=endpoints(samples)
            same(item['group_integer_loss_differences'],differences,'group paired losses');same(item['mean_loss_difference'],float(Fraction(sum(differences),54)),'mean full loss')
            same(item['success_difference'],success,'all success changes');same(item['CI95_exact'],[str(lo),str(hi)],'exact independent quantiles')
            same(item['CI95'],[float(lo),float(hi)],'derived interval');same(item['upper_strictly_below_zero'],hi<0,'strict gate sign')
    cfg=a.config();same([p['right'] for p in saved['primary']],cfg['primary_comparators'],'all seven fixed primary opponents')
    same([p['left'] for p in saved['primary']],[cfg['primary_program']]*7,'no primary substitution')
    same(saved['task_qualified'],all(Fraction(p['CI95_exact'][1])<0 for p in saved['primary']),'intersection task gate')
    same([p['program'] for p in saved['programs']],list(a.PROGRAMS),'all26 output rows')
    for p in saved['programs']:
        rows=[r for r in panels if r['program']==p['program']];available=[r for r in rows if r['mse'] is not None]
        for key,value in dict(executions=54,success=sum(bool(r['success']) for r in rows),failure=sum(not r['success'] for r in rows),
            mean_deadline_loss=sum(r['deadline_loss'] for r in rows)/54,actual_steps=sum(r['total_steps'] for r in rows),
            filter_updates=sum(r['filter_updates'] for r in rows),prediction_available=len(available),
            mean_trajectory_MSE=None if not available else math.fsum(r['mse'] for r in available)/len(available)).items():same(p[key],value,'complete program '+key)
    primary=[p for p in panels if p['program']==cfg['primary_program']];group_values=[]
    for group in range(9):
        values=[p for p in primary if p['group']==group and p['mse'] is not None]
        group_values.append((sum((Fraction(p['mse'])-Fraction(p['constant_mse']) for p in values),Fraction()),len(values)))
    points={}
    for task in io.TASKS:
        values=[p for p in primary if p['task']==task and p['mse'] is not None]
        points[task]=None if not values else sum((Fraction(p['mse'])-Fraction(p['constant_mse']) for p in values),Fraction())/len(values)
        same(saved['prediction']['task_points'][task]['available'],len(values),'task prediction availability')
        same(saved['prediction']['task_points'][task]['exact_difference'],None if points[task] is None else str(points[task]),'task exact predictive point')
    samples=[];missing=0
    for row in indices:
        denominator=sum(group_values[g][1] for g in row)
        if not denominator:missing+=1
        else:samples.append(sum((group_values[g][0] for g in row),Fraction())/denominator)
    same(saved['prediction']['allocated_trajectories'],54,'full predictive allocated denominator')
    same(saved['prediction']['available_trajectories'],sum(n for _,n in group_values),'full available denominator');same(saved['prediction']['unavailable_bootstrap_draws'],missing,'missing resamples not replaced')
    predictive=False
    if not missing and samples:
        lo,hi=endpoints(samples);same(saved['prediction']['CI95_exact'],[str(lo),str(hi)],'conditional factual predictive interval')
        predictive=hi<0 and all(v is not None and v<0 for v in points.values())
    same(saved['prediction']['qualified'],predictive,'separate predictive gate')
    same(saved['probability_calibration_qualified'],False,'no probability qualification');same(saved['A_mechanism_qualified'],False,'no algorithm novelty from reference qualification')
    return dict(integrity='PASSED',checked_fields=fields,all_executions=1404,independent_groups=9,
        production_statistics_disabled=True,exact_Fraction_signs=True,new_physics=0,new_fits=0,online_LLM_API_calls=0)


def audit(path):
    from src.analysis import occam_qualification_statistics_v1 as main
    from src.analysis.release_learning_guard_v1 import read_only
    start=perf_counter_ns();path=Path(path).resolve();m=a.checked(path);out=path.parent/'statistics_v1';saved=io.read(out/'statistics.json')
    source=path.parent/'qual/audit.json';require=io.require
    require(io.sha(source)==saved['source_audit_sha256'] and io.sha(out/'bootstrap_indices.json.gz')==saved['bootstrap_indices_sha256'],'bound statistic inputs')
    with gzip.open(out/'bootstrap_indices.json.gz','rt',encoding='utf8') as f:indices=json.load(f)
    guard={}
    def denied(*args,**kwargs):raise AssertionError('primary statistical implementation forbidden')
    with read_only(guard),ExitStack() as stack:
        for name in ('summarize','contrast','prediction_gate','draws','quantile','interval','validate_panels'):stack.enter_context(patch.object(main,name,denied))
        result=verify(io.read(source)['panels'],indices,saved)
    result.update(manifest_id=m['manifest_id'],guard=guard,source_statistics_sha256=io.sha(out/'statistics.json'),wall_ns=perf_counter_ns()-start)
    io.write(out/'independent_audit.json',result);return result
