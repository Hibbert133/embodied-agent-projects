"""Separate first-fork extraction, public features and augmented-lstsq refits."""
from collections import defaultdict,Counter
from itertools import groupby,combinations
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import math,struct
import numpy as np
from src.analysis import correction_effect_learning_v1 as main
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.short_probe_journal_audit_v1 import applied
io=main.io;source=main.source


def equal(x,y):
    if isinstance(x,dict):
        io.require(type(y) is dict and set(x)==set(y),'independent object keys')
        for k in x:equal(x[k],y[k])
    elif isinstance(x,(list,tuple)):
        io.require(type(y) in (list,tuple) and len(x)==len(y),'independent array length')
        for a,b in zip(x,y):equal(a,b)
    elif type(x) is float:io.require(type(y) in (int,float) and abs(x-y)<=2e-11*(1+abs(x)),'independent scalar')
    else:io.require(x==y,'independent literal field')


def bits(u):return struct.pack('<4f',*u)


def feature(packet):
    io.require(set(packet)=={'completed_steps','current','history2','command_a','command_b'},'independent strict public features')
    o=packet['current']['observation'];a=packet['command_a'];b=packet['command_b'];d=[]
    io.require(len(packet['history2'])==2,'two genuine history increments')
    for row in packet['history2']:
        d.extend((row['after']['observation'][j]-row['before']['observation'][j])/.01 for j in range(3))
    return [1.,*o[:3],*[o[4+j]-o[j] for j in range(3)],o[3],*d,*a[2:]],a[:2],b[:2]


def design(packet,kind):
    p,a,b=feature(packet);delta=[b[j]-a[j] for j in (0,1)]
    if kind in ('GLOBAL_SCALAR','GLOBAL_MATRIX'):return delta
    if kind=='PAIRED_CONTEXT':return [v*x for v in p for x in delta]
    return [[*p,*[v*x for v in p for x in u]] for u in (a,b)]


def audit_pairs(path):
    path=Path(path);m=main.checked(path);out=path.parent/'pairs';receipt=io.read(out/'receipt.json');start=perf_counter_ns();guard={}
    for n,h in receipt['artifact_sha256'].items():io.require(io.sha(out/n)==h,'unchanged pair artifact')
    actual=io.read(out/'public_pairs.json');registered=io.read(out/'pair_register.json');private=io.read(out/'oracle_diagnostics.json');seen=[];expected_public=[];expected_private=[]
    def denied(*args,**kwargs):raise RuntimeError('main pair extraction/features disabled')
    with read_only(guard),patch.object(main,'first_difference',denied),patch.object(main,'source_nodes',denied),patch.object(main.model,'features',denied):
        cases=list(io.rows(main.SOURCE/'train/cases.jsonl.gz'));outer=iter(groupby(io.rows(main.SOURCE/'train/events.jsonl.gz'),source.case_key))
        for index in range(0,648,4):
            family=[];witnesses=[];post=[]
            for case in cases[index:index+4]:
                key,it=next(outer);io.require(key==source.case_key(case),'independent source grouping');steps=[];commit=None
                for e in it:
                    if e['event']=='STEP_COMPLETE':
                        io.require(e['logical_step']==len(steps) and e['noise_cursor_after']==len(steps)+1,'independent noise cursor');steps.append(e)
                    elif e['event']=='NOISE_COMMITMENT':commit=e['tape_sha256_oracle']
                family.append((case,steps,commit));w=case['state_witness_refs'][0];witnesses.append((w['native_sha256'],w['comparison_python_sha256']))
                post.append(None if case['post_forecast'] is None else case['post_forecast']['at_calls'])
            io.require(witnesses[0]==witnesses[1]==witnesses[2]==witnesses[3] and post[0]==post[1]==post[2]==post[3],'independent common native/RNG/entry')
            io.require(all(c['initial_fault_oracle']==family[0][0]['initial_fault_oracle'] and c['destination_oracle']==family[0][0]['destination_oracle'] for c,_,_ in family),'independent same fault interventions')
            tape=source.noise({k:family[0][0][k] for k in source.KEYS});io.require(all(c==io.digest(tape.tolist()) for _,_,c in family),'independent same noise commitment')
            for ia,ib in combinations(range(4),2):
                ca,sa,_=family[ia];cb,sb,_=family[ib];node=tuple(ca[k] for k in ('cohort','group','task','context','acquisition_action'));pid=io.digest([node,ia,ib])
                io.require(ca['initial']==cb['initial'],'independent same initial public state');at=None
                for j in range(min(len(sa),len(sb))):
                    if bits(sa[j]['command'])!=bits(sb[j]['command']):at=j;break
                    io.require(sa[j]['after']==sb[j]['after'],'independent common physical prefix')
                saved=registered[len(seen)];io.require(saved['pair_id']==pid and saved['first_difference']==at,'independent first fork identity')
                io.require(saved['source_case_sha256']==[io.digest(ca),io.digest(cb)] and saved['loss_difference']==cb['deadline_loss']-ca['deadline_loss'],'complete source outcomes for diagnostics only')
                if at is None:
                    io.require(len(sa)==len(sb),'source endpoint contradiction');status='BEFORE_DECISION_TERMINAL' if ca['pre_forecast'] is None else 'ACQUISITION_TERMINAL' if post[0] is None else 'NO_SENT_DIFFERENCE'
                else:
                    status='ACTUAL_DIVERGENCE';io.require(post[0] is not None and at>=post[0] and sa[at]['phase']==sb[at]['phase']=='TAIL_TASK','independent after-adoption fork')
                    io.require(sa[at]['simulation_time_before']==sb[at]['simulation_time_before'],'independent physical clock')
                    current=ca['initial'] if at==0 else sa[at-1]['after'];history=[]
                    for j in (at-2,at-1):
                        io.require(j>=0,'no fabricated initial history');history.append(dict(at_calls=j,before=ca['initial'] if j==0 else sa[j-1]['after'],command=sa[j]['command'],after=sa[j]['after']))
                    packet=dict(completed_steps=at,current=current,history2=history,command_a=sa[at]['command'],command_b=sb[at]['command'])
                    da=[(sa[at]['after']['observation'][j]-current['observation'][j])/.01 for j in (0,1)];db=[(sb[at]['after']['observation'][j]-current['observation'][j])/.01 for j in (0,1)]
                    target=dict(displacement_a=da,displacement_b=db,effect=[db[j]-da[j] for j in (0,1)])
                    entry={k:saved[k] for k in ('pair_id','group','task','context','boundary','acquisition_action','rates')};entry.update(input=packet,target=target);expected_public.append(entry)
                    equal(entry,actual[len(expected_public)-1]);p,a,b=feature(packet)
                    u=[b[j]-a[j] for j in (0,1)];delta=target['effect'];v=[];actions=[]
                    for case,steps,_ in (family[ia],family[ib]):
                        e=steps[at];fault=case['destination_oracle'] if at>=case['planned_boundary'] else case['initial_fault_oracle'];act=applied(e['command'],fault,tape[at])
                        io.require(act==e['executed_action_oracle'],'legacy actuator calculation/source actual action');actions.append(act)
                    v=[actions[1][j]-actions[0][j] for j in (0,1)];norm=lambda q:sum(x*x for x in q)**.5
                    expected_private.append(dict(pair_id=pid,at=at,delta_sent_xy=u,delta_applied_xy_oracle=v,effect_xy=delta,
                        nominal_sent_error=sum((delta[j]-u[j])**2 for j in (0,1))/2,applied_semantics_error_oracle=sum((delta[j]-v[j])**2 for j in (0,1))/2,
                        zero_effect_error=sum(x*x for x in delta)/2,observed_to_sent_norm_ratio=None if norm(u)==0 else norm(delta)/norm(u),sent_contrast_zero=norm(u)==0,
                        observed_to_applied_norm_ratio_oracle=None if norm(v)==0 else norm(delta)/norm(v),applied_contrast_zero_oracle=norm(v)==0,
                        source_noise_cursor=at,shared_noise_does_not_imply_noise_free_response=True))
                io.require(saved['status']==status,'independent missingness reason');seen.append(saved)
        io.require(next(outer,None) is None and len(seen)==972 and len(expected_public)==len(actual),'full independent pair population')
        equal(expected_private,private)
    result=dict(integrity='PASSED',registered_pairs=972,available_pairs=len(actual),main_extract_and_features_disabled=True,
        shared_legacy_actuator_formula_disclosed=True,guard=guard,public_pairs_sha256=io.sha(out/'public_pairs.json'),wall_ns=perf_counter_ns()-start,new_physics=0,new_fits=0,online_LLM_API_calls=0)
    io.write(out/'audit.json',result);return result


def weights(rows):
    bygroup=defaultdict(set);byunit=defaultdict(set);bynode=Counter()
    for r in rows:
        g=r['group'];unit=(g,r['task'],r['context']);node=(*unit,r['acquisition_action']);bygroup[g].add(unit);byunit[unit].add(node);bynode[node]+=1
    return np.asarray([1/len(bygroup)/len(bygroup[r['group']])/len(byunit[(r['group'],r['task'],r['context'])])/bynode[(r['group'],r['task'],r['context'],r['acquisition_action'])] for r in rows])


def fit_one(rows,kind):
    w=weights(rows);x=np.asarray([design(r['input'],kind) for r in rows]);y=np.asarray([r['target']['effect'] for r in rows])
    if kind=='GLOBAL_SCALAR':x=x.reshape(-1,1);y=y.reshape(-1,1);w=np.repeat(w,2)/2
    elif kind=='ABSOLUTE_CONTEXT':x=x.reshape(-1,48);y=np.asarray([[r['target']['displacement_a'],r['target']['displacement_b']] for r in rows]).reshape(-1,2);w=np.repeat(w,2)/2
    scales=np.asarray([sum(float(w[i])*float(x[i,j])**2 for i in range(len(x)))**.5 for j in range(x.shape[1])]);scales=np.where(scales==0,1.,scales);z=x/scales
    augmented=np.vstack([z*np.sqrt(w[:,None]),math.sqrt(.01)*np.eye(z.shape[1])]);target=np.vstack([y*np.sqrt(w[:,None]),np.zeros((z.shape[1],y.shape[1]))])
    coef=np.linalg.lstsq(augmented,target,rcond=None)[0];return dict(kind=kind,scale=scales.tolist(),coef=coef.tolist(),ridge=.01,physical_response_qualified=False,task_benefit_qualified=False)


def predict(saved,packet):
    p,a,b=feature(packet);kind=saved['kind'];du=np.asarray(b)-np.asarray(a)
    if kind=='ZERO_EFFECT':return [0.,0.]
    if kind=='NOMINAL_SENT':return du.tolist()
    if kind=='GLOBAL_SCALAR':return (du*saved['coef'][0][0]/saved['scale'][0]).tolist()
    x=np.asarray(design(packet,kind));x=x[1]-x[0] if kind=='ABSOLUTE_CONTEXT' else x
    return (x/np.asarray(saved['scale'])@np.asarray(saved['coef'])).tolist()


def audit_models(path):
    path=Path(path);m=main.checked(path);out=path.parent/'models';receipt=io.read(out/'receipt.json');rows=io.read(path.parent/'pairs/public_pairs.json');bank=io.read(out/'bank.json')
    saved_predictions=io.read(out/'predictions.json');start=perf_counter_ns();guard={};maximum=0.;count=0
    def denied(*args,**kwargs):raise RuntimeError('main effect features/fitting/prediction disabled')
    with read_only(guard,max_lstsq=36),patch.object(main,'fit_one',denied),patch.object(main,'weights',denied),patch.object(main.model,'features',denied),patch.object(main.model,'design',denied),patch.object(main.model,'predict',denied):
        for fold in range(9):
            train=[r for r in rows if r['group']!=fold];held=[r for r in rows if r['group']==fold];models={}
            for kind in main.model.KINDS:
                expected=fit_one(train,kind);meta=bank[f'{fold}/{kind}'];io.require(io.sha(out/meta['file'])==meta['sha256'],'immutable new effect weights');actual=io.read(out/meta['file'])
                io.require(np.allclose(expected['scale'],actual['scale'],atol=2e-8,rtol=2e-8) and np.allclose(expected['coef'],actual['coef'],atol=2e-8,rtol=2e-8),'independent augmented least-squares weights')
                maximum=max(maximum,float(np.max(abs(np.asarray(expected['coef'])-np.asarray(actual['coef'])))));models[kind]=expected
            for r in held:
                for kind in main.model.COMPARATORS:
                    predicted=predict(dict(kind=kind) if kind in ('ZERO_EFFECT','NOMINAL_SENT') else models[kind],r['input']);saved=saved_predictions[count]
                    io.require(saved['pair_id']==r['pair_id'] and saved['group']==fold and saved['kind']==kind,'independent held-group prediction ownership')
                    equal(predicted,saved['prediction']);equal(sum((predicted[j]-r['target']['effect'][j])**2 for j in (0,1))/2,saved['mse']);count+=1
    io.require(count==len(saved_predictions) and guard['operation_counts']['lstsq_attempts']==36,'full independent model audit budget')
    result=dict(integrity='PASSED',independent_ridge_refits=36,predictions=count,maximum_absolute_parameter_gap=maximum,
        main_features_training_prediction_disabled=True,guard=guard,source_fit_receipt_sha256=io.sha(out/'receipt.json'),
        wall_ns=perf_counter_ns()-start,new_physics=0,online_LLM_API_calls=0,not_native_or_final_qualification=True)
    io.write(out/'audit.json',result);return result


def audit_statistics(path):
    path=Path(path);main.checked(path);out=path.parent/'evaluation';panels=io.read(out/'panels.json');decision=io.read(out/'decision.json')
    rows=io.read(path.parent/'pairs/public_pairs.json');pred=io.read(path.parent/'models/predictions.json');lookup={(p['pair_id'],p['kind']):p for p in pred};start=perf_counter_ns();guard={}
    with read_only(guard):
        for panel in panels:
            subset=[r for r in rows if all(r[k]==v for k,v in zip(panel['axes'],panel['values']))];w=weights(subset)
            io.require(panel['pairs']==len(subset) and panel['independent_groups']==len(set(r['group'] for r in subset)),'independent panel denominators')
            for kind in main.model.COMPARATORS:
                values=[sum((lookup[(r['pair_id'],kind)]['prediction'][j]-r['target']['effect'][j])**2 for j in (0,1))/2 for r in subset]
                equal(sum(float(x)*v for x,v in zip(w,values)),panel['mse'][kind])
        candidates=[p for p in panels if p['axes'] in ([],['task'])];tasks=[p for p in candidates if p['axes']==['task']]
        passed=len(tasks)==3 and all(p['mse']['PAIRED_CONTEXT']<p['mse'][c] for p in candidates for c in ('ZERO_EFFECT','GLOBAL_MATRIX','ABSOLUTE_CONTEXT'))
        io.require(decision['status']==('DEV_PREDICTIVE_ADVANTAGE' if passed else 'NO_DEV_PREDICTIVE_ADVANTAGE'),'independent fixed development rule')
    result=dict(integrity='PASSED',panels=len(panels),complete_model_grouped_statistics=True,guard=guard,wall_ns=perf_counter_ns()-start,
        original_native_qualification_unchanged=True,new_physics=0,new_fits=0,online_LLM_API_calls=0);io.write(out/'audit.json',result);return result
