"""Independent dense/scalar reader. No main provider or replay calls."""
from copy import deepcopy
import math
import numpy as np
from src.analysis.occam_qualification_math_audit_v1 import literal_bases
from src.probe.occam_performance_core_v1 import digest,RATES


def require(value,message):
    if not value:raise ValueError(message)


def near(a,b,message):
    x,y=np.asarray(a,float),np.asarray(b,float)
    require(x.shape==y.shape and np.isfinite(x).all() and np.isfinite(y).all()
        and np.allclose(x,y,rtol=1e-10,atol=1e-9),message)


def verify_replay(value,target,row,records,bank):
    p=bank['prior'];mean=np.array(p['mean'],float);P=np.array(p['covariance'],float)
    Q=np.array(p['process_covariance'],float);R=np.array(p['measurement_covariance'],float)
    serialized_mean=deepcopy(p['mean']);serialized_P=deepcopy(p['covariance'])
    matched=updates=attempts=0;divergence=None
    common={'window','query_sha256','at_calls','source_rate','target_rate','choices_match','declaration'}
    for j,source in enumerate(value['windows']):
        require(attempts<len(records),'missing declaration');record=records[attempts];attempts+=1
        q=source['query'];d=record['declaration'];phi=literal_bases(bank,q)
        expected_means=[float(phi[i,0]@mean) for i in range(4)]
        selected=int(np.argmin(expected_means));actual=source['selected_rate']
        require(record['window']==j and record['at_calls']==q['completed_steps'] and record['query_sha256']==digest(q),'literal query reference')
        require(q['history']==value['history'][:q['completed_steps']] and len(q['history'])==q['completed_steps'],'literal strict-past input')
        require(d['selected_index']==selected and d['selected_rate']==RATES[selected]==record['target_rate']
            and record['source_rate']==actual and d['version']==updates and d['beta']==0. and d['reward_weights']==[-1.],'independent choice/version')
        require(d['public_query_sha256']==digest(q) and d['at_calls']==q['completed_steps']
            and d['evaluation_steps']==q['evaluation_steps'],'independent timing/digest')
        near(d['bases'],phi,'independent network bases')
        require(d['state_sha256']==digest([serialized_mean,serialized_P,p['process_covariance'],p['measurement_covariance']]),'serialized posterior identity')
        expected_d={k:v for k,v in d.items() if k!='declaration_sha256'}
        require(d['declaration_sha256']==digest(expected_d),'durable model declaration')
        for i,pred in enumerate(d['predictions']):
            h=phi[i,0];variance=float(h@P@h)
            near(pred['mean'],[expected_means[i]],'literal mean')
            near(pred['latent_covariance'],[[variance]],'literal latent covariance')
            near(pred['observation_covariance'],[[variance+R[0,0]]],'literal observation covariance')
            near(d['scores'][i],-expected_means[i],'literal beta0 score')
        same=RATES[selected]==actual;require(record['choices_match']==same,'source versus target choice')
        if not same:
            require(set(record)==common,'no mismatched-action feedback or future state');divergence=j;break
        require(set(record)==common|{'measurement','current','feedback'},'only factual matched feedback')
        m=source['measurement'];f=record['feedback'];current=value['history'][m['end_at']-1]['after']
        require(record['measurement']==m and record['current']==current,'matched factual label/state')
        actual_update=target.endswith('_ADAPT') and m['full_window']
        require(f['adaptation_enabled']==target.endswith('_ADAPT') and f['update_applied']==actual_update
            and f['model_state_before_sha256']==d['state_sha256'],'fixed update factor')
        if actual_update:
            h=phi[selected,0];prior=P+Q;variance=float(h@prior@h+R[0,0]);gain=(prior@h)/variance
            innovation=float(m['cost']-h@mean);mean=mean+gain*innovation
            I=np.eye(len(mean))-np.outer(gain,h);P=I@prior@I.T+np.outer(gain,gain)*R[0,0];P=(P+P.T)*.5
            v=f['result']['posterior'];near(v['mean'],mean,'scalar update mean');near(v['covariance'],P,'scalar posterior')
            near(v['gain'],gain[:,None],'scalar gain');near(v['innovation'],[innovation],'literal innovation')
            near(v['innovation_covariance'],[[variance]],'one Q per complete matched window')
            serialized_mean=deepcopy(v['mean']);serialized_P=deepcopy(v['covariance']);updates+=1
        else:
            require(f['model_state_before_sha256']==f['model_state_after_sha256'] and 'posterior' not in f['result'],'no short/frozen update')
        require(f['version']==updates and f['completed_steps']==m['end_at']
            and f['model_state_after_sha256']==digest([serialized_mean,serialized_P,p['process_covariance'],p['measurement_covariance']]),'saved next posterior')
        matched+=1
    require(attempts==len(records),'no declarations after first divergence')
    n=len(value['windows']);expected=dict(target=target,source_windows=n,declarations=attempts,matching_windows=matched,
        first_divergence_window=divergence,analysis_posterior_updates=updates,
        status='NO_RECEIVER_DECISION' if not n else 'FIRST_RATE_DIVERGENCE' if divergence is not None else 'ALL_OBSERVED_RATE_CHOICES_MATCH',
        matching_fraction=matched/n if n else None,source_windows_not_used_as_feedback=n-matched,
        target_task_loss=None,target_task_success=None,independent_deployment=False,target_was_trained_on_this_source=True)
    for key,val in expected.items():require(row[key]==val,'all analysis fields '+key)
    return dict(declarations=attempts,posterior_updates=updates,candidate_predictions=4*attempts)


def verify_summary(rows,saved):
    expected=dict(analyses=len(rows),source_nonempty=sum(r['source_windows']>0 for r in rows),
        no_receiver_decision=sum(r['source_windows']==0 for r in rows),
        all_observed_rate_choices_match=sum(r['status']=='ALL_OBSERVED_RATE_CHOICES_MATCH' for r in rows),
        first_rate_divergence=sum(r['status']=='FIRST_RATE_DIVERGENCE' for r in rows),
        declarations=sum(r['declarations'] for r in rows),matching_windows=sum(r['matching_windows'] for r in rows),
        analysis_posterior_updates=sum(r['analysis_posterior_updates'] for r in rows))
    for key,value in expected.items():require(saved[key]==value,'literal summary count '+key)
    ids=sorted({r['spec']['group'] for r in rows});require([g['group'] for g in saved['groups']]==ids,'all groups')
    means=[]
    for entry in saved['groups']:
        group=[r for r in rows if r['spec']['group']==entry['group']];values=[r['matching_fraction'] for r in group if r['matching_fraction'] is not None]
        mean=math.fsum(values)/len(values) if values else None
        require(entry==dict(group=entry['group'],source_cases=len(group),available_cases=len(values),mean_matching_fraction=mean),'within-trajectory then group weights')
        if mean is not None:means.append(mean)
    require(saved['available_groups']==len(means) and saved['equal_group_matching_fraction']==(math.fsum(means)/len(means) if means else None),'equal group macro')
