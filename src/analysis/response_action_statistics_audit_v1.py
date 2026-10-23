"""Independent matrix extraction and shared whole-group resampling, no estimator calls."""
from pathlib import Path
from itertools import combinations,product
import numpy as np
from src.analysis import response_action_io_v1 as allocation
io=allocation.io


def independent_summary(cases,cohort,weight,primary):
    n=6 if cohort=='DEV' else 9;specs=allocation.population(cohort,weight)
    io.require(len(cases)==len(specs),'complete allocation')
    for c,s in zip(cases,specs):
        for k,v in s.items():io.require(c[k]==v,'case/order mismatch')
        io.require(c['completed'] and c['error'] is None and c['close_error'] is None and c['deadline_loss']==(c['total_steps'] if c['success'] else 500),'incomplete/mischarged outcome')
    ids=list(dict.fromkeys(allocation.spec_id(r) for r in cases));units=list(dict.fromkeys(r['unit_id'] for r in cases))
    table={(allocation.spec_id(c),c['unit_id']):c for c in cases}
    losses=np.array([[table[pid,u]['deadline_loss'] for u in units] for pid in ids],float)
    successes=np.array([[table[pid,u]['success'] for u in units] for pid in ids],bool)
    groups={g:[i for i,u in enumerate(units) if table[ids[0],u]['group']==g] for g in range(n)}
    gm=np.column_stack([losses[:,groups[g]].mean(axis=1) for g in range(n)])
    rng=np.random.default_rng(202610400 if cohort=='DEV' else 202610401);draws=[]
    for layer in range(3):
        indices=np.arange(layer,n,3);draws.append(indices[rng.integers(0,len(indices),(10000,len(indices)))])
    index=np.column_stack(draws)
    def interval(d):
        vals=d[index].mean(axis=1)
        return {'mean':float(d.mean()),'lower95':float(np.quantile(vals,.025)),'upper95':float(np.quantile(vals,.975)),
            'groups':n,'replicates':10000,'seed':202610400 if cohort=='DEV' else 202610401,'unit':'WHOLE_GROUP_STRATIFIED_BY_BOUNDARY',
            'multiplicity':'All four fixed primary upper bounds must be negative; secondary intervals unadjusted descriptive'}
    rows=[]
    for i,pid in enumerate(ids):
        values=[table[pid,u] for u in units];c=values[0]
        rows.append({'program':pid,'style':c['style'],'time_constant_s':c['time_constant_s'],'regularization_weight':c['regularization_weight'],
            'n':len(values),'successes':int(successes[i].sum()),'loss_sum':int(losses[i].sum()),'mean_deadline_loss':float(gm[i].mean()),
            'group_mean_deadline_loss':{g:float(gm[i,g]) for g in range(n)},
            **{field:sum(v[source] for v in values) for field,source in (('actual_control_steps','total_steps'),('rank_steps','rank_steps'),('task_pi_steps','pi_steps'),('movement_steps','movement_steps'),('response_model_forward_evaluations','response_model_forward_evaluations'),('kinematic_proxy_evaluations','kinematic_proxy_evaluations'))},
            'all_failure_ids':[v['case_id'] for v in values if not v['success']]})
    pairs=[]
    for i,j in combinations(range(len(ids)),2):
        d=losses[i]-losses[j]
        pairs.append({'left':ids[i],'right':ids[j],'loss_difference':interval(gm[i]-gm[j]),'paired_denominator':len(units),
            'success_difference':int(successes[i].sum()-successes[j].sum()),'left_adverse_vs_right':int((d>0).sum()),
            'left_helpful_vs_right':int((d<0).sum()),'ties':int((d==0).sum()),
            'right_success_to_left_failure':int((successes[j]&~successes[i]).sum()),'right_failure_to_left_success':int((successes[i]&~successes[j]).sum())})
    cells=[]
    for task,context,pid in product(allocation.GAINS,('UNCHANGED','CHANGED'),ids):
        values=[table[pid,u] for u in units if table[pid,u]['task']==task and table[pid,u]['context']==context]
        cells.append({'task':task,'context':context,'program':pid,'n':len(values),'successes':sum(v['success'] for v in values),
            'mean_deadline_loss':float(np.mean([v['deadline_loss'] for v in values])),'actual_control_steps':sum(v['total_steps'] for v in values)})
    pi=ids.index(primary);controls=allocation.expected_config()['primary_controls'];primary_results={primary+'_MINUS_'+pid:interval(gm[pi]-gm[ids.index(pid)]) for pid in controls}
    passed=cohort=='QUAL' and all(v['upper95']<0 for v in primary_results.values()) and all(gm[pi].mean()<gm[j].mean() for j in range(len(ids)) if j!=pi)
    return {'cohort':cohort,'executions':len(cases),'programs':rows,'primary_program':primary,'primary_comparisons':primary_results,
        'all_paired_secondary_comparisons':pairs,'complete_task_context_cells':cells,'all_failure_case_ids':[c['case_id'] for c in cases if not c['success']],
        'qualification_gate':'PASSED_ENGINEERING_CONTROL_REFERENCE_ONLY' if passed else 'NOT_PASSED' if cohort=='QUAL' else 'DEVELOPMENT_ONLY',
        'new_environment_steps':0,'new_api_calls':0,'new_model_fits':0,'novel_algorithm':False,'safety_guarantee':False}


def compare(actual,expected,path='root'):
    if isinstance(expected,dict):
        io.require(set(actual)==set(expected),'statistic dictionary keys '+path)
        return sum(compare(actual[k],v,path+'/'+str(k)) for k,v in expected.items())
    if isinstance(expected,list):
        io.require(len(actual)==len(expected),'statistic length '+path)
        return sum(compare(a,b,path) for a,b in zip(actual,expected))
    if isinstance(expected,(int,float,np.number)) and not isinstance(expected,(bool,np.bool_)):
        io.require(np.isclose(actual,expected,rtol=1e-11,atol=1e-12),'statistic numeric mismatch '+path)
    else:io.require(actual==expected,'statistic identifier mismatch '+path)
    return 1


def audit(path,cohort):
    path=Path(path).resolve();m=allocation.load_manifest(path);folder=path.parent/cohort.lower()
    a=io.read(folder/'audit.json');io.require(a['integrity']=='PASSED' and a['completion_sha256']==io.sha(folder/'completion.json'),'record audit binding')
    for n,h in io.read(folder/'completion.json')['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'source artifact changed')
    selection=io.read(path.parent/'selection.json');cases=list(io.rows(folder/'cases.jsonl.gz'))
    expected=independent_summary(cases,cohort,selection['selected_F20_weight'] if cohort=='QUAL' else None,selection['primary_program'])
    target=path.parent/'evaluation'/(cohort.lower()+'.json');actual=io.read(target)
    # JSON round-trip canonicalizes integer group keys without changing numbers.
    import json
    fields=compare({k:actual[k] for k in expected},json.loads(json.dumps(expected,allow_nan=False)))
    if cohort=='DEV':
        candidates=[r for r in expected['programs'] if r['style']=='F20_RANK'];best=min(candidates,key=lambda r:(r['loss_sum'],-r['regularization_weight']))
        io.require(selection['selected_F20_weight']==best['regularization_weight'] and selection['primary_program']==best['program'],'global development lock')
        gate=all(best['loss_sum']<r['loss_sum'] for r in expected['programs'] if r['style']!='F20_RANK')
        io.require(selection['development_gate_passed']==gate,'development entry gate')
    result={'integrity':'PASSED','cohort':cohort,'fields_checked':fields,'statistics_sha256':io.sha(target),
        'case_source_sha256':io.sha(folder/'cases.jsonl.gz'),'selection_sha256':io.sha(path.parent/'selection.json'),
        'auditor_sha256':io.sha(__file__),'new_environment_steps':0,'new_api_calls':0,'new_model_fits':0}
    io.write(path.parent/'evaluation'/('independent_audit_'+cohort.lower()+'.json'),result);return result
