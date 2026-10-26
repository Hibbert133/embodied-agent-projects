"""Second implementation of public branch support, kernels and risk decisions."""
from collections import defaultdict,Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import math,json
import numpy as np
from src.analysis import correction_scope_risk_reference_v1 as main
from src.analysis.release_learning_guard_v1 import read_only

io=main.io;A=('CONTINUE','VALIDATE8','MOVE_MEASURE');R=(.125,.5,2.,8.);T=('push-v3','reach-v3','door-open-v3')


def first_minimum(values):
    ordered=sorted(values);return next(i for i,v in enumerate(values) if v-ordered[0]<=1e-10)


def literal_node(v):
    if v is None:return None
    m=v['memory']
    result={'schema':'COMPLETE_RISK_PUBLIC_NODE_V1','stage':'PRE' if v['stage']=='PRE' else 'RETURN',
        'task':m['task'],'completed_steps':m['completed_steps'],'current':deepcopy(m['current']),
        'integral_xy':list(m['integral_xy']),'controller':deepcopy(m['controller']),'history':deepcopy(v['history']),
        'acquisition_action':None if v['stage']=='PRE' else v['acquisition_action']}
    assert set(result)=={'schema','stage','task','completed_steps','current','integral_xy','controller','history','acquisition_action'}
    assert len(result['history'])==result['completed_steps']
    return result


def literal_features(node):
    values=[1. if node['task']==t else 0. for t in T]
    values.extend(float(v) for v in node['current']['observation']);values.extend(float(v) for v in node['integral_xy'])
    values.append(node['completed_steps']/500.)
    values.extend(1. if node['acquisition_action']==a else 0. for a in A)
    for i in range(500):
        if i>=len(node['history']):values.extend([0.]*83);continue
        row=node['history'][i]
        values.extend(float(v) for v in row['before']['observation']);values.extend(float(v) for v in row['command'])
        values.extend(float(v) for v in row['after']['observation']);values.append(1.)
    assert len(values)==41548
    return values


def literal_kernel(z,centers,kind):
    d=max(1,len(z));result=[]
    for center in centers:
        result.append(float(np.dot(z,center)/d) if kind=='LINEAR' else math.exp(-float(np.sum((np.asarray(z)-center)**2))/(2*d)))
    return result


def literal_predict(model,folder,node):
    with np.load(Path(folder)/model['file'],allow_pickle=False) as saved:
        raw=literal_features(node)
        z=np.array([max(-10.,min(10.,(raw[int(i)]-mu)/sigma)) for i,mu,sigma in zip(saved['active'],saved['mean'],saved['scale'])])
        phi=literal_kernel(z,saved['centers'],model['kind'])
        answer=np.asarray(phi)@saved['coefficients']+saved['intercept']
        return [max(0.,min(1.,float(v))) for v in answer]


def literal_graphs(folder,cohort):
    cases=list(io.rows(Path(folder)/cohort.lower()/'cases.jsonl.gz'))
    examples=list(io.rows(Path(folder)/cohort.lower()/'examples.jsonl.gz'))
    order=('cohort','group','task','seed','context','planned_boundary','acquisition_action','time_constant_s')
    key=lambda row:tuple(row[k] for k in order)
    ex={(key(r['spec']),r['stage']):r['view'] for r in examples};units=defaultdict(list)
    assert len(ex)==2*len(cases)
    for row in cases:units[(row['cohort'],row['group'],row['task'],row['context'])].append(row)
    answer=[]
    for unit,rows in sorted(units.items()):
        rows=sorted(rows,key=lambda row:(A.index(row['acquisition_action']),R.index(row['time_constant_s'])))
        assert [(r['acquisition_action'],r['time_constant_s']) for r in rows]==[(a,r) for a in A for r in R]
        pre=[literal_node(ex[(key(r),'PRE')]) for r in rows]
        assert all(v==pre[0] for v in pre)
        returns=[]
        for ai in range(3):
            nodes=[literal_node(ex[(key(r),'POST')]) for r in rows[4*ai:4*ai+4]]
            assert all(v==nodes[0] for v in nodes)
            if nodes[0] is None:assert len({(r['deadline_loss'],r['success'],r['total_steps'],io.digest(r['final_memory'])) for r in rows[4*ai:4*ai+4]})==1
            returns.append(nodes[0])
        if pre[0] is None:assert all(v is None for v in returns) and len({r['deadline_loss'] for r in rows})==1
        answer.append(dict(unit=list(unit),boundary=rows[0]['planned_boundary'],pre=pre[0],returns=returns,
            leaves=[dict(loss=r['deadline_loss'],success=r['success'],steps=r['total_steps'],movement_steps=r['movement_steps'],measurement_steps=r['measurement_steps'],
                source_case_key=list(key(r)),source_case_sha256=io.digest(r)) for r in rows]))
    assert len(answer)=={'TRAIN':54,'CAL':18}[cohort]
    return answer


def literal_rows(name,graphs,models,folder,training):
    role,kind=name.rsplit('_',1);nodes=[];targets=[];groups=[];bindings=[]
    for graph in graphs:
        g=graph['unit'][1]
        if training and ((role=='receiver' and g not in range(6)) or (role=='sequential' and g not in (6,7,8))):continue
        if role in ('receiver','post_all'):
            for ai in range(3):
                node=graph['returns'][ai]
                if node is None:continue
                nodes.append(node);targets.append([graph['leaves'][4*ai+r]['loss']/500. for r in range(4)]);groups.append(g)
        elif graph['pre'] is not None:
            nodes.append(graph['pre']);groups.append(g)
            if role=='static':targets.append([leaf['loss']/500. for leaf in graph['leaves']])
            else:
                assert role=='sequential';ys=[];rates=[];model=models['receiver_'+kind]
                for ai in range(3):
                    node=graph['returns'][ai]
                    values=None if node is None else literal_predict(model,folder,node)
                    r=1 if node is None else first_minimum(values)
                    ys.append(graph['leaves'][4*ai+r]['loss']/500.);rates.append(R[r])
                targets.append(ys);bindings.append(dict(unit=graph['unit'],receiver_sha256=model['sha256'],rates=rates,targets=ys))
    return nodes,targets,groups,bindings


def denied(*args,**kwargs):raise RuntimeError('main reference implementation disabled during independent audit')


def audit_models(path):
    path=Path(path).resolve();m=main.checked(path);out=path.parent;bank=io.read(out/'bank.json');receipt=io.read(out/'fit_receipt.json')
    assert io.sha(out/'bank.json')==receipt['bank_sha256'];start=perf_counter_ns();guard={};refits=0;fields=0;proof=[]
    assert not (out/'model_audit_intent.json').exists()
    io.write(out/'model_audit_intent.json',dict(planned_independent_refits=8,no_automatic_retry=True,bank_sha256=io.sha(out/'bank.json')))
    with main.recorded_guard(guard,out/'model_audit_failure.json',max_lstsq=8),patch.multiple(main,features=denied,kernel=denied,fit_model=denied,predict=denied,training_rows=denied,assemble_graphs=denied):
        graphs={c:literal_graphs(main.ROOT/m['config']['source_run'],c) for c in ('TRAIN','CAL')}
        for c,rows in graphs.items():assert rows==list(io.rows(out/(c.lower()+'_graphs.jsonl.gz')))
        bindings={}
        for name in main.MODEL_NAMES:
            model=bank['models'][name];nodes,y,groups,labels=literal_rows(name,graphs['TRAIN'],bank['models'],out/'models',True)
            x=np.asarray([literal_features(n) for n in nodes]);y=np.asarray(y);n=len(nodes)
            counts=Counter(groups);w=np.asarray([n/(len(counts)*counts[g]) for g in groups])
            means=np.sum(x*w[:,None],axis=0)/sum(w);active=np.array([i for i in range(x.shape[1]) if any(v!=x[0,i] for v in x[1:,i])],dtype=int)
            scale=np.maximum(np.sqrt(np.sum(w[:,None]*(x[:,active]-means[active])**2,axis=0)/sum(w)),.05)
            z=np.minimum(10,np.maximum(-10,(x[:,active]-means[active])/scale))
            k=np.asarray([literal_kernel(row,z,model['kind']) for row in z]);system=np.zeros((n+1,n+1))
            system[:n,:n]=k+np.diag(.01/w);system[-1,:n]=1;system[:n,-1]=1
            rhs=np.concatenate((y,np.zeros((1,y.shape[1]))),axis=0);refit=np.linalg.lstsq(system,rhs,rcond=None)[0];refits+=1
            with np.load(out/'models'/model['file'],allow_pickle=False) as saved:
                assert np.array_equal(active,saved['active']) and np.allclose(means[active],saved['mean'],atol=2e-12,rtol=2e-12)
                assert np.allclose(scale,saved['scale'],atol=2e-12,rtol=2e-12) and np.allclose(z,saved['centers'],atol=2e-12,rtol=2e-12)
                assert np.allclose(refit,np.vstack((saved['coefficients'],saved['intercept'])),atol=2e-7,rtol=2e-7)
                fields+=refit.size+len(active)*2+z.size
            assert main.digest_array(x)==model['input_sha256'] and main.digest_array(y)==model['target_sha256'] and main.digest_array(w)==model['weights_sha256']
            assert io.sha(out/'models'/model['file'])==model['sha256'] and len(nodes)==model['rows']
            if name.startswith('sequential_'):
                assert model['fixed_receiver_sha256']==bank['models']['receiver_'+model['kind']]['sha256'];bindings[name]=labels
            proof.append(dict(model=name,rows=n,groups=sorted(counts),maximum_KKT_refit_difference=float(np.max(np.abs(system@refit-rhs)))))
        assert bindings==io.read(out/'fixed_receiver_training_labels.json')
        table=defaultdict(list)
        for graph in graphs['TRAIN']:
            if graph['pre'] is not None:table[graph['pre']['task']+'/'+str(graph['pre']['completed_steps'])].append([l['loss']/500 for l in graph['leaves']])
        assert all(np.allclose(np.mean(rows,axis=0),bank['mean_table'][key],atol=1e-14,rtol=1e-14) for key,rows in table.items())
        mean=np.mean([row for rows in table.values() for row in rows],axis=0);assert np.allclose(mean,bank['global_mean'],atol=1e-14,rtol=1e-14)
    result=dict(integrity='PASSED',independent_refits=refits,scalar_fields=fields,model_checks=proof,bank_sha256=io.sha(out/'bank.json'),
        graph_sha256={c:io.sha(out/(c.lower()+'_graphs.jsonl.gz')) for c in graphs},main_math_and_graph_builder_disabled=True,
        guard=guard,wall_ns=perf_counter_ns()-start,new_physics=0,new_policy_queries=0,online_LLM_API_calls=0)
    io.write(out/'model_audit.json',result);return result


def expected_pre(selector,bank,folder,node):
    if selector=='CONTINUE_05':return {'action':0,'rate':1,'values':None,'model':None}
    if '_POST_' in selector:return {'action':A.index(selector.split('_POST_')[0]),'rate':None,'values':None,'model':None}
    if selector=='TASK_TIME_MEAN':
        values=bank['mean_table'].get(node['task']+'/'+str(node['completed_steps']),bank['global_mean']);i=first_minimum(values)
        return {'action':i//4,'rate':i%4,'values':values,'model':'empirical_mean'}
    role,kind=selector.split('_');model=bank['models'][role.lower()+'_'+kind];values=literal_predict(model,folder,node);i=first_minimum(values)
    return {'action':i//4 if role=='STATIC' else i,'rate':i%4 if role=='STATIC' else None,'values':values,'model':model['sha256']}


def equal_decision(actual,expected):
    assert set(actual)==set(expected)
    for k in actual:
        if k=='values' and actual[k] is not None:assert np.allclose(actual[k],expected[k],atol=2e-9,rtol=2e-9)
        else:assert actual[k]==expected[k]


def audit_replay(path):
    path=Path(path).resolve();m=main.checked(path);out=path.parent;bank=io.read(out/'bank.json');results=io.read(out/'development_results.json')
    assert io.read(out/'model_audit.json')['bank_sha256']==io.sha(out/'bank.json')
    start=perf_counter_ns();guard={};checked=0
    assert not (out/'replay_audit.json').exists()
    with main.recorded_guard(guard,out/'replay_audit_failure.json'),patch.multiple(main,features=denied,kernel=denied,predict=denied,training_rows=denied,pre_choice=denied,post_choice=denied,evaluate=denied,assemble_graphs=denied):
        graphs=literal_graphs(main.ROOT/m['config']['source_run'],'CAL');by_unit={tuple(g['unit']):g for g in graphs}
        events=[json.loads(line) for line in (out/'development_replay.jsonl').read_text(encoding='utf8').splitlines()]
        assert [e['sequence'] for e in events]==list(range(len(events))) and all(a['saved_ns']<b['saved_ns'] for a,b in zip(events,events[1:]))
        current=None;outcomes=[];seen=set();pre_seq=None;post_seq=None;ai=ri=None
        for event in events:
            key=(tuple(event['unit']),event['selector']);graph=by_unit[key[0]];selector=key[1]
            if key!=current:
                assert key not in seen;seen.add(key);current=key;pre_seq=post_seq=None;ai=ri=None
            kind=event['kind']
            if kind=='ALREADY_TERMINAL':assert graph['pre'] is None;ai,ri=0,1
            elif kind=='PRE_INPUT':assert event['node']==graph['pre'] and event['input_sha256']==io.digest(graph['pre']);pre_seq=event['sequence']
            elif kind=='PRE_DECISION':
                assert event['input_sequence']==pre_seq<event['sequence'];expected=expected_pre(selector,bank,out/'models',graph['pre'])
                equal_decision(event['decision'],expected);ai,ri=expected['action'],expected['rate'];checked+=1
            elif kind=='ACQUISITION_TERMINAL':assert ri is None and event['action']==ai and graph['returns'][ai] is None;ri=1
            elif kind=='RETURN_INPUT':assert ri is None and event['node']==graph['returns'][ai] and event['input_sha256']==io.digest(event['node']);post_seq=event['sequence']
            elif kind=='POST_DECISION':
                assert event['action']==ai and event['input_sequence']==post_seq<event['sequence']
                name=('receiver_' if selector.startswith('SEQUENTIAL_') else 'post_all_')+selector.rsplit('_',1)[1]
                model=bank['models'][name];values=literal_predict(model,out/'models',graph['returns'][ai]);ri=first_minimum(values)
                equal_decision(event['decision'],dict(rate=ri,values=values,model=model['sha256']));checked+=1
            else:
                assert kind=='OUTCOME' and ai is not None and ri is not None
                leaf=graph['leaves'][4*ai+ri];baseline=graph['leaves'][1];same=graph['leaves'][4*ai+1]
                assert event['loss']==leaf['loss'] and event['success']==leaf['success'] and event['source_case_sha256']==leaf['source_case_sha256']
                assert event['source_case_key']==leaf['source_case_key'] and event['action']==A[ai] and event['rate']==R[ri]
                assert event['difference_to_CONTINUE_05']==leaf['loss']-baseline['loss'] and event['difference_to_same_acquisition_05']==leaf['loss']-same['loss']
                assert event['success_to_failure']==bool(same['success'] and not leaf['success']) and event['failure_to_success']==bool(not same['success'] and leaf['success'])
                outcomes.append({k:v for k,v in event.items() if k not in ('kind','sequence','saved_ns')});checked+=12
        assert len(outcomes)==18*12 and outcomes==results['results']
        assert len(seen)==18*12 and {s for _,s in seen}==set(main.SELECTORS)
        for summary in results['summaries']:
            rows=[r for r in outcomes if r['selector']==summary['selector']];assert len(rows)==summary['units']==18
            assert summary['success']==sum(r['success'] for r in rows) and math.isclose(summary['mean_loss'],sum(r['loss'] for r in rows)/18,abs_tol=1e-12)
            assert summary['choices']==dict(Counter(r['action']+'/'+str(r['rate']) for r in rows))
            changes=[r['difference_to_same_acquisition_05'] for r in rows]
            assert summary['same_acquisition_harm']==sum(v>0 for v in changes) and summary['same_acquisition_help']==sum(v<0 for v in changes)
            assert summary['same_acquisition_tie']==sum(v==0 for v in changes)
            assert summary['same_acquisition_harm_steps']==sum(v for v in changes if v>0) and summary['same_acquisition_worst_harm']==max([0]+changes)
            assert math.isclose(summary['same_acquisition_mean_difference'],sum(changes)/len(changes),abs_tol=1e-12)
            assert summary['success_to_failure']==sum(r['success_to_failure'] for r in rows) and summary['failure_to_success']==sum(r['failure_to_success'] for r in rows)
            assert summary['actual_source_steps']==sum(r['actual_source_steps'] for r in rows) and summary['new_environment_steps']==0
            for g,value in summary['group_differences_to_CONTINUE_05'].items():
                selected=[r for r in rows if r['unit'][1]==int(g)];assert len(selected)==6 and math.isclose(value,sum(r['difference_to_CONTINUE_05'] for r in selected)/6,abs_tol=1e-12)
        for metric in results['prediction_metrics']:
            nodes,ys,groups,_=literal_rows(metric['model'],graphs,bank['models'],out/'models',False);grouped=defaultdict(list)
            for node,y,g in zip(nodes,ys,groups):grouped[g].append(float(np.mean((np.asarray(literal_predict(bank['models'][metric['model']],out/'models',node))-y)**2)))
            expected={str(g):sum(v)/len(v) for g,v in grouped.items()}
            assert metric['factual_nodes']==len(nodes) and all(math.isclose(v,metric['group_MSE'][g],abs_tol=2e-10,rel_tol=2e-10) for g,v in expected.items())
            assert math.isclose(metric['group_mean_normalized_MSE'],sum(expected.values())/len(expected),abs_tol=2e-10,rel_tol=2e-10)
        assert io.sha(out/'development_replay.jsonl')==results['replay_log_sha256']
    result=dict(integrity='PASSED',offline_replays=len(outcomes),independent_development_groups=3,decision_and_outcome_fields=checked,
        all_source_branches_rebuilt=True,main_features_prediction_and_selectors_disabled=True,guard=guard,wall_ns=perf_counter_ns()-start,
        replay_sha256=io.sha(out/'development_replay.jsonl'),results_sha256=io.sha(out/'development_results.json'),
        new_physics=0,new_policy_queries=0,online_LLM_API_calls=0,not_an_independent_deployment=True)
    io.write(out/'replay_audit.json',result);return result
