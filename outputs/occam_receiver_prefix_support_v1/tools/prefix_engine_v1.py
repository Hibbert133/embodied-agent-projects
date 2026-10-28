"""Frozen receiver choices on supported old prefixes, never value estimation."""
from copy import deepcopy
import math
from src.probe.occam_performance_core_v1 import digest,RATES
from src.probe.occam_public_history_v1 import features

TARGETS=('META_ADAPT','META_FROZEN','ERM_ADAPT','ERM_FROZEN')


def require(ok,message):
    if not ok:raise ValueError(message)


def replay(value,target,provider):
    require(target in TARGETS,'one of all four frozen receivers')
    require(type(value) is dict and set(value)=={'schema','task','initial','history','windows'}
        and value['schema']=='OCCAM_PUBLIC_TRAIN_TRAJECTORY_V1','strict public source projection')
    windows=value['windows'];require(type(windows) is list and len(windows)<=31,'actual bounded source windows')
    records=[];matched=updates=0;divergence=None
    for j,window in enumerate(windows):
        require(type(window) is dict and set(window)=={'query','selected_rate','measurement'},'one factual window')
        query=window['query'];features(query,8)
        n=query['completed_steps']
        require(query['task']==value['task'] and query['initial']==value['initial']
            and query['history']==value['history'][:n] and len(query['history'])==n,'strict actual prior history, no future suffix')
        require(type(window['selected_rate']) in (int,float) and window['selected_rate'] in RATES,'legal actual source gain')
        if j:
            prior=windows[j-1]['measurement']
            require(not prior['terminal'] and prior['end_at']==n,'source window order')
        passed=deepcopy(query);before=digest(passed);declared=provider.declare(passed)
        require(digest(passed)==before and declared['public_query_sha256']==before
            and declared['at_calls']==n and declared['evaluation_steps']==query['evaluation_steps'],'unchanged query/declaration')
        index=declared['selected_index']
        require(type(index) is int and 0<=index<4 and declared['selected_rate']==RATES[index],'legal saved receiver choice')
        same=declared['selected_rate']==window['selected_rate']
        record=dict(window=j,query_sha256=before,at_calls=n,source_rate=window['selected_rate'],
            target_rate=declared['selected_rate'],choices_match=same,declaration=deepcopy(declared))
        if not same:
            divergence=j;records.append(record);break
        m=window['measurement']
        require(m['start_at']==n and m['planned_steps']==query['evaluation_steps'] and m['actual_steps']>0
            and m['end_at']==n+m['actual_steps']<=len(value['history']),'same observed window')
        current=deepcopy(value['history'][m['end_at']-1]['after'])
        feedback=provider.feedback(deepcopy(declared),deepcopy(m),current)
        require(type(feedback.get('update_applied')) is bool,'literal actual analysis update flag')
        require(feedback['update_applied']==(target.endswith('_ADAPT') and m['full_window']),'fixed adaptation/short rule')
        record.update(measurement=deepcopy(m),current=current,feedback=deepcopy(feedback))
        records.append(record);matched+=1;updates+=feedback['update_applied']
    return dict(target=target,source_windows=len(windows),declarations=len(records),matching_windows=matched,
        first_divergence_window=divergence,analysis_posterior_updates=updates,
        status='NO_RECEIVER_DECISION' if not windows else 'FIRST_RATE_DIVERGENCE' if divergence is not None else 'ALL_OBSERVED_RATE_CHOICES_MATCH',
        matching_fraction=matched/len(windows) if windows else None,
        source_windows_not_used_as_feedback=len(windows)-matched,
        target_task_loss=None,target_task_success=None,independent_deployment=False,
        target_was_trained_on_this_source=True),records


def summarize(rows):
    groups=[]
    for group in sorted({r['spec']['group'] for r in rows}):
        subset=[r for r in rows if r['spec']['group']==group]
        available=[r['matching_fraction'] for r in subset if r['matching_fraction'] is not None]
        groups.append(dict(group=group,source_cases=len(subset),available_cases=len(available),
            mean_matching_fraction=math.fsum(available)/len(available) if available else None))
    means=[g['mean_matching_fraction'] for g in groups if g['mean_matching_fraction'] is not None]
    return dict(analyses=len(rows),source_nonempty=sum(r['source_windows']>0 for r in rows),
        no_receiver_decision=sum(r['source_windows']==0 for r in rows),
        all_observed_rate_choices_match=sum(r['status']=='ALL_OBSERVED_RATE_CHOICES_MATCH' for r in rows),
        first_rate_divergence=sum(r['status']=='FIRST_RATE_DIVERGENCE' for r in rows),
        declarations=sum(r['declarations'] for r in rows),matching_windows=sum(r['matching_windows'] for r in rows),
        analysis_posterior_updates=sum(r['analysis_posterior_updates'] for r in rows),groups=groups,
        equal_group_matching_fraction=math.fsum(means)/len(means) if means else None,available_groups=len(means))
