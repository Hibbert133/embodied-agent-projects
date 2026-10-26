"""Read-only checks of all reported summaries and known semantic controls.

This supplements, and does not change, the frozen primary comparisons/models.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,math,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_io_v1 as a
from src.analysis import correction_scope_independent_v1 as literal
from src.analysis.release_learning_guard_v1 import read_only
io=a.io


def close(x,y):io.require(math.isclose(x,y,abs_tol=2e-12,rel_tol=2e-10),'reported number mismatch')
def quantile(values,p):
    v=sorted(values);i=(len(v)-1)*p;n=int(i);f=i-n
    return v[n]*(1-f)+v[min(n+1,len(v)-1)]*f


def semantic_controls(manifest,cohort):
    m=a.checked(manifest);folder=Path(manifest).parent/cohort.lower();audit=io.read(folder/'audit.json');io.require(audit['integrity']=='PASSED','main record audit')
    start=perf_counter_ns();guard={};unit=None;canonical={};pairs=changed_post=post_count=aliases=0;reference=None
    with read_only(guard):
        for r in io.rows(folder/'examples.jsonl.gz'):
            spec=r['spec'];key=(spec['group'],spec['task'])
            if key!=unit:unit=key;canonical={}
            slot=(r['stage'],spec['acquisition_action'],spec['time_constant_s'])
            if spec['context']=='UNCHANGED':canonical[slot]=r
            else:
                old=canonical[slot]
                if r['stage']=='PRE':
                    io.require(io.digest(old['view'])==io.digest(r['view']),'pre-entry sees private condition or unmatched history')
                    io.require(io.digest(old['prediction'])==io.digest(r['prediction']),'pre-entry predictions differ for identical public input');pairs+=1
                elif spec['acquisition_action']=='CONTINUE':
                    io.require(io.digest(old['view'])==io.digest(r['view']),'zero-step continuation magically sees the private change')
                else:post_count+=1;changed_post+=int(io.digest(old['view'])!=io.digest(r['view']))
        # Same0.5 controller: VALIDATE8 is ordinary task continuation. Phase is
        # explicitly a logical label, removed along with the known wall timer.
        if cohort!='NATIVE':
            unit=None
            fields=('logical_step','command','raw_policy','executed_action_oracle','after','reward','info','simulation_time_before','simulation_time_after','noise_cursor_after')
            for key,it in groupby(io.rows(folder/'events.jsonl.gz'),a.case_key):
                spec=dict(zip(a.KEYS,key));u=a.unit_key(spec)
                if u!=unit:unit=u;reference=None
                relevant=spec['time_constant_s']==.5 and spec['acquisition_action'] in ('CONTINUE','VALIDATE8')
                digest=hashlib.sha256();n=0
                for e in it:
                    if relevant and e['event']=='STEP_COMPLETE':
                        v=deepcopy({k:e[k] for k in fields})
                        if isinstance(v['info'].get('episode'),dict):v['info']['episode'].pop('t',None)
                        digest.update(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode());n+=1
                if relevant:
                    signature=(n,digest.hexdigest())
                    if spec['acquisition_action']=='CONTINUE':reference=signature
                    else:io.require(reference==signature,'same0.5 logical programs have different real trajectories');aliases+=1
    out=Path(manifest).parent/'supplemental_audit_v1';out.mkdir(exist_ok=True)
    result=dict(integrity='PASSED',cohort=cohort,pre_condition_pairs=pairs,
        post_acquisition_condition_pairs=post_count,post_input_changed_pairs=changed_post,
        complete_noop_physical_pairs=aliases,physical_projection_omissions=['logical phase','info.episode.t wall duration','host references/timers/whole-run ledger'],
        guard=guard,wall_ns=perf_counter_ns()-start,new_physics=0,new_fits=0,new_policy_queries=0,online_LLM_API_calls=0,
        post_hoc_additional_integrity_only=True,source_git_commit=m['source_git_commit'],script_sha256=io.sha(__file__))
    io.write(out/(cohort.lower()+'_semantic_controls.json'),result);return result


def compact_errors(folder):
    records=[]
    for r in io.rows(folder/'examples.jsonl.gz'):
        if r['target'] is None:continue
        records.append(dict(spec=r['spec'],stage=r['stage'],errors={kind:literal.errors(p,r['target']) for kind,p in r['prediction']['predictions'].items()}))
    return records


def reported_summaries(manifest):
    a.checked(manifest);base=Path(manifest).parent;s=io.read(base/'results/statistics.json');cal=io.read(base/'learning/calibration.json')
    guard={};start=perf_counter_ns();checked=0
    with read_only(guard):
        calrows=compact_errors(base/'cal');rows=compact_errors(base/'test')
        draws=s['bootstrap_indices'];io.require(len(draws)==10000 and s['bootstrap_replicates']==10000,'registered bootstrap count')
        for draw in draws:
            io.require(len(draw)==9 and all(type(g) is int and 0<=g<9 for g in draw) and sorted(g%3 for g in draw)==[0,0,0,1,1,1,2,2,2],'whole groups with fixed boundary strata')
        rng=np.random.default_rng(202610263);expected_draws=np.concatenate([rng.choice([b,b+3,b+6],size=(10000,3)) for b in range(3)],axis=1).tolist()
        io.require(draws==expected_draws,'registered deterministic bootstrap seed')
        for comparison in s['comparisons']:
            close(comparison['mean'],sum(comparison['group_means'])/9);checked+=1
            expected_counts=[sum(r['stage']=='PRE' and r['spec']['group']==g for r in rows) for g in range(9)]
            io.require(comparison['group_counts']==expected_counts,'primary group denominators');checked+=9
        for stage,models in cal['radii'].items():
            for kind,families in models.items():
                for family,radius in families.items():
                    values=[math.sqrt(r['errors'][kind][family]) for r in calrows if r['stage']==stage]
                    close(radius,quantile(values,.9));checked+=1
        for metric in s['metrics']:
            groups=defaultdict(list);coverage=defaultdict(list)
            for r in rows:
                if r['stage']!=metric['stage']:continue
                g=r['spec']['group'];v=r['errors'][metric['kind']][metric['family']]
                groups[g].append(v);coverage[g].append(float(math.sqrt(v)<=metric['radius']))
            close(metric['group_mean_MSE'],sum(sum(v)/len(v) for v in groups.values())/len(groups))
            close(metric['empirical_coverage'],sum(sum(v)/len(v) for v in coverage.values())/len(coverage))
            io.require(metric['factual_rows']==sum(map(len,groups.values())),'metric denominator');checked+=3
        allrows=list(io.rows(base/'test/examples.jsonl.gz'));availability=Counter(r['stage']+'/'+(r['missing_reason'] or 'FACTUAL_TARGET') for r in allrows)
        io.require(s['availability']==dict(availability),'all availability counts')
        for panel in s['panels']:
            selected=[r for r in allrows if r['stage']==panel['stage'] and r['spec']['task']==panel['task'] and r['spec']['context']==panel['context'] and r['spec']['planned_boundary']==panel['boundary']]
            io.require(panel['allocated']==len(selected) and panel['targets']==sum(r['target'] is not None for r in selected),'full panel denominator')
            io.require(panel['missing']==dict(Counter(r['missing_reason'] for r in selected if r['target'] is None)),'panel missing reasons');checked+=3
        io.require(s['all_PRE_panels_have_targets']==all(p['targets']>0 for p in s['panels'] if p['stage']=='PRE'),'independent coverage gate')
        cases=list(io.rows(base/'test/cases.jsonl.gz'))
        for result in s['complete_factual_program_results']:
            selected=[r for r in cases if r['acquisition_action']==result['action'] and r['time_constant_s']==result['rate']]
            io.require(result['executions']==len(selected) and result['success']==sum(r['success'] for r in selected),'task outcome denominator')
            close(result['mean_deadline_loss'],sum(r['deadline_loss'] for r in selected)/len(selected));checked+=3
        for result in s['fixed_rate_paired_harm_descriptive']:
            keep={a.unit_key(r):r for r in cases if r['acquisition_action']==result['action'] and r['time_constant_s']==.5}
            selected=[r for r in cases if r['acquisition_action']==result['action'] and r['time_constant_s']==result['rate']]
            differences=[r['deadline_loss']-keep[a.unit_key(r)]['deadline_loss'] for r in selected]
            expected=dict(denominator=len(selected),harm=sum(d>0 for d in differences),help=sum(d<0 for d in differences),ties=sum(d==0 for d in differences),
                success_to_failure=sum(not r['success'] and keep[a.unit_key(r)]['success'] for r in selected),failure_to_success=sum(r['success'] and not keep[a.unit_key(r)]['success'] for r in selected))
            for k,v in expected.items():io.require(result[k]==v,'paired factual update result '+k);checked+=1
            close(result['mean_difference'],sum(differences)/len(differences));checked+=1
        for cohort in a.COHORTS:
            source=io.read(base/cohort.lower()/'summary.json');record=io.read(base/cohort.lower()/'audit.json')
            close(s['costs'][cohort]['policy_queries'],sum(r['policy_queries'] for r in source['rows']))
            close(s['costs'][cohort]['independent_policy_replay_queries'],record['replay_fixed_policy_queries'])
            io.require(s['costs'][cohort]['collection_wall_ns']==source['wall_ns'] and s['costs'][cohort]['audit_wall_ns']==record['wall_ns'],'reported elapsed time sources');checked+=4
    result=dict(integrity='PASSED',reported_fields=checked,guard=guard,wall_ns=perf_counter_ns()-start,
        new_physics=0,new_fits=0,new_policy_queries=0,online_LLM_API_calls=0,post_hoc_additional_integrity_only=True,
        statistics_sha256=io.sha(base/'results/statistics.json'),calibration_sha256=io.sha(base/'learning/calibration.json'),script_sha256=io.sha(__file__))
    io.write(base/'results/reported_summaries_audit.json',result);return result


if __name__=='__main__':
    manifest=Path(sys.argv[1]);kind=sys.argv[2]
    result=reported_summaries(manifest) if kind=='SUMMARIES' else semantic_controls(manifest,kind)
    print({k:v for k,v in result.items() if k in ('integrity','cohort','pre_condition_pairs','complete_noop_physical_pairs','reported_fields')})
