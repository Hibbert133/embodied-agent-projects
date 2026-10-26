"""TRAIN-only controlled extra-trace ablation on complete factual branches.

The receiver is a standard risk regressor, not a novel acquisition algorithm.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,subprocess
import numpy as np
from src.analysis import correction_scope_risk_reference_v1 as old

io=old.io;ROOT=io.ROOT;A=old.ACTIONS;R=old.RATES;KINDS=('LINEAR','RBF')
BASE=ROOT/'outputs/correction_scope/trace_value_v1'
CONFIG=ROOT/'configs/movement_task/correction_trace_value_v1.json'
PROTOCOL=ROOT/'docs/protocols/correction_trace_value_v1_zh.md'
QKEYS={'schema','prefix','current','integral_xy','controller','completed_steps','acquisition_action','extra_trace'}
VARIANTS=('CONTINUE_FULL','VALIDATE8_FULL','MOVE_FULL','MOVE_MASK')
SELECTORS=('FIXED_CONTINUE_05','FIXED_MOVE_05',*tuple(v+'_'+k for v in VARIANTS for k in KINDS))


def validate_query(q):
    io.require(type(q) is dict and set(q)==QKEYS and q['schema']=='EXTRA_TRACE_PUBLIC_V1','strict extra-trace public query, no future/registry/private fields')
    pre=old.validate_node(q['prefix']);io.require(pre['stage']=='PRE','complete original task prefix remains visible')
    old.public.public_state(q['current']);old.public.vector(q['integral_xy'],2)
    io.require(max(abs(v) for v in q['integral_xy'])<=2 and q['controller']==pre['controller'],'actual bounded return memory')
    io.require(type(q['completed_steps']) is int and pre['completed_steps']<=q['completed_steps']<=500 and q['acquisition_action'] in A,'actual spent calls and acquisition')
    io.require(not any(q['current'][k] for k in ('success','terminated','truncated')),'no model query after terminal acquisition')
    trace=q['extra_trace'];n=q['completed_steps']-pre['completed_steps']
    if trace is None:
        io.require(q['acquisition_action']=='MOVE_MEASURE' and n>0,'only paid nonempty MOVE trace may be withheld')
    else:
        io.require(type(trace) is list and len(trace)==n,'actual consecutive available extra trace')
        previous=pre['current']
        for i,row in enumerate(trace):
            io.require(type(row) is dict and set(row)=={'at_calls','before','command','after'} and row['at_calls']==pre['completed_steps']+i,'no skipped/future trace calls')
            old.public.public_state(row['before']);old.public.public_state(row['after'])
            command=old.public.vector(row['command'],4)
            io.require(max(abs(v) for v in command)<=1 and tuple(np.asarray(command,np.float32).astype(float))==command,'actual float32 sent command')
            io.require(row['before']==previous and not any(previous[k] for k in ('success','terminated','truncated')),'extra trace causal continuity')
            previous=row['after']
        io.require(previous==q['current'],'actual current observation, not a hidden replacement')
    if q['acquisition_action']=='CONTINUE':
        io.require(n==0 and trace==[] and q['current']==pre['current'] and q['integral_xy']==pre['integral_xy'],'zero-step continuation cannot fabricate evidence')
    return q


def query(graph,action,full=True):
    io.require(type(full) is bool and action in range(3),'fixed query choice')
    if graph['pre'] is None or graph['returns'][action] is None:return None
    pre=graph['pre'];ret=graph['returns'][action];old.validate_node(ret)
    io.require(ret['history'][:pre['completed_steps']]==pre['history'] and ret['acquisition_action']==A[action],'actual common returned branch')
    trace=deepcopy(ret['history'][pre['completed_steps']:])
    io.require(full or action==2 or not trace,'normal task feedback cannot be withheld as a strong reference')
    result=dict(schema='EXTRA_TRACE_PUBLIC_V1',prefix=deepcopy(pre),current=deepcopy(ret['current']),integral_xy=deepcopy(ret['integral_xy']),
        controller=deepcopy(ret['controller']),completed_steps=ret['completed_steps'],acquisition_action=A[action],extra_trace=trace if full or not trace else None)
    return validate_query(result)


def features(q):
    validate_query(q);pre=old.features(q['prefix'])
    head=np.r_[pre,q['current']['observation'],q['integral_xy'],q['completed_steps']/500.,[float(q['acquisition_action']==a) for a in A]]
    x=np.zeros(len(head)+500*83);x[:len(head)]=head
    for i,row in enumerate(q['extra_trace'] or []):
        x[len(head)+83*i:len(head)+83*(i+1)]=[*row['before']['observation'],*row['command'],*row['after']['observation'],1.]
    io.require(x.shape==(83093,) and np.isfinite(x).all(),'complete visible prefix and typed available acquisition history')
    return x


def source_bindings(config):
    reference=ROOT/config['source_reference_run'];a1=ROOT/config['source_A1_run'];commit=config['source_result_commit']
    paths=[reference/'train_graphs.jsonl.gz',reference/'fit_receipt.json',reference/'model_audit.json',a1/'train/audit.json',a1/'train/summary.json',
        a1/'manifest.json',a1/'results/statistics.json',ROOT/'outputs/correction_scope/common_state_audit_v1/train.json']
    result={}
    for p in paths:
        name=p.relative_to(ROOT).as_posix();raw=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        io.require(hashlib.sha256(raw).hexdigest()==io.sha(p),'source commit bytes '+name);result[name]=io.sha(p)
    model=io.read(reference/'model_audit.json');io.require(model['integrity']=='PASSED' and model['graph_sha256']['TRAIN']==io.sha(reference/'train_graphs.jsonl.gz'),'previous complete factual-branch audit')
    audit=io.read(a1/'train/audit.json');io.require(audit['integrity']=='PASSED','source TRAIN record audit')
    for n,h in {**audit['collection_sha256'],'examples.jsonl.gz':audit['examples_sha256']}.items():
        p=a1/'train'/n;io.require(io.sha(p)==h,'current source TRAIN raw bytes');result[p.relative_to(ROOT).as_posix()]=h
    io.require(io.read(ROOT/'outputs/correction_scope/common_state_audit_v1/train.json')['integrity']=='PASSED','actual common world/RNG/memory proof')
    return result


def prepare():
    complete=io.read(BASE/'freeze_validation/complete.json');io.require(complete['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean checked freeze')
    for n,h in complete['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed trace-effect source')
    io.require(not list(BASE.glob('run_*/manifest.json')),'one frozen run only')
    cfg=io.read(CONFIG);head=io.git('rev-parse','HEAD');bindings=source_bindings(cfg)
    out=BASE/('run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12]);out.mkdir(exist_ok=False)
    m=dict(protocol=cfg['protocol'],source_git_commit=head,config=cfg,source_sha256=complete['source_sha256'],input_sha256=bindings,
        CAL_TEST_numeric_data_used=False,old_TEST_statistics_bytes_only_for_immutability=True,new_physics=0,online_LLM_API_calls=0)
    m['manifest_id']=io.digest(m);io.write(out/'manifest.json',m);return out/'manifest.json'


def checked(path):
    path=Path(path).resolve();m=io.read(path);v=dict(m);mid=v.pop('manifest_id')
    io.require(path.parent.parent==BASE.resolve() and mid==io.digest(v) and m['config']==io.read(CONFIG),'owned frozen trace effect')
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'unchanged trace-effect source '+n)
    return m


def load_graphs(m):
    graphs=list(io.rows(ROOT/m['config']['source_reference_run']/'train_graphs.jsonl.gz'))
    io.require(len(graphs)==54 and len({tuple(g['unit']) for g in graphs})==54 and {g['unit'][0] for g in graphs}=={'TRAIN'},'only all source TRAIN units')
    io.require({g['unit'][1] for g in graphs}==set(range(9)),'all independent source groups')
    for graph in graphs:
        io.require(len(graph['leaves'])==12,'no unsupported/fabricated factual leaf')
        if graph['pre'] is None:io.require(len({(l['loss'],l['success'],l['steps']) for l in graph['leaves']})==1,'early terminal leaves agree')
        for ai in range(3):
            if graph['returns'][ai] is None:io.require(len({(l['loss'],l['success'],l['steps']) for l in graph['leaves'][4*ai:4*ai+4]})==1,'terminal return has no invented tail')
    return graphs


def rows(graphs,heldout):
    result=[]
    for graph in graphs:
        if graph['unit'][1] in heldout:continue
        for action in range(3):
            full=query(graph,action,True)
            if full is None:continue
            variants=[('FULL',full)]
            if action==2:variants.append(('MASK',query(graph,action,False)))
            for release,value in variants:
                result.append(dict(unit=graph['unit'],action=action,release=release,query=value,
                    target=[v['loss']/500. for v in graph['leaves'][4*action:4*action+4]],owner=(*graph['unit'],action)))
    return result


def weights(records):
    owners={tuple(r['owner']) for r in records};copies=Counter(tuple(r['owner']) for r in records);counts=Counter(o[1] for o in owners)
    io.require(owners and all(r['unit'][0]=='TRAIN' for r in records),'TRAIN-only independent original-node weights')
    return np.array([len(owners)/(len(counts)*counts[r['unit'][1]]*copies[tuple(r['owner'])]) for r in records])


def fit(records,kind,path):
    x=np.stack([features(r['query']) for r in records]);y=np.asarray([r['target'] for r in records]);w=weights(records)
    io.require(y.shape==(len(x),4) and np.min(y)>=0 and np.max(y)<=1,'actual normalized complete costs')
    active=np.flatnonzero(np.ptp(x,axis=0)>0);mean=np.average(x[:,active],axis=0,weights=w)
    scale=np.maximum(np.sqrt(np.average((x[:,active]-mean)**2,axis=0,weights=w)),.05);z=np.clip((x[:,active]-mean)/scale,-10,10)
    n=len(x);system=np.zeros((n+1,n+1));system[:n,:n]=old.kernel(z,z,kind)+np.diag(.01/w);system[-1,:n]=1;system[:n,-1]=1
    solution=np.linalg.solve(system,np.r_[y,np.zeros((1,4))])
    with Path(path).open('xb') as f:np.savez_compressed(f,active=active,mean=mean,scale=scale,centers=z,coefficients=solution[:-1],intercept=solution[-1])
    return dict(kind=kind,file=Path(path).name,sha256=io.sha(path),view_rows=n,original_nodes=len({r['owner'] for r in records}),
        training_groups=sorted({r['unit'][1] for r in records}),features_sha256=old.digest_array(x),targets_sha256=old.digest_array(y),weights_sha256=old.digest_array(w),
        row_registry=[dict(unit=r['unit'],action=r['action'],release=r['release'],weight=float(v)) for r,v in zip(records,w)],active_features=len(active))


def predict(model,folder,q):
    io.require(io.sha(Path(folder)/model['file'])==model['sha256'],'fixed receiver bytes')
    with np.load(Path(folder)/model['file'],allow_pickle=False) as b:
        x=features(q);z=np.clip((x[b['active']]-b['mean'])/b['scale'],-10,10)
        answer=(old.kernel(z[None,:],b['centers'],model['kind'])@b['coefficients'])[0]+b['intercept']
    io.require(np.isfinite(answer).all(),'finite risk output');return np.clip(answer,0,1).tolist()


def train(path):
    path=Path(path).resolve();m=checked(path);out=path.parent;folder=out/'models';folder.mkdir(exist_ok=False);start=perf_counter_ns();guard={};models={}
    with old.recorded_guard(guard,out/'training_failure.json',max_solve=6):
        graphs=load_graphs(m);log=old.Journal(out/'fit_attempts.jsonl')
        try:
            for fold,held in enumerate(m['config']['heldout_groups']):
                records=rows(graphs,held)
                for kind in KINDS:
                    name=f'F{fold}_{kind}';log.write('FIT_INTENT',dict(model=name,heldout=held,view_rows=len(records)))
                    model=fit(records,kind,folder/(name+'.npz'));model['heldout_groups']=held;models[name]=model
                    log.write('FIT_DONE',dict(model=name,sha256=model['sha256']))
        finally:log.close()
        bank=dict(schema='EXTRA_TRACE_FIXED_RECEIVER_BANK_V1',manifest_id=m['manifest_id'],models=models,actual_fits=len(models),
            same_receiver_for_FULL_MASK=True,no_separate_release_indicator=True,duplicate_views_preserve_original_node_weight=True)
        bank['bank_id']=io.digest(bank);io.write(out/'bank.json',bank)
    result=dict(integrity='FOR_INDEPENDENT_MODEL_AUDIT',actual_fits=len(models),bank_sha256=io.sha(out/'bank.json'),guard=guard,wall_ns=perf_counter_ns()-start,
        new_physics=0,new_policy_queries=0,online_LLM_API_calls=0,all_fits_TRAIN_only=True)
    io.write(out/'fit_receipt.json',result);return result


def decode(selector):
    if selector.startswith('FIXED_'):return (0 if selector=='FIXED_CONTINUE_05' else 2),True,None
    variant,kind=selector.rsplit('_',1);io.require(kind in KINDS and variant in VARIANTS,'registered selector')
    return (0 if variant=='CONTINUE_FULL' else 1 if variant=='VALIDATE8_FULL' else 2),variant!='MOVE_MASK',kind


def summarize(results):
    summaries=[]
    for selector in SELECTORS:
        selected=[r for r in results if r['selector']==selector];d=[r['difference_to_same_acquisition_05'] for r in selected]
        summaries.append(dict(selector=selector,units=len(selected),success=sum(r['success'] for r in selected),mean_loss=sum(r['loss'] for r in selected)/len(selected),
            group_mean_loss={str(g):sum(r['loss'] for r in selected if r['unit'][1]==g)/6 for g in range(9)},
            harm=sum(v>0 for v in d),help=sum(v<0 for v in d),ties=sum(v==0 for v in d),harm_steps=sum(max(0,v) for v in d),worst_harm=max([0]+d),
            mean_same_acquisition_difference=sum(d)/len(d),success_to_failure=sum(r['success_to_failure'] for r in selected),failure_to_success=sum(r['failure_to_success'] for r in selected),
            choices=dict(Counter(r['action']+'/'+str(r['rate']) for r in selected))))
    contrasts=[]
    for kind in KINDS:
        f={tuple(r['unit']):r for r in results if r['selector']=='MOVE_FULL_'+kind};masked={tuple(r['unit']):r for r in results if r['selector']=='MOVE_MASK_'+kind}
        diffs={k:f[k]['loss']-masked[k]['loss'] for k in f}
        panels=[]
        for task in old.TASKS:
            for context in ('UNCHANGED','CHANGED'):
                for boundary in (16,32,64):
                    keys=[k for k in f if k[2:]==(task,context) and (16,32,64)[k[1]%3]==boundary]
                    panels.append(dict(task=task,context=context,boundary=boundary,units=len(keys),mean_difference=sum(diffs[k] for k in keys)/len(keys)))
        contrasts.append(dict(kind=kind,units=len(f),mean_FULL_minus_MASK=sum(diffs.values())/len(diffs),
            group_differences={str(g):sum(v for k,v in diffs.items() if k[1]==g)/6 for g in range(9)},
            choice_changes=sum(f[k]['rate']!=masked[k]['rate'] for k in f),FULL_success=sum(r['success'] for r in f.values()),MASK_success=sum(r['success'] for r in masked.values()),
            FULL_harm_cases=sum(v>0 for v in diffs.values()),FULL_help_cases=sum(v<0 for v in diffs.values()),ties=sum(v==0 for v in diffs.values()),panels=panels))
    return summaries,contrasts


def evaluate(path):
    path=Path(path).resolve();m=checked(path);out=path.parent;bank=io.read(out/'bank.json');audit=io.read(out/'model_audit.json')
    io.require(audit['integrity']=='PASSED' and audit['bank_sha256']==io.sha(out/'bank.json'),'independently locked receivers')
    start=perf_counter_ns();guard={};log=old.Journal(out/'replay.jsonl');results=[];metric_rows=[]
    try:
        with old.recorded_guard(guard,out/'replay_failure.json'):
            for graph in load_graphs(m):
                group=graph['unit'][1];fold=next(i for i,g in enumerate(m['config']['heldout_groups']) if group in g)
                for selector in SELECTORS:
                    action,full,kind=decode(selector);info=dict(unit=graph['unit'],fold=fold,selector=selector);q=None;values=None
                    if graph['pre'] is None:action=0;rate=1;log.write('ALREADY_TERMINAL',info)
                    elif kind is None:rate=1;log.write('FIXED_CHOICE',dict(**info,action=action,rate=rate))
                    else:
                        q=query(graph,action,full)
                        if q is None:rate=1;log.write('ACQUISITION_TERMINAL',dict(**info,action=action))
                        else:
                            seq=log.write('PUBLIC_INPUT',dict(**info,query=q,input_sha256=io.digest(q)))
                            model=bank['models'][f'F{fold}_{kind}'];values=predict(model,out/'models',q);rate=old.choice(values)
                            log.write('RATE_CHOICE',dict(**info,input_sequence=seq,action=action,rate=rate,values=values,model_sha256=model['sha256']))
                    leaf=graph['leaves'][4*action+rate];same=graph['leaves'][4*action+1];baseline=graph['leaves'][1]
                    r=dict(**info,action=A[action],rate=R[rate],loss=leaf['loss'],success=leaf['success'],actual_source_steps=leaf['steps'],
                        source_case_key=leaf['source_case_key'],source_case_sha256=leaf['source_case_sha256'],live_choice=q is not None,
                        difference_to_CONTINUE_05=leaf['loss']-baseline['loss'],difference_to_same_acquisition_05=leaf['loss']-same['loss'],
                        success_to_failure=bool(same['success'] and not leaf['success']),failure_to_success=bool(not same['success'] and leaf['success']))
                    log.write('OUTCOME',r);results.append(r)
                    if values is not None:
                        target=[v['loss']/500 for v in graph['leaves'][4*action:4*action+4]]
                        metric_rows.append(dict(unit=graph['unit'],selector=selector,MSE=float(np.mean((np.asarray(values)-target)**2))))
    finally:log.close()
    io.require(len(results)==540,'all source units, kernels and fixed references')
    summaries,contrasts=summarize(results);metrics=[]
    for selector in SELECTORS[2:]:
        values=[r for r in metric_rows if r['selector']==selector];grouped={str(g):[r['MSE'] for r in values if r['unit'][1]==g] for g in range(9)}
        metrics.append(dict(selector=selector,live_nodes=len(values),missing_terminal_nodes=54-len(values),
            group_MSE={g:sum(v)/len(v) if v else None for g,v in grouped.items()},trajectory_mean_MSE=sum(r['MSE'] for r in values)/len(values)))
    result=dict(integrity='FOR_INDEPENDENT_REPLAY_AUDIT',classification='POST_HOC_TRAIN_ONLY_CROSSFITTED_DEVELOPMENT',manifest_id=m['manifest_id'],
        results=results,summaries=summaries,FULL_MASK_contrasts=contrasts,prediction_metrics=metrics,metric_rows=metric_rows,
        replay_sha256=io.sha(out/'replay.jsonl'),guard=guard,wall_ns=perf_counter_ns()-start,new_physics=0,new_policy_queries=0,online_LLM_API_calls=0,
        no_nominal_confidence_intervals_due_to_overlapping_training=True,qualification_or_novelty_claim=False,publication_goal_complete=False)
    io.write(out/'results.json',result);return result
