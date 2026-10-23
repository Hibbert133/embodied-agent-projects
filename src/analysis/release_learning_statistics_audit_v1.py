"""Separate scalar/Fraction reconstruction; main statistics functions disabled."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
from time import perf_counter_ns
import math
import numpy as np
from src.analysis import release_learning_io_v1 as a
io=a.io


def q(values,p):
    s=sorted(values);position=p*(len(s)-1);lo=position.numerator//position.denominator;weight=position-lo
    return Fraction(s[lo])+(Fraction(s[min(lo+1,len(s)-1)])-s[lo])*weight


def independent(rows,cohort,draws):
    groups=a.GROUPS[cohort];programs=a.programs(cohort);n=6*groups
    lookup={tuple(c[k] for k in ('group','task','context','program')):c for c in rows}
    io.require(len(lookup)==len(rows)==n*len(programs),'entire unique own-history population')
    totals={p:sum(c['deadline_loss'] for c in rows if c['program']==p) for p in programs};out={};coverage=Counter()
    for p in programs:
        group_loss=[0]*groups;group_success=[0]*groups;counts=Counter()
        if p=='LEARNED_EFFECT':continue
        for g in range(groups):
            for task in ('push-v3','reach-v3','door-open-v3'):
                for context in ('UNCHANGED','CHANGED'):
                    x=lookup[(g,task,context,'LEARNED_EFFECT')];y=lookup[(g,task,context,p)]
                    d=x['deadline_loss']-y['deadline_loss'];group_loss[g]+=d;group_success[g]+=int(x['success'])-int(y['success'])
                    counts['harmful']+=int(d>0);counts['helpful']+=int(d<0);counts['tied']+=int(d==0)
                    counts['success_to_failure']+=int(y['success'] and not x['success']);counts['failure_to_success']+=int(x['success'] and not y['success'])
        bs=[sum(group_loss[g] for g in row) for row in draws];ss=[sum(group_success[g] for g in row) for row in draws];upper=q(bs,Fraction(159,160))/n
        out[p]=dict(n=n,mean_loss_difference=float(Fraction(sum(group_loss),n)),CI95=[float(q(bs,Fraction(1,40))/n),float(q(bs,Fraction(39,40))/n)],
            one_sided_family_upper=float(upper),upper_exact=dict(numerator=upper.numerator,denominator=upper.denominator),**dict(counts),
            success_difference=float(Fraction(sum(group_success),n)),success_difference_CI95=[float(q(ss,Fraction(1,40))/n),float(q(ss,Fraction(39,40))/n)])
    for x in rows:
        if x['program']!='LEARNED_EFFECT' or x['learning'] is None:continue
        l=x['learning'];r=l['receiver_decision']
        if r is None or not l['saved_return']['record']['steps']:continue
        full=l['release_receipt']['binding']['assigned_exposure'];coverage['actual_nonempty_released']+=int(full);coverage['actual_nonempty_withheld']+=int(not full)
        y=lookup[(x['group'],x['task'],x['context'],'FORCE_MASKED')]['learning']
        io.require(y['saved_return']['record']==l['saved_return']['record'],'same actual acquisition, different supplemental exposure')
        if y['receiver_decision'] is not None:coverage['actual_different_gain_vs_forced_mask']+=int(r['choice']['time_constant_s']!=y['receiver_decision']['choice']['time_constant_s'])
    cover=all(coverage[k]>0 for k in ('actual_nonempty_released','actual_nonempty_withheld','actual_different_gain_vs_forced_mask'))
    no_worse=all(totals['LEARNED_EFFECT']<=v for v in totals.values());dev=cover and no_worse and all(totals['LEARNED_EFFECT']<totals[p] for p in a.PRIMARY)
    qual=cover and no_worse and all(out[p]['upper_exact']['numerator']<0 for p in a.PRIMARY)
    return out,dict(coverage),no_worse,'PASSED' if dev else 'NOT_QUALIFIED',('PASSED' if qual else 'NOT_QUALIFIED') if cohort=='QUAL' else 'NOT_EVALUATED_ON_DEV'


def audit(path,cohort):
    a.checked(path);root=Path(path).parent/cohort.lower();start=perf_counter_ns();r=io.read(root/'statistics.json');draws=io.read(root/'bootstrap_indices.json');groups=a.GROUPS[cohort]
    # Different integer-draw construction, same registered PCG64 stream.
    rng=np.random.default_rng(2026102370);expected=[]
    for _ in range(10000):
        row=[]
        for offset in range(3):
            pool=list(range(offset,groups,3));row.extend(pool[int(i)] for i in rng.integers(0,len(pool),len(pool)))
        expected.append(row)
    io.require(draws==expected,'complete stratified whole-group draw stream')
    rows=list(io.rows(root/'cases.jsonl.gz'));comparisons,coverage,no_worse,dev,qual=independent(rows,cohort,draws)
    io.require(io.digest(comparisons)==io.digest(r['comparisons']),'independent full paired losses, success changes, exact confidence endpoints')
    for key in ('actual_nonempty_released','actual_nonempty_withheld','actual_different_gain_vs_forced_mask'):io.require(coverage.get(key,0)==r['mechanism_coverage'][key],'complete mechanism denominator')
    io.require(no_worse==r['no_worse_mean_than_all_other_controls'] and dev==r['DEV_gate'] and qual==r['QUAL_gate'],'independent preregistered stopping gates')
    for p in a.programs(cohort):
        own=[c for c in rows if c['program']==p];v=r['programs'][p]
        io.require(len(own)==v['n'] and sum(c['success'] for c in own)==v['success'] and sum(c['deadline_loss'] for c in own)==v['loss_sum']
            and float(Fraction(v['loss_sum'],len(own)))==v['mean_cutoff_loss'] and sum(c['total_steps'] for c in own)==v['actual_control_steps'],'entire program result and cost')
    failures=[{k:c[k] for k in (*a.KEYS,'total_steps','deadline_loss','success','stop_reason')} for c in rows if not c['success']]
    io.require(io.digest(failures)==io.digest(r['all_task_failures']),'all complete task failures retained exactly once')
    panels=[]
    for p in a.programs(cohort):
        for task in ('push-v3','reach-v3','door-open-v3'):
            for context in ('UNCHANGED','CHANGED'):
                for boundary in (16,32,64):
                    cell=[c for c in rows if c['program']==p and c['task']==task and c['context']==context and c['planned_boundary']==boundary]
                    panels.append(dict(program=p,task=task,context=context,boundary=boundary,n=len(cell),success=sum(c['success'] for c in cell),mean_cutoff_loss=sum(c['deadline_loss'] for c in cell)/len(cell)))
    io.require(io.digest(panels)==io.digest(r['panels']),'complete task/condition/boundary panels')
    lookup={tuple(c[k] for k in ('group','task','context','program')):c for c in rows};updates=[];signals=[]
    for c in rows:
        if c['program']!='LEARNED_EFFECT' or c['learning'] is None or c['learning']['receiver_decision'] is None:continue
        l=c['learning'];record=l['saved_return']['record'];action=record['action'];rate=l['receiver_decision']['choice']['time_constant_s']
        if rate!=.5:
            p={'CONTINUE':'RAW','VALIDATE8':'VALIDATE_NO_UPDATE','MOVE_MEASURE':'MOVE_NO_UPDATE'}[action];other=lookup[(c['group'],c['task'],c['context'],p)]
            io.require(other['learning']['saved_return']['record']==record,'actual same-action fixed-rate comparison')
            updates.append(dict(group=c['group'],task=c['task'],context=c['context'],action=action,rate=rate,comparator=p,
                loss_difference=c['deadline_loss']-other['deadline_loss'],candidate_success=c['success'],comparator_success=other['success']))
        if record['steps']:
            exposed=l['release_receipt']['binding']['assigned_exposure'];p='FORCE_MASKED' if exposed else 'RELEASE_ALWAYS';other=lookup[(c['group'],c['task'],c['context'],p)]
            io.require(other['learning']['saved_return']['record']==record,'actual exposure comparison')
            signals.append(dict(group=c['group'],task=c['task'],context=c['context'],action=action,exposed=exposed,comparator=p,
                loss_difference=c['deadline_loss']-other['deadline_loss'],candidate_success=c['success'],comparator_success=other['success']))
    u=r['task_adverse_gain_updates'];s=r['supplemental_exposure_pairs']
    io.require(io.digest(updates)==io.digest(u['cases']) and io.digest(signals)==io.digest(s['cases']),'all adverse-update and exposure/opportunity pairs')
    io.require(u['actual_gain_changes']==len(updates) and u['assigned_population']==groups*6 and u['harmful']==sum(v['loss_difference']>0 for v in updates)
        and u['helpful']==sum(v['loss_difference']<0 for v in updates) and u['tied']==sum(v['loss_difference']==0 for v in updates)
        and u['positive_loss_sum']==sum(max(0,v['loss_difference']) for v in updates),'complete gain-change severity denominators')
    io.require(s['assigned_population']==groups*6 and s['harmful_actual_exposures']==sum(v['exposed'] and v['loss_difference']>0 for v in signals)
        and s['missed_opportunities_from_withholding']==sum(not v['exposed'] and v['loss_difference']>0 for v in signals),'complete information harm/opportunity counters')
    result=dict(integrity='PASSED',cohort=cohort,DEV_gate=dev,QUAL_gate=qual,statistics_sha256=io.sha(root/'statistics.json'),
        source_cases_sha256=io.sha(root/'cases.jsonl.gz'),bootstrap_indices_sha256=io.sha(root/'bootstrap_indices.json'),
        whole_groups=groups,paired_comparisons=len(comparisons),new_model_fits=0,new_environment_steps=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
    io.write(root/'statistics_audit.json',result);return result
