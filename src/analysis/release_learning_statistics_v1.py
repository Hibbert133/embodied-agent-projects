"""Full-population cutoff loss and whole-group paired sampling; never step IID."""
from fractions import Fraction
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import release_learning_io_v1 as a
io=a.io


def quantile(values,p):
    values=sorted(values);at=p*(len(values)-1);i=at.numerator//at.denominator;f=at-i
    return Fraction(values[i])*(1-f)+Fraction(values[min(i+1,len(values)-1)])*f


def sampling(groups):
    rng=np.random.default_rng(2026102370);strata=[[g for g in range(groups) if g%3==j] for j in range(3)]
    return np.asarray([np.concatenate([rng.choice(s,len(s),replace=True) for s in strata]).tolist() for _ in range(10000)],int)


def compute(rows,cohort,indices):
    io.require(cohort in ('DEV','QUAL'),'own-history comparison only');groups=a.GROUPS[cohort];programs=a.programs(cohort)
    lookup={(r['group'],r['task'],r['context'],r['program']):r for r in rows}
    io.require(len(lookup)==len(rows)==groups*6*len(programs),'complete unique registered population')
    for s in a.population(cohort):
        key=tuple(s[k] for k in ('group','task','context','program'));r=lookup[key]
        for k,v in s.items():io.require(r[k]==v,'registered own-history allocation')
        io.require(type(r['deadline_loss']) is int and r['deadline_loss']==(r['total_steps'] if r['success'] else 500),'whole actual cutoff loss')
    io.require(indices.shape==(10000,groups) and np.all((0<=indices)&(indices<groups)),'whole independent group indices')
    totals={p:sum(r['deadline_loss'] for r in rows if r['program']==p) for p in programs};n=groups*6
    result={p:dict(success=sum(r['success'] for r in rows if r['program']==p),n=n,loss_sum=totals[p],mean_cutoff_loss=totals[p]/n,
        actual_control_steps=sum(r['total_steps'] for r in rows if r['program']==p)) for p in programs}
    comparisons={};paired=[]
    for p in programs:
        if p=='LEARNED_EFFECT':continue
        diffs=[];success_diffs=[];harm=helped=ties=sto_f=fto_s=0
        for g in range(groups):
            d=sd=0
            for t in io.TASKS:
                for c in ('UNCHANGED','CHANGED'):
                    x=lookup[(g,t,c,'LEARNED_EFFECT')];y=lookup[(g,t,c,p)];delta=x['deadline_loss']-y['deadline_loss'];d+=delta;sd+=int(x['success'])-int(y['success'])
                    harm+=int(delta>0);helped+=int(delta<0);ties+=int(delta==0);sto_f+=int(y['success'] and not x['success']);fto_s+=int(x['success'] and not y['success'])
                    paired.append(dict(group=g,task=t,context=c,comparator=p,loss_difference=delta,candidate_success=x['success'],comparator_success=y['success']))
            diffs.append(d);success_diffs.append(sd)
        boot=np.asarray(diffs,np.int64)[indices].sum(1).tolist();sboot=np.asarray(success_diffs,np.int64)[indices].sum(1).tolist()
        low=quantile(boot,Fraction(1,40))/n;high=quantile(boot,Fraction(39,40))/n;upper=quantile(boot,Fraction(159,160))/n
        comparisons[p]=dict(n=n,mean_loss_difference=sum(diffs)/n,CI95=[float(low),float(high)],one_sided_family_upper=float(upper),
            upper_exact=dict(numerator=upper.numerator,denominator=upper.denominator),harmful=harm,helpful=helped,tied=ties,
            success_to_failure=sto_f,failure_to_success=fto_s,success_difference=sum(success_diffs)/n,
            success_difference_CI95=[float(quantile(sboot,Fraction(1,40))/n),float(quantile(sboot,Fraction(39,40))/n)])
    released=withheld=different=0
    for r in rows:
        if r['program']!='LEARNED_EFFECT' or r['learning'] is None:continue
        l=r['learning'];d=l['receiver_decision']
        if d is None or not l['saved_return']['record']['steps']:continue
        exposed=l['release_receipt']['binding']['assigned_exposure'];released+=int(exposed);withheld+=int(not exposed)
        y=lookup[(r['group'],r['task'],r['context'],'FORCE_MASKED')]['learning']
        io.require(y is not None and y['saved_return']['record']==l['saved_return']['record'],'same-acquisition actual forced-mask comparator')
        if y['receiver_decision'] is not None:different+=int(d['choice']['time_constant_s']!=y['receiver_decision']['choice']['time_constant_s'])
    coverage=bool(released and withheld and different)
    update_pairs=[];information_pairs=[]
    for x in rows:
        if x['program']!='LEARNED_EFFECT' or x['learning'] is None or x['learning']['receiver_decision'] is None:continue
        l=x['learning'];record=l['saved_return']['record'];action=record['action'];rate=l['receiver_decision']['choice']['time_constant_s']
        if rate!=.5:
            baseline={'CONTINUE':'RAW','VALIDATE8':'VALIDATE_NO_UPDATE','MOVE_MEASURE':'MOVE_NO_UPDATE'}[action]
            y=lookup[(x['group'],x['task'],x['context'],baseline)]
            io.require(y['learning'] is not None and y['learning']['saved_return']['record']==record,'actual same-acquisition fixed-rate comparator')
            update_pairs.append(dict(group=x['group'],task=x['task'],context=x['context'],action=action,rate=rate,
                comparator=baseline,loss_difference=x['deadline_loss']-y['deadline_loss'],candidate_success=x['success'],comparator_success=y['success']))
        if record['steps']:
            exposed=l['release_receipt']['binding']['assigned_exposure'];baseline='FORCE_MASKED' if exposed else 'RELEASE_ALWAYS'
            y=lookup[(x['group'],x['task'],x['context'],baseline)]
            io.require(y['learning'] is not None and y['learning']['saved_return']['record']==record,'actual same-acquisition exposure counterpart')
            information_pairs.append(dict(group=x['group'],task=x['task'],context=x['context'],action=action,exposed=exposed,
                comparator=baseline,loss_difference=x['deadline_loss']-y['deadline_loss'],candidate_success=x['success'],comparator_success=y['success']))
    no_worse=all(totals['LEARNED_EFFECT']<=totals[p] for p in programs)
    dev=coverage and no_worse and all(totals['LEARNED_EFFECT']<totals[p] for p in a.PRIMARY)
    qual=coverage and no_worse and all(comparisons[p]['upper_exact']['numerator']<0 for p in a.PRIMARY)
    panels=[]
    for p in programs:
        for task in io.TASKS:
            for c in ('UNCHANGED','CHANGED'):
                for boundary in (16,32,64):
                    r=[s for s in rows if s['program']==p and s['task']==task and s['context']==c and s['planned_boundary']==boundary]
                    panels.append(dict(program=p,task=task,context=c,boundary=boundary,n=len(r),success=sum(s['success'] for s in r),mean_cutoff_loss=sum(s['deadline_loss'] for s in r)/len(r)))
    return dict(schema='RELEASE_LEARNING_WHOLE_GROUP_STATISTICS_V1',cohort=cohort,groups=groups,units=n,programs=result,comparisons=comparisons,
        primary_comparators=list(a.PRIMARY),mechanism_coverage=dict(actual_nonempty_released= released,actual_nonempty_withheld=withheld,actual_different_gain_vs_forced_mask=different),
        task_adverse_gain_updates=dict(assigned_population=n,actual_gain_changes=len(update_pairs),harmful=sum(r['loss_difference']>0 for r in update_pairs),
            helpful=sum(r['loss_difference']<0 for r in update_pairs),tied=sum(r['loss_difference']==0 for r in update_pairs),
            positive_loss_sum=sum(max(0,r['loss_difference']) for r in update_pairs),success_to_failure=sum(r['comparator_success'] and not r['candidate_success'] for r in update_pairs),cases=update_pairs),
        supplemental_exposure_pairs=dict(assigned_population=n,cases=information_pairs,
            harmful_actual_exposures=sum(r['exposed'] and r['loss_difference']>0 for r in information_pairs),
            missed_opportunities_from_withholding=sum(not r['exposed'] and r['loss_difference']>0 for r in information_pairs),
            interpretation='Post-hoc paired actual full-task outcomes; not online labels or a numerical-parameter/physical-model qualification'),
        no_worse_mean_than_all_other_controls=no_worse,DEV_gate='PASSED' if dev else 'NOT_QUALIFIED',QUAL_gate=('PASSED' if qual else 'NOT_QUALIFIED') if cohort=='QUAL' else 'NOT_EVALUATED_ON_DEV',
        panels=panels,paired_cases=paired,all_task_failures=[{k:r[k] for k in (*a.KEYS,'total_steps','deadline_loss','success','stop_reason')} for r in rows if not r['success']],
        bootstrap='stratified entire groups,10000 draws, nominal one-sided Bonferroni upper159/160 for eight primaries; approximate statistical interval, no safety guarantee',
        full_CCF_A_objective_complete=False)


def run(path,cohort):
    a.checked(path);root=Path(path).parent/cohort.lower();io.require(io.read(root/'audit.json')['integrity']=='PASSED','complete record audit before statistics')
    start=perf_counter_ns();indices=sampling(a.GROUPS[cohort]);io.write(root/'bootstrap_indices.json',indices.tolist())
    result=compute(list(io.rows(root/'cases.jsonl.gz')),cohort,indices);io.write(root/'statistics.json',result)
    io.write(root/'statistics_receipt.json',dict(integrity='PASSED',source_cases_sha256=io.sha(root/'cases.jsonl.gz'),
        statistics_sha256=io.sha(root/'statistics.json'),indices_sha256=io.sha(root/'bootstrap_indices.json'),new_model_fits=0,
        new_environment_steps=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start));return result
