"""Whole-group independent-test statistics; no post-result model selection."""
from collections import Counter,defaultdict
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import correction_scope_io_v1 as a
from src.analysis import correction_scope_learning_v1 as learning
from src.analysis import correction_scope_independent_v1 as independent
from src.analysis.release_learning_guard_v1 import read_only
from src.probe import correction_scope_model_v1 as model
io=a.io


def quantile(values,p):
    v=sorted(values);i=(len(v)-1)*p;lo=int(i);f=i-lo
    return v[lo]*(1-f)+v[min(lo+1,len(v)-1)]*f


def group_difference(rows,family,comparator,draws,stage='PRE'):
    grouped=defaultdict(list)
    for r in rows:
        if r['stage']!=stage or r['target'] is None:continue
        forecasts=r['prediction']['predictions'];p=model.family_errors(forecasts['FULL_RBF'],r['target'])
        if comparator=='MARGINAL_PRODUCT':q=p['factorized_joint_32']
        else:q=model.family_errors(forecasts[comparator],r['target'])[family]
        grouped[r['spec']['group']].append(p[family]-q)
    io.require(set(grouped)==set(range(9)),'all TEST independent groups required')
    means=np.asarray([np.mean(grouped[g]) for g in range(9)]);boot=means[np.asarray(draws,int)].mean(1)
    return dict(stage=stage,family=family,comparator=comparator,group_means=means.tolist(),
        group_counts=[len(grouped[g]) for g in range(9)],mean=float(means.mean()),CI95=[float(np.quantile(boot,.025)),float(np.quantile(boot,.975))],
        upper_strictly_below_zero=bool(np.quantile(boot,.975)<0))


def statistics(path):
    path=Path(path).resolve();m=a.checked(path);out=path.parent/'results';out.mkdir(exist_ok=False);start=perf_counter_ns();rows=learning.examples(path,'TEST')
    io.require(io.read(path.parent/'test/prediction_audit.json')['integrity']=='PASSED','independent TEST forecast audit')
    cal=io.read(path.parent/'learning/calibration.json');first=next(io.rows(path.parent/'test/events.jsonl.gz'))['saved_ns'];io.require(first>cal['locked_ns'],'TEST before calibration freeze')
    guard={}
    with read_only(guard):
        rng=np.random.default_rng(202610263);draws=np.concatenate([rng.choice([b,b+3,b+6],size=(10000,3)) for b in range(3)],axis=1).tolist()
        comparisons=[group_difference(rows,f,c,draws) for f in ('occupancy_32','error_32','joint_32') for c in ('PERSISTENCE','COMMAND_RBF','RATE_BLIND_RBF','FULL_LINEAR')]
        comparisons.append(group_difference(rows,'joint_32','MARGINAL_PRODUCT',draws))
        panels=[];metrics=[];availability=Counter()
        for r in rows:availability[r['stage']+'/'+(r['missing_reason'] or 'FACTUAL_TARGET')]+=1
        for stage in model.STAGES:
            for task in model.TASKS:
                for context in ('UNCHANGED','CHANGED'):
                    for boundary in (16,32,64):
                        data=[r for r in rows if r['stage']==stage and r['spec']['task']==task and r['spec']['context']==context and r['spec']['planned_boundary']==boundary]
                        panels.append(dict(stage=stage,task=task,context=context,boundary=boundary,allocated=len(data),targets=sum(r['target'] is not None for r in data),
                            missing=dict(Counter(r['missing_reason'] for r in data if r['target'] is None))))
            for kind in ('PERSISTENCE',*model.KINDS):
                values=[(r,model.family_errors(r['prediction']['predictions'][kind],r['target'])) for r in rows if r['stage']==stage and r['target'] is not None]
                for family in values[0][1]:
                    grouped=defaultdict(list);covered=defaultdict(list)
                    for r,e in values:
                        grouped[r['spec']['group']].append(e[family]);covered[r['spec']['group']].append(float(np.sqrt(e[family])<=cal['radii'][stage][kind][family]))
                    metrics.append(dict(stage=stage,kind=kind,family=family,group_mean_MSE=float(np.mean([np.mean(v) for v in grouped.values()])),
                        empirical_coverage=float(np.mean([np.mean(v) for v in covered.values()])),radius=cal['radii'][stage][kind][family],factual_rows=len(values)))
        costs={};tasks=[];adverse=[]
        for cohort in a.COHORTS:
            s=io.read(path.parent/cohort.lower()/'summary.json');audit=io.read(path.parent/cohort.lower()/'audit.json')
            costs[cohort]=dict(executions=s['executions'],control_steps=s['control_steps'],policy_queries=sum(r['policy_queries'] for r in s['rows']),
                all_resets=s['lifecycle']['counts']['reset_attempts'],physical_frames=s['lifecycle']['counts']['simulation_frames_completed'],
                independent_policy_replay_queries=audit['replay_fixed_policy_queries'],collection_wall_ns=s['wall_ns'],audit_wall_ns=audit['wall_ns'])
            if cohort!='TEST':continue
            for action in model.ACTIONS:
                for rate in model.RATES:
                    cases=[r for r in s['rows'] if r['acquisition_action']==action and r['time_constant_s']==rate]
                    tasks.append(dict(action=action,rate=rate,executions=len(cases),success=sum(r['success'] for r in cases),mean_deadline_loss=float(np.mean([r['deadline_loss'] for r in cases]))))
                    if rate==.5:continue
                    keep={a.unit_key(r):r for r in s['rows'] if r['acquisition_action']==action and r['time_constant_s']==.5}
                    differences=[r['deadline_loss']-keep[a.unit_key(r)]['deadline_loss'] for r in cases]
                    adverse.append(dict(action=action,rate=rate,denominator=len(cases),harm=sum(d>0 for d in differences),help=sum(d<0 for d in differences),ties=sum(d==0 for d in differences),
                        mean_difference=float(np.mean(differences)),success_to_failure=sum(not r['success'] and keep[a.unit_key(r)]['success'] for r in cases),failure_to_success=sum(r['success'] and not keep[a.unit_key(r)]['success'] for r in cases)))
        complete_panels=all(p['targets']>0 for p in panels if p['stage']=='PRE');passed=complete_panels and all(c['upper_strictly_below_zero'] for c in comparisons)
        result=dict(integrity='FOR_INDEPENDENT_STATISTICS_AUDIT',manifest_id=m['manifest_id'],component_gate='PASSED' if passed else 'NOT_QUALIFIED',
            primary='PRE32 joint applicability/query forecast only; not a new algorithm or selected task-performance test',
            comparisons=comparisons,all_PRE_panels_have_targets=complete_panels,panels=panels,availability=dict(availability),
            metrics=metrics,complete_factual_program_results=tasks,fixed_rate_paired_harm_descriptive=adverse,costs=costs,
            bootstrap_indices=draws,bootstrap_replicates=10000,guard=guard,wall_ns=perf_counter_ns()-start,
            online_LLM_API_calls=0,task_benefit_qualified=False,algorithm_novelty_established=False,publication_goal_complete=False)
    io.write(out/'statistics.json',result);return result


def audit_statistics(path):
    path=Path(path).resolve();a.checked(path);out=path.parent/'results';s=io.read(out/'statistics.json');rows=learning.examples(path,'TEST');start=perf_counter_ns();guard={};fields=0
    from unittest.mock import patch
    with read_only(guard),patch.object(model,'family_errors',side_effect=RuntimeError('main metrics disabled')),patch(__name__+'.group_difference',side_effect=RuntimeError('main comparisons disabled')):
        for comparison in s['comparisons']:
            grouped=defaultdict(list)
            for r in rows:
                if r['stage']!='PRE' or r['target'] is None:continue
                p=independent.errors(r['prediction']['predictions']['FULL_RBF'],r['target'])
                other=p['factorized_joint_32'] if comparison['comparator']=='MARGINAL_PRODUCT' else independent.errors(r['prediction']['predictions'][comparison['comparator']],r['target'])[comparison['family']]
                grouped[r['spec']['group']].append(p[comparison['family']]-other)
            means=[sum(grouped[g])/len(grouped[g]) for g in range(9)]
            boot=[sum(means[g] for g in draw)/9 for draw in s['bootstrap_indices']]
            ci=[quantile(boot,.025),quantile(boot,.975)]
            io.require(np.allclose(means,comparison['group_means'],atol=2e-12,rtol=2e-12) and np.allclose(ci,comparison['CI95'],atol=2e-12,rtol=2e-12),'independent whole-group comparisons')
            io.require((ci[1]<0)==comparison['upper_strictly_below_zero'],'independent decision gate');fields+=len(means)+len(boot)+2
        io.require(s['component_gate']==('PASSED' if s['all_PRE_panels_have_targets'] and all(c['upper_strictly_below_zero'] for c in s['comparisons']) else 'NOT_QUALIFIED'),'no primary substitution')
        total=dict(executions=0,control_steps=0,all_resets=0,physical_frames=0)
        for cohort in a.COHORTS:
            cases=list(io.rows(path.parent/cohort.lower()/'cases.jsonl.gz'));steps=sum(r['total_steps'] for r in cases)
            expected=dict(executions=len(cases),control_steps=steps,all_resets=51*len(cases),physical_frames=25500*len(cases)+5*steps)
            for key,value in expected.items():io.require(s['costs'][cohort][key]==value,'independent complete costs');total[key]+=value;fields+=1
    result=dict(integrity='PASSED',component_gate=s['component_gate'],scalar_fields=fields,total_actual_costs=total,wall_ns=perf_counter_ns()-start,
        guard=guard,statistics_sha256=io.sha(out/'statistics.json'),main_metrics_and_comparisons_disabled=True,online_LLM_API_calls=0)
    io.write(out/'statistics_audit.json',result);return result
