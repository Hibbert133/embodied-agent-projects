"""Literal features, weights, refits and supported held-out leaf decisions."""
from collections import Counter,defaultdict
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import json,math
import numpy as np
from src.analysis import correction_trace_value_v1 as main
from src.analysis import correction_scope_risk_reference_independent_v1 as prior

io=main.io;A=('CONTINUE','VALIDATE8','MOVE_MEASURE');R=(.125,.5,2.,8.)

def forbidden(*args,**kwargs):raise RuntimeError('main trace-value math disabled during independent audit')

def literal_query(graph,action,full):
    pre=graph['pre'];ret=graph['returns'][action]
    if pre is None or ret is None:return None
    assert ret['history'][:len(pre['history'])]==pre['history']
    trace=deepcopy(ret['history'][pre['completed_steps']:])
    assert full or action==2 or not trace
    return dict(schema='EXTRA_TRACE_PUBLIC_V1',prefix=deepcopy(pre),current=deepcopy(ret['current']),integral_xy=list(ret['integral_xy']),
        controller=deepcopy(ret['controller']),completed_steps=ret['completed_steps'],acquisition_action=A[action],extra_trace=None if trace and not full else trace)

def literal_features(q):
    values=prior.literal_features(q['prefix']);values.extend(float(v) for v in q['current']['observation'])
    values.extend(float(v) for v in q['integral_xy']);values.append(q['completed_steps']/500.);values.extend(float(q['acquisition_action']==a) for a in A)
    trace=q['extra_trace']
    for i in range(500):
        if trace is None or i>=len(trace):values.extend([0.]*83);continue
        row=trace[i]
        for key in ('before','command','after'):
            values.extend(float(v) for v in (row[key] if key=='command' else row[key]['observation']))
        values.append(1.)
    assert len(values)==83093;return values

def literal_rows(graphs,heldout):
    result=[]
    for graph in graphs:
        if graph['unit'][1] in heldout:continue
        for ai in range(3):
            full=literal_query(graph,ai,True)
            if full is None:continue
            for release in (('FULL','MASK') if ai==2 else ('FULL',)):
                result.append(dict(unit=graph['unit'],action=ai,release=release,query=literal_query(graph,ai,release=='FULL'),
                    target=[graph['leaves'][4*ai+r]['loss']/500. for r in range(4)],owner=(*graph['unit'],ai)))
    return result

def literal_weights(records):
    owners=[]
    for r in records:
        if r['owner'] not in owners:owners.append(r['owner'])
    groups=sorted({o[1] for o in owners});answer=[]
    for row in records:
        count=sum(o[1]==row['unit'][1] for o in owners);copies=sum(r['owner']==row['owner'] for r in records)
        answer.append(len(owners)/(len(groups)*count*copies))
    return np.asarray(answer)

def literal_predict(model,folder,q):
    raw=literal_features(q)
    with np.load(Path(folder)/model['file'],allow_pickle=False) as b:
        z=np.asarray([max(-10.,min(10.,(raw[int(i)]-mu)/sigma)) for i,mu,sigma in zip(b['active'],b['mean'],b['scale'])])
        phi=prior.literal_kernel(z,b['centers'],model['kind']);y=np.asarray(phi)@b['coefficients']+b['intercept']
        return [max(0.,min(1.,float(v))) for v in y]

def verify_sources(m):
    actual=prior.literal_graphs(main.ROOT/m['config']['source_A1_run'],'TRAIN')
    saved=list(io.rows(main.ROOT/m['config']['source_reference_run']/'train_graphs.jsonl.gz'))
    assert actual==saved and len(actual)==54
    return actual

def audit_models(path):
    path=Path(path).resolve();m=main.checked(path);out=path.parent;bank=io.read(out/'bank.json');start=perf_counter_ns();guard={};fields=refits=0
    assert io.sha(out/'bank.json')==io.read(out/'fit_receipt.json')['bank_sha256'] and not (out/'model_audit_intent.json').exists()
    io.write(out/'model_audit_intent.json',dict(planned_refits=6,bank_sha256=io.sha(out/'bank.json'),no_automatic_retry=True))
    with main.old.recorded_guard(guard,out/'model_audit_failure.json',max_lstsq=6),patch.multiple(main,features=forbidden,query=forbidden,fit=forbidden,predict=forbidden,rows=forbidden,weights=forbidden,load_graphs=forbidden):
        graphs=verify_sources(m)
        for fold,held in enumerate(m['config']['heldout_groups']):
            records=literal_rows(graphs,held);x=np.asarray([literal_features(r['query']) for r in records]);y=np.asarray([r['target'] for r in records]);w=literal_weights(records)
            active=np.flatnonzero(np.any(x!=x[0],axis=0));mean=np.sum(x[:,active]*w[:,None],axis=0)/sum(w)
            scale=np.maximum(.05,np.sqrt(np.sum(w[:,None]*(x[:,active]-mean)**2,axis=0)/sum(w)));z=np.minimum(10,np.maximum(-10,(x[:,active]-mean)/scale))
            for kind in ('LINEAR','RBF'):
                model=bank['models'][f'F{fold}_{kind}'];n=len(records);k=np.asarray([prior.literal_kernel(v,z,kind) for v in z]);system=np.zeros((n+1,n+1))
                system[:n,:n]=k+np.diag(.01/w);system[-1,:n]=1;system[:n,-1]=1;rhs=np.concatenate((y,np.zeros((1,4))),axis=0)
                refit=np.linalg.lstsq(system,rhs,rcond=None)[0];refits+=1
                with np.load(out/'models'/model['file'],allow_pickle=False) as saved:
                    assert np.array_equal(active,saved['active']) and np.allclose(mean,saved['mean'],atol=2e-12,rtol=2e-12)
                    assert np.allclose(scale,saved['scale'],atol=2e-12,rtol=2e-12) and np.allclose(z,saved['centers'],atol=2e-12,rtol=2e-12)
                    assert np.allclose(refit,np.vstack((saved['coefficients'],saved['intercept'])),atol=2e-7,rtol=2e-7)
                assert main.old.digest_array(x)==model['features_sha256'] and main.old.digest_array(y)==model['targets_sha256'] and main.old.digest_array(w)==model['weights_sha256']
                assert io.sha(out/'models'/model['file'])==model['sha256'] and model['heldout_groups']==held and not set(model['training_groups'])&set(held)
                assert model['row_registry']==[dict(unit=r['unit'],action=r['action'],release=r['release'],weight=float(weight)) for r,weight in zip(records,w)]
                assert math.isclose(sum(w),model['original_nodes'],abs_tol=1e-10) and model['view_rows']==n
                fields+=refit.size+z.size+2*len(active)
    result=dict(integrity='PASSED',independent_refits=refits,scalar_fields=fields,bank_sha256=io.sha(out/'bank.json'),guard=guard,wall_ns=perf_counter_ns()-start,
        source_TRAIN_graph_rebuilt=True,CAL_TEST_numeric_data_used=False,main_math_disabled=True,new_physics=0,new_policy_queries=0,online_LLM_API_calls=0)
    io.write(out/'model_audit.json',result);return result

def decode_literal(selector):
    if selector=='FIXED_CONTINUE_05':return 0,True,None
    if selector=='FIXED_MOVE_05':return 2,True,None
    kind=selector.rsplit('_',1)[1]
    return (0 if selector.startswith('CONTINUE_') else 1 if selector.startswith('VALIDATE8_') else 2),not selector.startswith('MOVE_MASK_'),kind

def close(a,b):assert math.isclose(a,b,abs_tol=2e-9,rel_tol=2e-9)

def audit_replay(path):
    path=Path(path).resolve();m=main.checked(path);out=path.parent;bank=io.read(out/'bank.json');result=io.read(out/'results.json');start=perf_counter_ns();guard={};fields=0
    assert io.read(out/'model_audit.json')['bank_sha256']==io.sha(out/'bank.json') and not (out/'replay_audit.json').exists()
    with main.old.recorded_guard(guard,out/'replay_audit_failure.json'),patch.multiple(main,features=forbidden,query=forbidden,predict=forbidden,decode=forbidden,summarize=forbidden,load_graphs=forbidden,evaluate=forbidden):
        graphs=verify_sources(m);lookup={tuple(g['unit']):g for g in graphs};events=[json.loads(v) for v in (out/'replay.jsonl').read_text(encoding='utf8').splitlines()]
        assert [r['sequence'] for r in events]==list(range(len(events))) and all(a['saved_ns']<b['saved_ns'] for a,b in zip(events,events[1:]))
        current=None;seen=set();outcomes=[];metrics=[];input_sequence=None;chosen=None;q=None;values=None
        for e in events:
            key=(tuple(e['unit']),e['selector']);graph=lookup[key[0]];ai,full,kind=decode_literal(key[1]);fold=next(i for i,v in enumerate(m['config']['heldout_groups']) if e['unit'][1] in v)
            assert fold==e['fold']
            if key!=current:
                assert key not in seen;seen.add(key);current=key;input_sequence=chosen=None;q=values=None
            if e['kind']=='ALREADY_TERMINAL':assert graph['pre'] is None;chosen=(0,1)
            elif e['kind']=='FIXED_CHOICE':assert graph['pre'] is not None and kind is None and (e['action'],e['rate'])==(ai,1);chosen=(ai,1)
            elif e['kind']=='ACQUISITION_TERMINAL':assert graph['returns'][ai] is None and e['action']==ai;chosen=(ai,1)
            elif e['kind']=='PUBLIC_INPUT':
                q=literal_query(graph,ai,full);assert q==e['query'] and io.digest(q)==e['input_sha256'];input_sequence=e['sequence']
            elif e['kind']=='RATE_CHOICE':
                assert input_sequence==e['input_sequence']<e['sequence'];model=bank['models'][f'F{fold}_{kind}'];values=literal_predict(model,out/'models',q);rate=prior.first_minimum(values)
                assert e['model_sha256']==model['sha256'] and (e['action'],e['rate'])==(ai,rate) and np.allclose(values,e['values'],atol=2e-9,rtol=2e-9)
                chosen=(ai,rate);fields+=6
            else:
                assert e['kind']=='OUTCOME' and chosen is not None;action,rate=chosen;leaf=graph['leaves'][4*action+rate];same=graph['leaves'][4*action+1]
                assert e['action']==A[action] and e['rate']==R[rate] and e['loss']==leaf['loss'] and e['success']==leaf['success']
                assert e['actual_source_steps']==leaf['steps'] and e['source_case_key']==leaf['source_case_key'] and e['source_case_sha256']==leaf['source_case_sha256']
                assert e['difference_to_CONTINUE_05']==leaf['loss']-graph['leaves'][1]['loss'] and e['difference_to_same_acquisition_05']==leaf['loss']-same['loss']
                assert e['success_to_failure']==bool(same['success'] and not leaf['success']) and e['failure_to_success']==bool(not same['success'] and leaf['success'])
                assert e['live_choice']==(q is not None)
                outcomes.append({k:v for k,v in e.items() if k not in ('sequence','saved_ns','kind')});fields+=12
                if values is not None:
                    target=[v['loss']/500 for v in graph['leaves'][4*action:4*action+4]]
                    metrics.append(dict(unit=e['unit'],selector=e['selector'],MSE=float(np.mean((np.asarray(values)-target)**2))))
        assert len(outcomes)==len(seen)==540 and outcomes==result['results']
        for actual,expected in zip(result['metric_rows'],metrics):
            assert actual['unit']==expected['unit'] and actual['selector']==expected['selector'];close(actual['MSE'],expected['MSE'])
        assert len(metrics)==len(result['metric_rows'])
        for s in result['summaries']:
            rows=[r for r in outcomes if r['selector']==s['selector']];assert len(rows)==s['units']==54
            close(s['mean_loss'],sum(r['loss'] for r in rows)/54);assert s['success']==sum(r['success'] for r in rows)
            assert s['choices']==dict(Counter(r['action']+'/'+str(r['rate']) for r in rows))
            diffs=[r['difference_to_same_acquisition_05'] for r in rows]
            assert [s[k] for k in ('harm','help','ties','harm_steps','worst_harm')]==[sum(v>0 for v in diffs),sum(v<0 for v in diffs),sum(v==0 for v in diffs),sum(max(0,v) for v in diffs),max([0]+diffs)]
            close(s['mean_same_acquisition_difference'],sum(diffs)/54)
            assert s['success_to_failure']==sum(r['success_to_failure'] for r in rows) and s['failure_to_success']==sum(r['failure_to_success'] for r in rows)
            for g in range(9):
                selected=[r for r in rows if r['unit'][1]==g];assert len(selected)==6;close(s['group_mean_loss'][str(g)],sum(r['loss'] for r in selected)/6)
        for contrast in result['FULL_MASK_contrasts']:
            kind=contrast['kind'];full={tuple(r['unit']):r for r in outcomes if r['selector']=='MOVE_FULL_'+kind};masked={tuple(r['unit']):r for r in outcomes if r['selector']=='MOVE_MASK_'+kind}
            diffs={k:full[k]['loss']-masked[k]['loss'] for k in full};close(contrast['mean_FULL_minus_MASK'],sum(diffs.values())/54)
            assert contrast['units']==54 and contrast['choice_changes']==sum(full[k]['rate']!=masked[k]['rate'] for k in full)
            assert contrast['FULL_success']==sum(r['success'] for r in full.values()) and contrast['MASK_success']==sum(r['success'] for r in masked.values())
            assert [contrast[k] for k in ('FULL_harm_cases','FULL_help_cases','ties')]==[sum(v>0 for v in diffs.values()),sum(v<0 for v in diffs.values()),sum(v==0 for v in diffs.values())]
            for g in range(9):close(contrast['group_differences'][str(g)],sum(v for k,v in diffs.items() if k[1]==g)/6)
            for p in contrast['panels']:
                values=[v for k,v in diffs.items() if k[2:]==(p['task'],p['context']) and (16,32,64)[k[1]%3]==p['boundary']]
                assert p['units']==len(values)==3;close(p['mean_difference'],sum(values)/3)
        for metric in result['prediction_metrics']:
            selected=[r for r in metrics if r['selector']==metric['selector']];assert metric['live_nodes']==len(selected) and metric['missing_terminal_nodes']==54-len(selected)
            close(metric['trajectory_mean_MSE'],sum(r['MSE'] for r in selected)/len(selected))
            for g in range(9):
                values=[r['MSE'] for r in selected if r['unit'][1]==g]
                if values:close(metric['group_MSE'][str(g)],sum(values)/len(values))
                else:assert metric['group_MSE'][str(g)] is None
        assert io.sha(out/'replay.jsonl')==result['replay_sha256']
    receipt=dict(integrity='PASSED',offline_replays=len(outcomes),checked_fields=fields,main_features_prediction_and_summaries_disabled=True,
        TRAIN_only_sources_rebuilt=True,results_sha256=io.sha(out/'results.json'),replay_sha256=io.sha(out/'replay.jsonl'),guard=guard,
        wall_ns=perf_counter_ns()-start,new_physics=0,new_policy_queries=0,online_LLM_API_calls=0,not_final_deployment=True)
    io.write(out/'replay_audit.json',receipt);return receipt
