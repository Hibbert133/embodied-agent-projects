"""Complete-population loss selection and four co-primary independent task contrasts."""
from itertools import combinations,product
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import response_action_io_v1 as allocation
io=allocation.io


def bootstrap(values,cohort):
    n=6 if cohort=='DEV' else 9;io.require(set(values)==set(range(n)),'complete independent groups')
    v=np.asarray([values[i] for i in range(n)],float);io.require(np.isfinite(v).all(),'finite group metrics')
    seed=202610400 if cohort=='DEV' else 202610401;r=np.random.default_rng(seed);sample=[]
    for boundary in range(3):
        ids=np.arange(boundary,n,3);sample.append(v[ids[r.integers(0,len(ids),(10000,len(ids)))]] )
    means=np.concatenate(sample,axis=1).mean(axis=1)
    return {'mean':float(v.mean()),'lower95':float(np.quantile(means,.025)),'upper95':float(np.quantile(means,.975)),
        'groups':n,'replicates':10000,'seed':seed,'unit':'WHOLE_GROUP_STRATIFIED_BY_BOUNDARY',
        'multiplicity':'All four fixed primary upper bounds must be negative; secondary intervals unadjusted descriptive'}


def validate_cases(cases,cohort,weight=None):
    specs=allocation.population(cohort,weight);io.require(len(cases)==len(specs),'full allocated population')
    for c,s in zip(cases,specs):
        for k,v in s.items():io.require(c[k]==v,'allocation order/spec drift')
        io.require(c['completed'] and c['error'] is None and c['close_error'] is None,'incomplete case cannot disappear')
        io.require(type(c['success']) is bool and type(c['total_steps']) is int and 0<=c['total_steps']<=500,'actual outcome')
        io.require(c['deadline_loss']==(c['total_steps'] if c['success'] else 500),'cutoff loss and acquisition costs')


def summary_rows(cases,cohort,weight=None):
    validate_cases(cases,cohort,weight);n=6 if cohort=='DEV' else 9;rows=[]
    for p in allocation.programs(cohort,weight):
        pid=allocation.program_id(p.style,p.time_constant_s,p.regularization_weight);actual=[r for r in cases if allocation.spec_id(r)==pid]
        groups={i:float(np.mean([r['deadline_loss'] for r in actual if r['group']==i])) for i in range(n)}
        rows.append({'program':pid,'style':p.style,'time_constant_s':p.time_constant_s,'regularization_weight':p.regularization_weight,
            'n':len(actual),'successes':sum(c['success'] for c in actual),'loss_sum':sum(c['deadline_loss'] for c in actual),
            'mean_deadline_loss':float(np.mean(list(groups.values()))),'group_mean_deadline_loss':groups,
            'actual_control_steps':sum(c['total_steps'] for c in actual),'rank_steps':sum(c['rank_steps'] for c in actual),
            'task_pi_steps':sum(c['pi_steps'] for c in actual),'movement_steps':sum(c['movement_steps'] for c in actual),
            'response_model_forward_evaluations':sum(c['response_model_forward_evaluations'] for c in actual),
            'kinematic_proxy_evaluations':sum(c['kinematic_proxy_evaluations'] for c in actual),
            'all_failure_ids':[c['case_id'] for c in actual if not c['success']]})
    return rows


def choose(cases):
    rows=summary_rows(cases,'DEV');best=min((r for r in rows if r['style']=='F20_RANK'),key=lambda r:(r['loss_sum'],-r['regularization_weight']))
    controls=[r for r in rows if r['style']!='F20_RANK'];passed=all(best['loss_sum']<r['loss_sum'] for r in controls)
    return {'selected_F20_weight':best['regularization_weight'],'primary_program':best['program'],'all_development_programs':rows,
        'development_gate_passed':passed,'development_gate':'PASSED_FOR_LOCKED_QUALIFICATION_ONLY' if passed else 'FAILED_STOP_NO_QUALIFICATION',
        'selection_rule':'Complete full DEV sum cutoff loss; ties largest weight; no task/context selection',
        'new_environment_steps':0,'new_api_calls':0,'new_model_fits':0}


def checked_cohort(path,cohort):
    folder=Path(path).parent/cohort.lower();a=io.read(folder/'audit.json')
    io.require(a['integrity']=='PASSED' and a['completion_sha256']==io.sha(folder/'completion.json') and
        a['auditor_sha256']==io.sha(allocation.ROOT/'src/analysis/response_action_audit_v1.py') and
        a['rank_auditor_sha256']==io.sha(allocation.ROOT/'src/analysis/response_action_rank_audit_v1.py'),'source-bound independent record audit')
    for n,h in io.read(folder/'completion.json')['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'audited original changed')
    return a,list(io.rows(folder/'cases.jsonl.gz'))


def select(path):
    path=Path(path).resolve();m=allocation.load_manifest(path);io.require(not (path.parent/'qual').exists(),'cannot select after QUAL')
    _,cases=checked_cohort(path,'DEV');choice=choose(cases)
    value={**{k:m[k] for k in io.IDENTITY},**choice,'DEV_completion_sha256':io.sha(path.parent/'dev/completion.json'),
        'DEV_audit_sha256':io.sha(path.parent/'dev/audit.json'),'locked_ns':perf_counter_ns(),'statistics_source_sha256':io.sha(__file__)}
    io.write(path.parent/'selection.json',value);return value


def verify_selection(path):
    path=Path(path).resolve();m=allocation.load_manifest(path);v=io.read(path.parent/'selection.json')
    io.require(v['development_gate_passed'],'negative DEV stops QUAL; no new samples or fallback method')
    _,cases=checked_cohort(path,'DEV')
    for k,want in choose(cases).items():io.require(io.digest(v[k])==io.digest(want),'selection lock changed')
    for k in io.IDENTITY:io.require(v[k]==m[k],'selection/run identity')
    io.require(v['DEV_completion_sha256']==io.sha(path.parent/'dev/completion.json') and v['DEV_audit_sha256']==io.sha(path.parent/'dev/audit.json') and v['statistics_source_sha256']==io.sha(__file__),'selection source binding')
    return v


def summarize(cases,cohort,weight=None,primary=None):
    rows=summary_rows(cases,cohort,weight);byid={r['program']:r for r in rows};pairs=[];primary_results={}
    for left,right in combinations(byid,2):
        a,b=byid[left],byid[right];differences={g:a['group_mean_deadline_loss'][g]-b['group_mean_deadline_loss'][g] for g in a['group_mean_deadline_loss']}
        paired={allocation.spec_id(c)+'|'+c['unit_id']:c for c in cases}
        adverse=helpful=tie=success_to_failure=failure_to_success=0
        for c in cases:
            if allocation.spec_id(c)!=left:continue
            other=paired[right+'|'+c['unit_id']];d=c['deadline_loss']-other['deadline_loss']
            adverse+=d>0;helpful+=d<0;tie+=d==0;success_to_failure+=other['success'] and not c['success'];failure_to_success+=c['success'] and not other['success']
        pairs.append({'left':left,'right':right,'loss_difference':bootstrap(differences,cohort),
            'paired_denominator':a['n'],'success_difference':a['successes']-b['successes'],
            'left_adverse_vs_right':int(adverse),'left_helpful_vs_right':int(helpful),'ties':int(tie),
            'right_success_to_left_failure':int(success_to_failure),'right_failure_to_left_success':int(failure_to_success)})
    if primary is not None:
        a=byid[primary]
        for name in allocation.expected_config()['primary_controls']:
            b=byid[name];primary_results[primary+'_MINUS_'+name]=bootstrap({g:a['group_mean_deadline_loss'][g]-b['group_mean_deadline_loss'][g] for g in a['group_mean_deadline_loss']},cohort)
    cells=[]
    for task,context,p in product(allocation.GAINS,('UNCHANGED','CHANGED'),allocation.programs(cohort,weight)):
        pid=allocation.program_id(p.style,p.time_constant_s,p.regularization_weight);actual=[r for r in cases if r['task']==task and r['context']==context and allocation.spec_id(r)==pid]
        cells.append({'task':task,'context':context,'program':pid,'n':len(actual),'successes':sum(r['success'] for r in actual),
            'mean_deadline_loss':float(np.mean([r['deadline_loss'] for r in actual])),'actual_control_steps':sum(r['total_steps'] for r in actual)})
    passed=cohort=='QUAL' and len(primary_results)==4 and all(r['upper95']<0 for r in primary_results.values()) and all(byid[primary]['mean_deadline_loss']<r['mean_deadline_loss'] for r in rows if r['program']!=primary)
    return {'cohort':cohort,'executions':len(cases),'programs':rows,'primary_program':primary,'primary_comparisons':primary_results,
        'all_paired_secondary_comparisons':pairs,'complete_task_context_cells':cells,'all_failure_case_ids':[c['case_id'] for c in cases if not c['success']],
        'qualification_gate':'PASSED_ENGINEERING_CONTROL_REFERENCE_ONLY' if passed else 'NOT_PASSED' if cohort=='QUAL' else 'DEVELOPMENT_ONLY',
        'new_environment_steps':0,'new_api_calls':0,'new_model_fits':0,'novel_algorithm':False,'safety_guarantee':False}


def evaluate(path,cohort):
    path=Path(path).resolve();m=allocation.load_manifest(path);io.require(cohort in ('DEV','QUAL'),'scientific evaluation phase')
    _,cases=checked_cohort(path,cohort);v=io.read(path.parent/'selection.json')
    if cohort=='QUAL':verify_selection(path)
    value={**{k:m[k] for k in io.IDENTITY},**summarize(cases,cohort,v['selected_F20_weight'] if cohort=='QUAL' else None,v['primary_program']),
        'audit_sha256':io.sha(path.parent/cohort.lower()/'audit.json'),'selection_sha256':io.sha(path.parent/'selection.json'),'statistics_source_sha256':io.sha(__file__)}
    folder=path.parent/'evaluation';folder.mkdir(exist_ok=True);io.write(folder/(cohort.lower()+'.json'),value);return value
