"""Literal supervision interventions and independently refitted/replayed controls."""
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import json
import numpy as np
from src.analysis import correction_transfer_ablation_v1 as main
from src.analysis import correction_transfer_independent_v1 as ind
from src.analysis import transfer_risk_independent_math_v1 as numbers

io=main.io;A=('CONTINUE','VALIDATE8','MOVE_MEASURE');R=(.125,.5,2.,8.)
KINDS=('FUTURE_MARGINAL_PRODUCT','FUTURE_RATE_MEAN','HISTORY_RECONSTRUCT')
P=('w1','b1','w2','b2','wr','br')


def denied(*args,**kwargs):raise RuntimeError('main auxiliary ablation implementation disabled')


def literal_past(node):
    values=node['history'][max(0,len(node['history'])-32):]
    if len(values)==0:raise ValueError('missing real past window')
    count=[0.]*24;joint=[0.]*24
    for row in values:
        b=row['before']['observation'];after=row['after']['observation'];u=row['command']
        q=int(u[0]>=0)+2*int(u[1]>=0);level=min(2,int(3*max(abs(u[0]),abs(u[1]))))
        near=int(sum((b[i+4]-b[i])**2 for i in range(3))**.5<=.1);k=(q*3+level)*2+near
        count[k]+=1;joint[k]+=sum(((after[i]-b[i])/.01-u[i])**2 for i in range(2))
    n=len(values)
    return np.asarray([*[v/n for v in count],*[v/n for v in joint],sum(joint)/n,n/32])


def literal_supervision(nodes,targets,kind):
    result=[]
    for node,blocks in zip(nodes,targets):
        if kind=='FUTURE_MARGINAL_PRODUCT':
            result.append([[*b[:24],*[b[k]*b[48] for k in range(24)],b[48],b[49]] for b in blocks])
        elif kind=='FUTURE_RATE_MEAN':
            one=[sum(float(blocks[r,k]) for r in range(4))/4 for k in range(50)];result.append([list(one) for _ in range(4)])
        elif kind=='HISTORY_RECONSTRUCT':result.append([literal_past(node).tolist() for _ in range(4)])
        else:raise ValueError('unknown intervention')
    return np.asarray(result)


def audit_models(path):
    path=Path(path).resolve();m=main.checked(path);out=path.parent;start=perf_counter_ns();guard={};ledger={};fields=0;maximum=0.;proof=[]
    bank=io.read(out/'bank.json');assert io.sha(out/'bank.json')==io.read(out/'fit_receipt.json')['bank_sha256']
    io.write(out/'model_audit_intent.json',dict(neural_refits=9,ridge_refits=9,optimizer_updates=9000,no_automatic_retry=True))
    with main.prior.old.recorded_guard(guard,out/'model_audit_failure.json',max_lstsq=9),ExitStack() as stack:
        stack.enter_context(patch.object(main.labels,'supervision',denied));stack.enter_context(patch.object(main.labels,'past_summary',denied))
        for name in ('fit','summarize'):stack.enter_context(patch.object(main,name,denied))
        for name in ('receiver_rows','historical','weights','make_basis','design','dataset','receiver_prediction','receiver_decision','pre_rows'):
            stack.enter_context(patch.object(main.prior,name,denied))
        for name in ('forward','objective','initialize','fit'):stack.enter_context(patch.object(main.prior.network,name,denied))
        for name in ('features','kernel','fit_model','predict','assemble_graphs'):stack.enter_context(patch.object(main.prior.old,name,denied))
        base=io.ROOT/m['config']['source_run'];graphs=ind.prior.literal_graphs(base,'TRAIN')
        assert graphs==list(io.rows(io.ROOT/m['config']['source_graph']));examples=list(io.rows(base/'train/examples.jsonl.gz'));binding_all={}
        availability=[]
        for graph in graphs:
            returned=[]
            for ai,node in enumerate(graph['returns']):
                reason=None if node is not None else 'ALREADY_TERMINAL' if graph['pre'] is None else 'ACQUISITION_TERMINAL'
                returned.append(dict(action=A[ai],available=node is not None,history_length=None if node is None else len(node['history']),missing_reason=reason))
            availability.append(dict(unit=graph['unit'],pre_available=graph['pre'] is not None,returns=returned))
        assert io.read(out/'source_availability.json')==availability
        for fold in range(3):
            receiver_groups,pre_groups,held=ind.fold_groups(fold);nodes,cost,factual,groups,ids=ind.rows(graphs,examples,receiver_groups)
            basis=ind.basis_for(nodes,groups);gamma=max(.05,float(np.sum(ind.mass(groups)*factual[:,:,48].mean(1))))
            for kind in KINDS:
                key=str(fold)+'/'+kind;model=bank['models'][str(fold)][kind]['receiver'];saved=ind.saved(out/'models'/model['file'])
                target=literal_supervision(nodes,factual,kind);label_path=out/'training_labels'/model['training_label_file'];saved_target=np.asarray(io.read(label_path))
                assert io.sha(label_path)==model['training_label_file_sha256'] and main.prior.old.digest_array(saved_target)==model['target_sha256']
                assert np.allclose(target,saved_target,atol=3e-12,rtol=3e-12);fields+=target.size
                assert io.sha(out/'models'/model['file'])==model['sha256'] and model['training_nodes']==ids and model['training_groups']==list(receiver_groups)
                assert np.array_equal(basis['active'],saved['active']) and abs(gamma-float(saved['gamma']))<2e-12
                for name in ('mean','scale','centers'):assert np.allclose(basis[name],saved[name],atol=2e-11,rtol=2e-11);fields+=basis[name].size
                data=ind.pack(nodes,cost,target,groups,basis,gamma)
                parameters=numbers.refit(data,'JOINT_SPO',m['config']['model_rng_seed']+fold,1000,ledger)
                gap=max(float(np.max(abs(parameters[k]-saved[k]))) for k in P);maximum=max(maximum,gap)
                assert gap<=5e-8,'independent control SGD mismatch '+key;fields+=sum(v.size for v in parameters.values())
                hn,hc,hy,hg,_=ind.rows(graphs,examples,held);hd=ind.pack(hn,hc,hy,hg,basis,gamma)
                _,_,own=numbers.evaluate(parameters,hd,'JOINT_SPO',derivatives=False)
                _,_,actual=numbers.evaluate({k:saved[k] for k in P},ind.pack(hn,hc,hy,hg,saved,gamma),'JOINT_SPO',derivatives=False)
                assert [ind.prior.first_minimum(v) for v in own['scores']]==[ind.prior.first_minimum(v) for v in actual['scores']]
                ns=[];ys=[];gs=[];bindings=[]
                for graph in graphs:
                    if graph['unit'][1] not in pre_groups or graph['pre'] is None:continue
                    choices=[];target_cost=[]
                    for ai,node in enumerate(graph['returns']):
                        if node is None:c=dict(rate=1,model_sha256=model['sha256'],terminal=True)
                        else:
                            scores=ind.receiver(model,out/'models',node)['scores'][0].tolist()
                            c=dict(rate=ind.prior.first_minimum(scores),scores=scores,model_sha256=model['sha256'],query_sha256=io.digest(node))
                        choices.append(c);target_cost.append(graph['leaves'][4*ai+c['rate']]['loss']/500)
                    ns.append(graph['pre']);ys.append(target_cost);gs.append(graph['unit'][1])
                    bindings.append(dict(unit=graph['unit'],fixed_receiver_sha256=model['sha256'],saved_choices_before_label_selection=choices,target=target_cost,
                        source_case_sha256=[graph['leaves'][4*ai+c['rate']]['source_case_sha256'] for ai,c in enumerate(choices)]))
                binding_all[key]=bindings;pre=bank['models'][str(fold)][kind]['precritic'];b=ind.saved(out/'models'/pre['file']);prep=ind.basis_for(ns,gs);z=prep['centers'];n=len(ns)
                w=ind.mass(gs)*n;k=np.asarray([ind.prior.literal_kernel(v,z,'RBF') for v in z]);system=np.zeros((n+1,n+1));system[:n,:n]=k+np.diag(.01/w);system[:n,n]=1;system[n,:n]=1
                coef=np.linalg.lstsq(system,np.vstack((ys,np.zeros((1,3)))),rcond=None)[0]
                assert np.allclose(coef,np.vstack((b['coefficients'],b['intercept'])),atol=2e-7,rtol=2e-7)
                assert pre['fixed_receiver_sha256']==model['sha256'] and io.sha(out/'models'/pre['file'])==pre['sha256']
                for name in ('active','mean','scale','centers'):assert np.allclose(prep[name],b[name],atol=2e-11,rtol=2e-11);fields+=prep[name].size
                assert main.prior.old.digest_array(ys)==pre['target_sha256'];fields+=coef.size
                proof.append(dict(fold=fold,kind=kind,parameter_gap=gap,groups=list(receiver_groups),pre_groups=list(pre_groups),heldout=list(held)))
        actual=io.read(out/'fixed_receiver_labels.json');ind.equal_tree(binding_all,actual)
        assert ledger==dict(fit_attempts=9,optimizer_steps=9000)
    reused=io.ROOT/m['config']['source_learning_run']/'model_audit.json'
    receipt=dict(integrity='PASSED',bank_sha256=io.sha(out/'bank.json'),independent_neural_ledger=ledger,independent_ridge_refits=9,
        scalar_fields=fields,maximum_parameter_absolute_gap=maximum,models=proof,guard=guard,wall_ns=perf_counter_ns()-start,
        original_literal_TRAIN_labels_reused_sha256=io.sha(reused),original_literal_TRAIN_label_fields_reused=io.read(reused)['literal_factual_target_fields'],
        main_target_network_feature_math_disabled=True,new_physics=0,new_policy_queries=0,online_LLM_API_calls=0)
    io.write(out/'model_audit.json',receipt);return receipt


def audit_replay(path):
    path=Path(path).resolve();m=main.checked(path);out=path.parent;start=perf_counter_ns();guard={};bank=io.read(out/'bank.json');result=io.read(out/'results.json')
    rows=io.read(out/'selected_rows.json');receipt=io.read(out/'replay_receipt.json')
    assert receipt['selected_sha256']==io.sha(out/'selected_rows.json') and receipt['replay_sha256']==io.sha(out/'replay.jsonl')
    source=io.ROOT/m['config']['source_learning_run'];old_rows=io.read(source/'selected_rows.json');old_results=io.read(source/'results.json')
    assert rows[:1728]==old_rows and len(rows)==2376
    io.write(out/'replay_audit_intent.json',dict(total_rows=2376,reused_rows=1728,new_offline_rows=648,no_automatic_retry=True))
    with main.prior.old.recorded_guard(guard,out/'replay_audit_failure.json'),ExitStack() as stack:
        for name in ('evaluate','summarize'):stack.enter_context(patch.object(main,name,denied))
        for name in ('receiver_prediction','receiver_decision','historical','design'):stack.enter_context(patch.object(main.prior,name,denied))
        for name in ('forward','objective','fit'):stack.enter_context(patch.object(main.prior.network,name,denied))
        for name in ('features','predict','kernel'):stack.enter_context(patch.object(main.prior.old,name,denied))
        graphs=ind.prior.literal_graphs(io.ROOT/m['config']['source_run'],'TRAIN');byunit={tuple(g['unit']):g for g in graphs}
        events=[json.loads(line) for line in (out/'replay.jsonl').read_text(encoding='utf8').splitlines()]
        assert [v['sequence'] for v in events]==list(range(len(events))) and all(a['saved_ns']<b['saved_ns'] for a,b in zip(events,events[1:]))
        for i,(e,row) in enumerate(zip(events[:1728],old_rows)):
            assert e['kind']=='SOURCE_ROW_REUSED' and e['source_row_index']==i and e['source_row_sha256']==io.digest(row) and e['source_replay_sha256']==io.sha(source/'replay.jsonl')
        stream=iter(events[1728:])
        for row in rows[1728:]:
            graph=byunit[tuple(row['unit'])];fold=graph['unit'][1]//3;kind,action=row['selector'].split('/');model=bank['models'][str(fold)][kind]
            related=[]
            while True:
                e=next(stream);assert e['unit']==row['unit'] and e['selector']==row['selector'];related.append(e)
                if e['kind']=='FACTUAL_OUTCOME':break
            ai,ri=0,1
            if graph['pre'] is None:assert related[0]['kind']=='ALREADY_TERMINAL'
            else:
                assert related[0]['query_sha256']==io.digest(graph['pre'])
                if action=='TWO_STAGE':
                    scores=ind.prior.literal_predict(model['precritic'],out/'models',graph['pre']);ai=ind.prior.first_minimum(scores)
                    assert related[0]['kind']=='PRE_DECISION' and related[0]['action']==ai and np.allclose(scores,related[0]['scores'],atol=5e-9,rtol=5e-9)
                else:ai=A.index(action);assert related[0]['kind']=='PRE_FIXED_ACTION' and related[0]['action']==ai
                node=graph['returns'][ai]
                if node is None:assert related[1]['kind']=='ACQUISITION_TERMINAL'
                else:
                    scores=ind.receiver(model['receiver'],out/'models',node)['scores'][0];ri=ind.prior.first_minimum(scores);e=related[1]
                    assert e['kind']=='RETURN_DECISION' and e['decision']['rate']==ri and e['decision']['query_sha256']==io.digest(node)
                    assert np.allclose(scores,e['decision']['scores'],atol=5e-9,rtol=5e-9)
            assert row['leaf']==graph['leaves'][4*ai+ri] and row['baseline']==graph['leaves'][1] and row['same_acquisition']==graph['leaves'][4*ai+1]
            assert row['action']==A[ai] and row['rate']==R[ri] and row['fold']==fold
            assert {k:v for k,v in related[-1].items() if k not in ('kind','sequence','saved_ns')}==row
        assert next(stream,None) is None
        for key in main.prior.SELECTORS:assert result['selectors'][key]==old_results['selectors'][key]
        for selector in main.NEW_SELECTORS:
            rr=[r for r in rows if r['selector']==selector];s=result['selectors'][selector];assert len(rr)==s['n']==54
            delta=np.asarray([r['leaf']['loss']-r['baseline']['loss'] for r in rr]);expected=dict(success=sum(v['leaf']['success'] for v in rr),
                mean_loss=sum(v['leaf']['loss'] for v in rr)/54,total_executed_steps=sum(v['leaf']['steps'] for v in rr),
                acquisition_steps=sum(v['leaf']['movement_steps']+v['leaf']['measurement_steps'] for v in rr),harm=int(sum(delta>0)),help=int(sum(delta<0)),tie=int(sum(delta==0)),harm_severity=int(sum(delta[delta>0])),
                success_to_failure=sum(v['baseline']['success'] and not v['leaf']['success'] for v in rr),failure_to_success=sum(not v['baseline']['success'] and v['leaf']['success'] for v in rr),
                same_acquisition_harm=sum(v['leaf']['loss']>v['same_acquisition']['loss'] for v in rr),same_acquisition_help=sum(v['leaf']['loss']<v['same_acquisition']['loss'] for v in rr),
                chosen_actions=dict(Counter(v['action'] for v in rr)),chosen_rates=dict(Counter(str(v['rate']) for v in rr)))
            for k,v in expected.items():ind.equal_tree(v,s[k],selector+'/'+k)
            assert len(s['panels'])==18
            for g in range(9):assert abs(s['groups'][str(g)]-sum(v['leaf']['loss'] for v in rr if v['unit'][1]==g)/6)<1e-10
            for key,value in s['panels'].items():
                task,context,boundary=key.split('/');v=[r for r in rr if r['unit'][2]==task and r['unit'][3]==context and r['boundary']==int(boundary)]
                assert len(v)==value['n']==3 and value['success']==sum(r['leaf']['success'] for r in v) and abs(value['mean_loss']-sum(r['leaf']['loss'] for r in v)/3)<1e-10
    receipt=dict(integrity='PASSED',all_rows=2376,original_rows_exactly_reused=1728,new_offline_choices_checked=648,all_selectors=44,panels_per_selector=18,
        original_replay_audit_sha256=io.sha(source/'replay_audit.json'),new_decisions_precede_factual_leaf_lookup=True,
        guard=guard,results_sha256=io.sha(out/'results.json'),replay_sha256=io.sha(out/'replay.jsonl'),wall_ns=perf_counter_ns()-start,
        new_physics=0,new_fits=0,new_policy_queries=0,online_LLM_API_calls=0)
    io.write(out/'replay_audit.json',receipt);return receipt
